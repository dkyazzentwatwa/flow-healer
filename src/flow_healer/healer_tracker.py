from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger("apple_flow.healer_tracker")


@dataclass(slots=True, frozen=True)
class HealerIssue:
    issue_id: str
    repo: str
    title: str
    body: str
    author: str
    labels: list[str]
    priority: int
    html_url: str


@dataclass(slots=True, frozen=True)
class PullRequestResult:
    number: int
    state: str
    html_url: str


class GitHubHealerTracker:
    """Minimal GitHub issue + PR adapter for autonomous healer flows."""

    def __init__(
        self,
        *,
        repo_path: Path,
        token: str | None = None,
        api_base_url: str = "https://api.github.com",
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.token = (token or os.getenv("GITHUB_TOKEN", "")).strip()
        self.api_base_url = api_base_url.rstrip("/")
        self.repo_slug = self._infer_repo_slug(self.repo_path)
        self._viewer_login: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.repo_slug)

    def list_ready_issues(
        self,
        *,
        required_labels: list[str],
        trusted_actors: list[str],
        limit: int = 20,
    ) -> list[HealerIssue]:
        if not self.enabled:
            return []
        labels_query = ",".join(sorted({label.strip() for label in required_labels if label.strip()}))
        payload = self._request_json(
            f"/repos/{self.repo_slug}/issues?state=open&per_page={int(max(1, limit))}"
            + (f"&labels={quote(labels_query)}" if labels_query else "")
        )
        trusted = {actor.strip().lower() for actor in trusted_actors if actor.strip()}
        out: list[HealerIssue] = []
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            if "pull_request" in item:
                continue
            author = str(((item.get("user") or {}).get("login")) or "").strip()
            if trusted and author.lower() not in trusted:
                continue
            label_names = [
                str((label or {}).get("name") or "").strip()
                for label in (item.get("labels") or [])
                if isinstance(label, dict)
            ]
            if required_labels and not all(req in label_names for req in required_labels):
                continue
            issue = HealerIssue(
                issue_id=str(item.get("number")),
                repo=self.repo_slug,
                title=str(item.get("title") or ""),
                body=str(item.get("body") or ""),
                author=author,
                labels=label_names,
                priority=self._priority_from_labels(label_names),
                html_url=str(item.get("html_url") or ""),
            )
            out.append(issue)
        return out

    def issue_has_label(self, *, issue_id: str, label: str) -> bool:
        if not self.enabled:
            return False
        payload = self._request_json(f"/repos/{self.repo_slug}/issues/{quote(issue_id)}")
        if not isinstance(payload, dict):
            return False
        labels = [
            str((entry or {}).get("name") or "").strip()
            for entry in (payload.get("labels") or [])
            if isinstance(entry, dict)
        ]
        return label in labels

    def find_open_issue_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        if not self.enabled or not fingerprint.strip():
            return None
        query = (
            f"repo:{self.repo_slug} is:issue is:open "
            f"\"flow-healer-fingerprint: `{fingerprint.strip()}`\""
        )
        payload = self._request_json(
            f"/search/issues?q={quote(query)}&per_page=1"
        )
        if not isinstance(payload, dict):
            return None
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return None
        item = items[0] if isinstance(items[0], dict) else {}
        number = int(item.get("number") or 0)
        if number <= 0:
            return None
        return {
            "number": number,
            "html_url": str(item.get("html_url") or ""),
            "title": str(item.get("title") or ""),
        }

    def create_issue(self, *, title: str, body: str, labels: list[str] | None = None) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        payload = self._request_json(
            f"/repos/{self.repo_slug}/issues",
            method="POST",
            body={
                "title": title,
                "body": body,
                "labels": labels or [],
            },
        )
        if not isinstance(payload, dict):
            return None
        number = int(payload.get("number") or 0)
        if number <= 0:
            return None
        return {
            "number": number,
            "html_url": str(payload.get("html_url") or ""),
            "state": str(payload.get("state") or "open"),
        }

    def open_or_update_pr(
        self,
        *,
        issue_id: str,
        branch: str,
        title: str,
        body: str,
        base: str = "main",
    ) -> PullRequestResult | None:
        if not self.enabled:
            return None

        existing = self._request_json(
            f"/repos/{self.repo_slug}/pulls?state=open&head={quote(self.repo_slug.split('/')[0] + ':' + branch)}"
        )
        if isinstance(existing, list) and existing:
            pr = existing[0] if isinstance(existing[0], dict) else {}
            return PullRequestResult(
                number=int(pr.get("number") or 0),
                state=str(pr.get("state") or "open"),
                html_url=str(pr.get("html_url") or ""),
            )

        payload = self._request_json(
            f"/repos/{self.repo_slug}/pulls",
            method="POST",
            body={
                "title": title,
                "body": body,
                "head": branch,
                "base": base,
            },
        )
        if not isinstance(payload, dict):
            return None
        return PullRequestResult(
            number=int(payload.get("number") or 0),
            state=str(payload.get("state") or "open"),
            html_url=str(payload.get("html_url") or ""),
        )

    def get_pr_state(self, *, pr_number: int) -> str:
        if not self.enabled or pr_number <= 0:
            return ""
        payload = self._request_json(f"/repos/{self.repo_slug}/pulls/{int(pr_number)}")
        if not isinstance(payload, dict):
            return ""
        if bool(payload.get("merged")):
            return "merged"
        mergeable_state = str(payload.get("mergeable_state") or "")
        if mergeable_state == "dirty":
            return "conflict"
        return str(payload.get("state") or "")

    def add_pr_comment(self, *, pr_number: int, body: str) -> bool:
        if not self.enabled or pr_number <= 0 or not body.strip():
            return False
        payload = self._request_json(
            f"/repos/{self.repo_slug}/issues/{int(pr_number)}/comments",
            method="POST",
            body={"body": body},
        )
        return isinstance(payload, dict) and "id" in payload

    def list_pr_comments(self, *, pr_number: int) -> list[dict[str, Any]]:
        if not self.enabled or pr_number <= 0:
            return []
        payload = self._request_json(f"/repos/{self.repo_slug}/issues/{int(pr_number)}/comments")
        if not isinstance(payload, list):
            return []
        return [
            {
                "id": int(item.get("id") or 0),
                "body": str(item.get("body") or ""),
                "author": str((item.get("user") or {}).get("login") or "").strip(),
                "created_at": str(item.get("created_at") or ""),
            }
            for item in payload
            if isinstance(item, dict)
        ]

    def list_pr_reviews(self, *, pr_number: int) -> list[dict[str, Any]]:
        if not self.enabled or pr_number <= 0:
            return []
        payload = self._request_json(f"/repos/{self.repo_slug}/pulls/{int(pr_number)}/reviews")
        if not isinstance(payload, list):
            return []
        return [
            {
                "id": int(item.get("id") or 0),
                "body": str(item.get("body") or ""),
                "author": str((item.get("user") or {}).get("login") or "").strip(),
                "state": str(item.get("state") or ""),
                "created_at": str(item.get("submitted_at") or item.get("created_at") or ""),
            }
            for item in payload
            if isinstance(item, dict)
        ]

    def list_pr_review_comments(self, *, pr_number: int) -> list[dict[str, Any]]:
        if not self.enabled or pr_number <= 0:
            return []
        payload = self._request_json(f"/repos/{self.repo_slug}/pulls/{int(pr_number)}/comments")
        if not isinstance(payload, list):
            return []
        return [
            {
                "id": int(item.get("id") or 0),
                "body": str(item.get("body") or ""),
                "author": str((item.get("user") or {}).get("login") or "").strip(),
                "path": str(item.get("path") or ""),
                "created_at": str(item.get("created_at") or ""),
            }
            for item in payload
            if isinstance(item, dict)
        ]

    def viewer_login(self) -> str:
        if self._viewer_login is not None:
            return self._viewer_login
        if not self.enabled:
            self._viewer_login = ""
            return self._viewer_login
        payload = self._request_json("/user")
        if not isinstance(payload, dict):
            self._viewer_login = ""
            return self._viewer_login
        self._viewer_login = str(payload.get("login") or "").strip()
        return self._viewer_login

    def _request_json(self, path: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
        url = f"{self.api_base_url}{path}"
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = Request(url, method=method, data=data)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "apple-flow-healer")
        req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            logger.warning("GitHub API %s %s failed: %s", method, path, exc)
            return {}
        except URLError as exc:
            logger.warning("GitHub API network error for %s %s: %s", method, path, exc)
            return {}
        except json.JSONDecodeError:
            logger.warning("GitHub API returned non-JSON response for %s %s", method, path)
            return {}

    @staticmethod
    def _priority_from_labels(labels: list[str]) -> int:
        lowered = {label.lower() for label in labels}
        if "severity:critical" in lowered or "priority:p0" in lowered:
            return 0
        if "priority:p1" in lowered:
            return 10
        if "priority:p2" in lowered:
            return 20
        return 100

    @staticmethod
    def _infer_repo_slug(repo_path: Path) -> str:
        try:
            proc = subprocess.run(
                ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode != 0:
                return ""
            raw = (proc.stdout or "").strip()
            # Supports https://github.com/owner/repo(.git) and git@github.com:owner/repo(.git)
            match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$", raw)
            if not match:
                return ""
            owner = match.group("owner").strip()
            repo = match.group("repo").strip()
            if not owner or not repo:
                return ""
            return f"{owner}/{repo}"
        except Exception:
            return ""
