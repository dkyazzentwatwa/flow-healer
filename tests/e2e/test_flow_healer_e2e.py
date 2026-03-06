from __future__ import annotations

import difflib
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

import flow_healer.service as service_module
from flow_healer.config import AppConfig, RelaySettings, ServiceSettings
from flow_healer.healer_tracker import GitHubHealerTracker
from flow_healer.service import FlowHealerService
from flow_healer.store import SQLiteStore


def _git(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        check=True,
        capture_output=True,
        text=True,
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_patch(path: str, before: str, after: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "```diff\n" + "".join(diff) + "```\n"


def _run_pytest_locally(workspace: Path, command: list[str], timeout_seconds: int) -> dict[str, Any]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(workspace) if not existing else f"{workspace}{os.pathsep}{existing}"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *command[1:]],
        cwd=str(workspace),
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=max(30, timeout_seconds),
    )
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return {
        "exit_code": int(proc.returncode),
        "output_tail": output[-2000:],
    }


def _build_demo_repo(tmp_path: Path) -> Path:
    repo_path = tmp_path / "repo"
    origin_path = tmp_path / "origin.git"
    repo_path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-b", "main"], cwd=repo_path)
    _git(["config", "user.name", "Flow Healer Test"], cwd=repo_path)
    _git(["config", "user.email", "flow-healer@example.com"], cwd=repo_path)
    _write(
        repo_path / "demo.py",
        "def add(a: int, b: int) -> int:\n"
        "    return a - b\n",
    )
    _write(
        repo_path / "tests" / "test_demo.py",
        "from demo import add\n\n"
        "def test_add() -> None:\n"
        "    assert add(2, 3) == 5\n",
    )
    _git(["add", "."], cwd=repo_path)
    _git(["commit", "-m", "init"], cwd=repo_path)
    _git(["init", "--bare", str(origin_path)])
    _git(["remote", "add", "origin", str(origin_path)], cwd=repo_path)
    _git(["push", "-u", "origin", "main"], cwd=repo_path)
    return repo_path


@dataclass
class FakeGitHubIssue:
    number: int
    title: str
    body: str
    labels: list[str]
    state: str = "open"
    author: str = "alice"


class FakeGitHubState:
    def __init__(self, *, repo_slug: str, viewer_login: str = "healer-service") -> None:
        self.repo_slug = repo_slug
        self.viewer_login = viewer_login
        self._lock = threading.Lock()
        self._issue_counter = 0
        self._pr_counter = 0
        self._comment_counter = 1000
        self._review_counter = 2000
        self._review_comment_counter = 3000
        self.issues: dict[int, FakeGitHubIssue] = {}
        self.pulls: dict[int, dict[str, Any]] = {}
        self.issue_comments: dict[int, list[dict[str, Any]]] = {}
        self.reviews: dict[int, list[dict[str, Any]]] = {}
        self.review_comments: dict[int, list[dict[str, Any]]] = {}

    def add_issue(self, *, title: str, body: str, labels: list[str], author: str = "alice") -> int:
        with self._lock:
            self._issue_counter += 1
            issue = FakeGitHubIssue(
                number=self._issue_counter,
                title=title,
                body=body,
                labels=list(labels),
                author=author,
            )
            self.issues[issue.number] = issue
            return issue.number

    def add_issue_comment(self, *, pr_number: int, body: str, author: str) -> int:
        with self._lock:
            self._comment_counter += 1
            entry = {
                "id": self._comment_counter,
                "body": body,
                "user": {"login": author},
                "created_at": f"2026-03-06T01:{self._comment_counter % 60:02d}:00Z",
            }
            self.issue_comments.setdefault(pr_number, []).append(entry)
            return entry["id"]

    def add_review(self, *, pr_number: int, body: str, author: str, state: str = "CHANGES_REQUESTED") -> int:
        with self._lock:
            self._review_counter += 1
            entry = {
                "id": self._review_counter,
                "body": body,
                "state": state,
                "user": {"login": author},
                "submitted_at": f"2026-03-06T02:{self._review_counter % 60:02d}:00Z",
            }
            self.reviews.setdefault(pr_number, []).append(entry)
            return entry["id"]

    def add_review_comment(self, *, pr_number: int, body: str, author: str, path: str) -> int:
        with self._lock:
            self._review_comment_counter += 1
            entry = {
                "id": self._review_comment_counter,
                "body": body,
                "path": path,
                "user": {"login": author},
                "created_at": f"2026-03-06T03:{self._review_comment_counter % 60:02d}:00Z",
            }
            self.review_comments.setdefault(pr_number, []).append(entry)
            return entry["id"]

    def issue_payload(self, issue: FakeGitHubIssue) -> dict[str, Any]:
        return {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body,
            "state": issue.state,
            "html_url": f"https://example.test/{self.repo_slug}/issues/{issue.number}",
            "user": {"login": issue.author},
            "labels": [{"name": label} for label in issue.labels],
        }

    def merge_pr(self, pr_number: int) -> None:
        with self._lock:
            pr = self.pulls.get(pr_number)
            if pr is None:
                return
            pr["state"] = "closed"
            pr["merged"] = True


class FakeGitHubAPI:
    def __init__(self, state: FakeGitHubState) -> None:
        self.state = state
        self.base_url = "https://fake-github.local"

    def request_json(self, path: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
        parsed = urlsplit(path)
        parts = [part for part in parsed.path.split("/") if part]
        query = parse_qs(parsed.query)
        payload = body or {}

        if parsed.path == "/user":
            return {"login": self.state.viewer_login}

        if parts[:2] == ["search", "issues"]:
            search_query = query.get("q", [""])[0]
            match = re.search(r"flow-healer-fingerprint:\s*`([^`]+)`", search_query)
            fingerprint = match.group(1) if match else ""
            items = []
            for issue in self.state.issues.values():
                if issue.state == "open" and fingerprint and fingerprint in issue.body:
                    items.append(self.state.issue_payload(issue))
            return {"items": items[:1]}

        if len(parts) < 4 or parts[0] != "repos":
            return {}

        repo_slug = f"{parts[1]}/{parts[2]}"
        if repo_slug != self.state.repo_slug:
            return {}

        if method == "GET":
            if parts[3] == "issues" and len(parts) == 4:
                labels_csv = query.get("labels", [""])[0]
                wanted_labels = [label.strip() for label in labels_csv.split(",") if label.strip()]
                response = []
                for issue in self.state.issues.values():
                    if issue.state != "open":
                        continue
                    if wanted_labels and not all(label in issue.labels for label in wanted_labels):
                        continue
                    response.append(self.state.issue_payload(issue))
                return response

            if parts[3] == "issues" and len(parts) == 5:
                issue = self.state.issues.get(int(parts[4]))
                return self.state.issue_payload(issue) if issue is not None else {}

            if parts[3] == "issues" and len(parts) == 6 and parts[5] == "comments":
                return list(self.state.issue_comments.get(int(parts[4]), []))

            if parts[3] == "pulls" and len(parts) == 4:
                head = query.get("head", [""])[0]
                return [
                    pr for pr in self.state.pulls.values()
                    if pr.get("state") == "open" and (not head or pr.get("head_label") == head)
                ]

            if parts[3] == "pulls" and len(parts) == 5:
                pr = self.state.pulls.get(int(parts[4]))
                if not pr:
                    return {}
                return {**pr, "merged": bool(pr.get("merged")), "mergeable_state": "clean"}

            if parts[3] == "pulls" and len(parts) == 6 and parts[5] == "reviews":
                return list(self.state.reviews.get(int(parts[4]), []))

            if parts[3] == "pulls" and len(parts) == 6 and parts[5] == "comments":
                return list(self.state.review_comments.get(int(parts[4]), []))

            return {}

        if method == "POST":
            if parts[3] == "issues" and len(parts) == 4:
                number = self.state.add_issue(
                    title=str(payload.get("title") or ""),
                    body=str(payload.get("body") or ""),
                    labels=[str(label) for label in payload.get("labels") or []],
                    author=self.state.viewer_login,
                )
                issue = self.state.issues[number]
                return self.state.issue_payload(issue)

            if parts[3] == "issues" and len(parts) == 6 and parts[5] == "comments":
                comment_id = self.state.add_issue_comment(
                    pr_number=int(parts[4]),
                    body=str(payload.get("body") or ""),
                    author=self.state.viewer_login,
                )
                return {"id": comment_id}

            if parts[3] == "issues" and len(parts) == 6 and parts[5] == "reactions":
                return {"id": 9999}

            if parts[3] == "pulls" and len(parts) == 4:
                with self.state._lock:
                    self.state._pr_counter += 1
                    pr_number = self.state._pr_counter
                    branch = str(payload.get("head") or "")
                    head_label = f"{repo_slug.split('/')[0]}:{branch}" if branch else ""
                    pr = {
                        "number": pr_number,
                        "state": "open",
                        "html_url": f"https://example.test/{repo_slug}/pull/{pr_number}",
                        "head": {"ref": branch},
                        "base": {"ref": str(payload.get("base") or "main")},
                        "title": str(payload.get("title") or ""),
                        "body": str(payload.get("body") or ""),
                        "head_label": head_label,
                    }
                    self.state.pulls[pr_number] = pr
                return pr

        if method == "PATCH":
            if parts[3] == "issues" and len(parts) == 5:
                issue = self.state.issues.get(int(parts[4]))
                if issue is None:
                    return {}
                issue.state = str(payload.get("state") or issue.state)
                return self.state.issue_payload(issue)

        return {}


class ScriptedConnector:
    def __init__(
        self,
        *,
        proposer_outputs: dict[str, list[Any]],
        verifier_outputs: dict[str, list[Any]] | None = None,
        reviewer_outputs: dict[str, list[Any]] | None = None,
    ) -> None:
        self.proposer_outputs = {key: list(value) for key, value in proposer_outputs.items()}
        self.verifier_outputs = {key: list(value) for key, value in (verifier_outputs or {}).items()}
        self.reviewer_outputs = {key: list(value) for key, value in (reviewer_outputs or {}).items()}
        self.prompts: list[tuple[str, str]] = []

    def ensure_started(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def get_or_create_thread(self, sender: str) -> str:
        return sender

    def reset_thread(self, sender: str) -> str:
        return sender

    def run_turn(self, thread_id: str, prompt: str) -> str:
        self.prompts.append((thread_id, prompt))
        if thread_id.startswith("healer-verify:"):
            issue_id = thread_id.split(":", 1)[1]
            outputs = self.verifier_outputs.get(issue_id)
            if not outputs:
                return json.dumps({"verdict": "pass", "summary": "ok"})
            step = outputs.pop(0)
            self.verifier_outputs[issue_id] = outputs
            return step(prompt) if callable(step) else str(step)
        if thread_id.startswith("healer-review:"):
            issue_id = thread_id.split(":", 1)[1]
            outputs = self.reviewer_outputs.get(issue_id)
            if not outputs:
                return "LGTM from reviewer agent."
            step = outputs.pop(0)
            self.reviewer_outputs[issue_id] = outputs
            return step(prompt) if callable(step) else str(step)
        if thread_id.startswith("healer:"):
            issue_id = thread_id.split(":", 1)[1]
            outputs = self.proposer_outputs[issue_id]
            step = outputs.pop(0)
            return step(prompt) if callable(step) else str(step)
        raise AssertionError(f"Unexpected thread id: {thread_id}")


def _make_service(repo_path: Path, *, state_root: Path, api_base_url: str, enable_scan_issue_creation: bool = False) -> FlowHealerService:
    return FlowHealerService(
        AppConfig(
            service=ServiceSettings(
                github_token_env="GITHUB_TOKEN",
                github_api_base_url=api_base_url,
                connector_command="python3",
                state_root=str(state_root),
            ),
            repos=[
                RelaySettings(
                    repo_name="demo",
                    healer_repo_path=str(repo_path),
                    healer_repo_slug="owner/repo",
                    healer_issue_required_labels=["healer:ready"],
                    healer_pr_required_label="healer:pr-approved",
                    healer_scan_enable_issue_creation=enable_scan_issue_creation,
                    healer_scan_default_labels=["kind:scan"],
                )
            ],
        )
    )


def _clear_backoff(db_path: Path, *, issue_id: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE healer_issues SET backoff_until = NULL WHERE issue_id = ?", (issue_id,))
    conn.commit()
    conn.close()


@pytest.fixture
def portable_pytest_gates(monkeypatch):
    monkeypatch.setattr(service_module, "CodexCliConnector", lambda **kwargs: None)
    monkeypatch.setattr(
        "flow_healer.healer_runner._run_pytest_locally",
        lambda workspace, command, timeout_seconds: _run_pytest_locally(workspace, command, timeout_seconds),
    )
    monkeypatch.setattr(
        "flow_healer.healer_runner._run_pytest_in_docker",
        lambda workspace, command, timeout_seconds: _run_pytest_locally(workspace, command, timeout_seconds),
    )


@pytest.fixture
def fake_github(monkeypatch):
    apis: dict[str, FakeGitHubAPI] = {}
    original = GitHubHealerTracker._request_json

    def _fake_request(self, path: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
        api = apis.get(self.api_base_url)
        if api is None:
            return original(self, path, method=method, body=body)
        return api.request_json(path, method=method, body=body)

    monkeypatch.setattr(GitHubHealerTracker, "_request_json", _fake_request)

    def _register(state: FakeGitHubState) -> FakeGitHubAPI:
        api = FakeGitHubAPI(state)
        apis[api.base_url] = api
        return api

    return _register


def test_e2e_issue_ingestion_to_pr_open(tmp_path: Path, monkeypatch, portable_pytest_gates, fake_github) -> None:
    repo_path = _build_demo_repo(tmp_path)
    state = FakeGitHubState(repo_slug="owner/repo")
    issue_number = state.add_issue(
        title="Fix addition bug",
        body="Please repair the bug in demo.py",
        labels=["healer:ready", "healer:pr-approved"],
    )
    connector = ScriptedConnector(
        proposer_outputs={
            str(issue_number): [
                _make_patch(
                    "demo.py",
                    "def add(a: int, b: int) -> int:\n    return a - b\n",
                    "def add(a: int, b: int) -> int:\n    return a + b\n",
                )
            ]
        },
    )
    monkeypatch.setattr(service_module, "CodexCliConnector", lambda **kwargs: connector)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    api = fake_github(state)
    service = _make_service(repo_path, state_root=tmp_path / "state", api_base_url=api.base_url)
    service.start("demo", once=True)

    rows = service.status_rows("demo")
    doctor = service.doctor_rows("demo")

    assert len(state.pulls) == 1
    pr_number = next(iter(state.pulls))
    assert state.issue_comments[pr_number][-1]["body"] == "LGTM from reviewer agent."
    assert any("Flow's on it" in comment["body"] for comment in state.issue_comments[issue_number])
    assert any("PR is up and cruising" in comment["body"] for comment in state.issue_comments[issue_number])
    assert rows[0]["state_counts"]["pr_open"] == 1
    assert doctor[0]["github_token_present"] is True

    store = SQLiteStore(service.config.repo_db_path("demo"))
    store.bootstrap()
    issue = store.get_healer_issue(str(issue_number))
    assert issue is not None
    assert issue["state"] == "pr_open"
    store.close()


def test_e2e_retry_cleans_workspace_before_second_attempt(tmp_path: Path, monkeypatch, portable_pytest_gates, fake_github) -> None:
    repo_path = _build_demo_repo(tmp_path)
    state = FakeGitHubState(repo_slug="owner/repo")
    issue_number = state.add_issue(
        title="Retry addition bug",
        body="Fix the bug in demo.py",
        labels=["healer:ready", "healer:pr-approved"],
    )
    connector = ScriptedConnector(
        proposer_outputs={
            str(issue_number): [
                _make_patch(
                    "demo.py",
                    "def add(a: int, b: int) -> int:\n    return a - b\n",
                    "def add(a: int, b: int) -> int:\n    return a * b\n",
                ),
                _make_patch(
                    "demo.py",
                    "def add(a: int, b: int) -> int:\n    return a - b\n",
                    "def add(a: int, b: int) -> int:\n    return a + b\n",
                ),
            ]
        },
    )
    monkeypatch.setattr(service_module, "CodexCliConnector", lambda **kwargs: connector)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    api = fake_github(state)
    service = _make_service(repo_path, state_root=tmp_path / "state", api_base_url=api.base_url)
    service.start("demo", once=True)
    _clear_backoff(service.config.repo_db_path("demo"), issue_id=str(issue_number))
    service.start("demo", once=True)

    assert len(state.pulls) == 1
    store = SQLiteStore(service.config.repo_db_path("demo"))
    store.bootstrap()
    issue = store.get_healer_issue(str(issue_number))
    assert issue is not None
    assert issue["state"] == "pr_open"
    attempts = store.list_healer_attempts(issue_id=str(issue_number), limit=5)
    assert [attempt["state"] for attempt in attempts][:2] == ["pr_open", "failed"]
    store.close()


def test_e2e_pr_feedback_requeues_and_updates_existing_pr(tmp_path: Path, monkeypatch, portable_pytest_gates, fake_github) -> None:
    repo_path = _build_demo_repo(tmp_path)
    state = FakeGitHubState(repo_slug="owner/repo")
    issue_number = state.add_issue(
        title="Follow up on review",
        body="Fix demo.py and respond to review",
        labels=["healer:ready", "healer:pr-approved"],
    )

    def second_fix(prompt: str) -> str:
        assert "PR comment from @bob" in prompt
        assert "PR review (changes_requested) from @reviewer" in prompt
        assert "Inline review comment on demo.py from @reviewer" in prompt
        return _make_patch(
            "demo.py",
            "def add(a: int, b: int) -> int:\n    return a + b\n",
            "def add(a: int, b: int) -> int:\n    # review addressed\n    return a + b\n",
        )

    connector = ScriptedConnector(
        proposer_outputs={
            str(issue_number): [
                _make_patch(
                    "demo.py",
                    "def add(a: int, b: int) -> int:\n    return a - b\n",
                    "def add(a: int, b: int) -> int:\n    return a + b\n",
                ),
                second_fix,
            ]
        },
    )
    monkeypatch.setattr(service_module, "CodexCliConnector", lambda **kwargs: connector)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    api = fake_github(state)
    service = _make_service(repo_path, state_root=tmp_path / "state", api_base_url=api.base_url)
    service.start("demo", once=True)
    pr_number = next(iter(state.pulls))
    state.add_issue_comment(pr_number=pr_number, body="Please also note the review feedback.", author="bob")
    state.add_review(pr_number=pr_number, body="Please cover the review edge case.", author="reviewer")
    state.add_review_comment(pr_number=pr_number, body="Add a tiny note here.", author="reviewer", path="demo.py")
    service.start("demo", once=True)

    assert len(state.pulls) == 1
    assert len(state.issue_comments[pr_number]) >= 2
    store = SQLiteStore(service.config.repo_db_path("demo"))
    store.bootstrap()
    issue = store.get_healer_issue(str(issue_number))
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert int(issue["last_issue_comment_id"]) > 0
    assert int(issue["last_review_id"]) > 0
    assert int(issue["last_review_comment_id"]) > 0
    store.close()


def test_e2e_scan_creates_and_dedupes_issue(tmp_path: Path, monkeypatch, fake_github) -> None:
    repo_path = _build_demo_repo(tmp_path)
    state = FakeGitHubState(repo_slug="owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    api = fake_github(state)
    service = _make_service(
        repo_path,
        state_root=tmp_path / "state",
        api_base_url=api.base_url,
        enable_scan_issue_creation=True,
    )
    first = service.run_scan("demo", dry_run=False)
    second = service.run_scan("demo", dry_run=False)

    assert first[0]["summary"]["findings_over_threshold"] == 1
    assert len(first[0]["summary"]["created_issues"]) == 1
    assert second[0]["summary"]["deduped_count"] == 1
    assert second[0]["summary"]["created_issues"] == []


def test_e2e_pending_approval_posts_issue_comment(tmp_path: Path, monkeypatch, fake_github) -> None:
    repo_path = _build_demo_repo(tmp_path)
    state = FakeGitHubState(repo_slug="owner/repo")
    issue_number = state.add_issue(
        title="Update demo doc note",
        body="Add a roadmap note to demo.py",
        labels=["healer:ready"],
    )
    connector = ScriptedConnector(
        proposer_outputs={
            str(issue_number): [
                _make_patch(
                    "demo.py",
                    "def add(a: int, b: int) -> int:\n    return a - b\n",
                    "def add(a: int, b: int) -> int:\n    # roadmap note\n    return a - b\n",
                )
            ]
        },
    )
    monkeypatch.setattr(service_module, "CodexCliConnector", lambda **kwargs: connector)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(
        "flow_healer.healer_runner._run_test_gates",
        lambda *args, **kwargs: {
            "mode": "local_only",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        },
    )

    api = fake_github(state)
    service = _make_service(repo_path, state_root=tmp_path / "state", api_base_url=api.base_url)
    service.start("demo", once=True)

    comments = state.issue_comments[issue_number]
    assert any("Flow's on it" in comment["body"] for comment in comments)
    assert any("Required label to continue: `healer:pr-approved`" in comment["body"] for comment in comments)


def test_e2e_merged_pr_closes_issue_and_marks_resolved(tmp_path: Path, monkeypatch, portable_pytest_gates, fake_github) -> None:
    repo_path = _build_demo_repo(tmp_path)
    state = FakeGitHubState(repo_slug="owner/repo")
    issue_number = state.add_issue(
        title="Fix addition bug",
        body="Please repair the bug in demo.py",
        labels=["healer:ready", "healer:pr-approved"],
    )
    connector = ScriptedConnector(
        proposer_outputs={
            str(issue_number): [
                _make_patch(
                    "demo.py",
                    "def add(a: int, b: int) -> int:\n    return a - b\n",
                    "def add(a: int, b: int) -> int:\n    return a + b\n",
                )
            ]
        },
    )
    monkeypatch.setattr(service_module, "CodexCliConnector", lambda **kwargs: connector)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    api = fake_github(state)
    service = _make_service(repo_path, state_root=tmp_path / "state", api_base_url=api.base_url)
    service.start("demo", once=True)

    pr_number = next(iter(state.pulls))
    state.merge_pr(pr_number)

    service.start("demo", once=True)

    store = SQLiteStore(service.config.repo_db_path("demo"))
    store.bootstrap()
    issue = store.get_healer_issue(str(issue_number))
    assert issue is not None
    assert issue["state"] == "resolved"
    assert issue["pr_state"] == "merged"
    assert state.issues[issue_number].state == "closed"
    assert any("Merged and wrapped up" in comment["body"] for comment in state.issue_comments[issue_number])
    store.close()
