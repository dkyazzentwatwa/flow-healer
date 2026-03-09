from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .healer_tracker import GitHubHealerTracker, HealerIssue, PullRequestDetails, PullRequestResult


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class LocalHealerTracker:
    """Local filesystem-backed tracker used when GitHub APIs are unavailable."""

    def __init__(self, *, repo_path: Path, state_root: Path) -> None:
        self.repo_path = Path(repo_path).expanduser().resolve()
        self.repo_slug = self.repo_path.name
        self._state_root = Path(state_root).expanduser().resolve()
        self._state_root.mkdir(parents=True, exist_ok=True)
        self._state_path = self._state_root / "tracker_state.json"
        self._lock = threading.RLock()
        self._viewer_login = "flow-healer-local"

    @property
    def enabled(self) -> bool:
        return self.repo_path.exists()

    def get_last_error(self) -> tuple[str, str]:
        return "", ""

    def list_ready_issues(
        self,
        *,
        required_labels: list[str],
        trusted_actors: list[str],
        limit: int = 20,
    ) -> list[HealerIssue]:
        data = self._read_state()
        trusted = {entry.strip().lower() for entry in trusted_actors if entry.strip()}
        required = [entry.strip() for entry in required_labels if entry.strip()]
        out: list[HealerIssue] = []
        for issue in data["issues"]:
            if str(issue.get("state") or "open") != "open":
                continue
            if str(issue.get("is_pull_request") or "") == "true":
                continue
            labels = [str(label).strip() for label in issue.get("labels", []) if str(label).strip()]
            if required and not all(label in labels for label in required):
                continue
            author = str(issue.get("author") or self._viewer_login).strip()
            if trusted and author.lower() not in trusted:
                continue
            out.append(
                HealerIssue(
                    issue_id=str(issue.get("number")),
                    repo=self.repo_slug,
                    title=str(issue.get("title") or ""),
                    body=str(issue.get("body") or ""),
                    author=author,
                    labels=labels,
                    priority=self._priority_from_labels(labels),
                    html_url=str(issue.get("html_url") or ""),
                    created_at=str(issue.get("created_at") or ""),
                    updated_at=str(issue.get("updated_at") or ""),
                )
            )
        out.sort(key=GitHubHealerTracker._issue_sort_key)
        return out[: max(1, int(limit))]

    def issue_has_label(self, *, issue_id: str, label: str) -> bool:
        issue = self.get_issue(issue_id=issue_id)
        if issue is None:
            return False
        labels = {str(entry).strip().lower() for entry in issue.get("labels", []) if str(entry).strip()}
        return str(label or "").strip().lower() in labels

    def get_issue(self, *, issue_id: str) -> dict[str, Any] | None:
        if not str(issue_id or "").strip():
            return None
        data = self._read_state()
        for issue in data["issues"]:
            if str(issue.get("number")) != str(issue_id).strip():
                continue
            return {
                "issue_id": str(issue.get("number")),
                "state": str(issue.get("state") or ""),
                "title": str(issue.get("title") or ""),
                "body": str(issue.get("body") or ""),
                "labels": [str(label).strip() for label in issue.get("labels", []) if str(label).strip()],
            }
        return None

    def add_issue_label(self, *, issue_id: str, label: str) -> bool:
        normalized_issue = str(issue_id or "").strip()
        normalized_label = str(label or "").strip()
        if not normalized_issue or not normalized_label:
            return False
        data = self._read_state()
        for issue in data["issues"]:
            if str(issue.get("number")) != normalized_issue:
                continue
            labels = [str(entry).strip() for entry in issue.get("labels", []) if str(entry).strip()]
            lowered = {entry.lower() for entry in labels}
            if normalized_label.lower() not in lowered:
                labels.append(normalized_label)
                issue["labels"] = labels
                issue["updated_at"] = _utc_now_iso()
                self._write_state(data)
            return True
        return False

    def remove_issue_label(self, *, issue_id: str, label: str) -> bool:
        normalized_issue = str(issue_id or "").strip()
        normalized_label = str(label or "").strip()
        if not normalized_issue or not normalized_label:
            return False
        data = self._read_state()
        for issue in data["issues"]:
            if str(issue.get("number")) != normalized_issue:
                continue
            labels = [str(entry).strip() for entry in issue.get("labels", []) if str(entry).strip()]
            filtered = [entry for entry in labels if entry.lower() != normalized_label.lower()]
            if len(filtered) != len(labels):
                issue["labels"] = filtered
                issue["updated_at"] = _utc_now_iso()
                self._write_state(data)
            return True
        return False

    def find_open_issue_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        marker = f"flow-healer-fingerprint: `{str(fingerprint or '').strip()}`"
        if not str(fingerprint or "").strip():
            return None
        data = self._read_state()
        for issue in data["issues"]:
            if str(issue.get("state") or "open") != "open":
                continue
            body = str(issue.get("body") or "")
            if marker not in body:
                continue
            return {
                "number": int(issue.get("number") or 0),
                "html_url": str(issue.get("html_url") or ""),
                "title": str(issue.get("title") or ""),
            }
        return None

    def create_issue(self, *, title: str, body: str, labels: list[str] | None = None) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        created = _utc_now_iso()
        payload: dict[str, Any] = {
            "title": title,
            "body": body,
            "labels": [str(label).strip() for label in (labels or []) if str(label).strip()],
            "state": "open",
            "author": self._viewer_login,
            "created_at": created,
            "updated_at": created,
            "is_pull_request": "false",
        }
        data = self._mutate_state(issue_update=payload)
        number = int(payload.get("number") or 0)
        issue = next((entry for entry in data["issues"] if int(entry.get("number") or 0) == number), None)
        if issue is None:
            return None
        return {
            "number": number,
            "html_url": str(issue.get("html_url") or ""),
            "state": str(issue.get("state") or "open"),
        }

    def add_issue_reaction(self, *, issue_id: str, reaction: str = "eyes") -> bool:
        return self._append_to_issue(issue_id=issue_id, field="reactions", value=str(reaction or "").strip())

    def add_issue_comment(self, *, issue_id: str, body: str) -> bool:
        return self._append_to_issue(
            issue_id=issue_id,
            field="comments",
            value={"author": self._viewer_login, "body": body, "created_at": _utc_now_iso()},
        )

    def close_issue(self, *, issue_id: str) -> bool:
        return self._set_issue_state(issue_id=issue_id, state="closed")

    def find_pr_for_issue(self, *, issue_id: str, limit: int = 100) -> PullRequestResult | None:
        data = self._read_state()
        matches = [
            pr for pr in data["pull_requests"] if str(pr.get("issue_id") or "").strip() == str(issue_id).strip()
        ]
        matches = matches[-max(1, int(limit)) :]
        if not matches:
            return None
        pr = matches[-1]
        return PullRequestResult(
            number=int(pr.get("number") or 0),
            state=str(pr.get("state") or "open"),
            html_url=str(pr.get("html_url") or ""),
        )

    def open_or_update_pr(
        self,
        *,
        issue_id: str,
        branch: str,
        title: str,
        body: str,
        base: str = "main",
    ) -> PullRequestResult | None:
        data = self._read_state()
        for pr in data["pull_requests"]:
            if str(pr.get("branch") or "").strip() != str(branch).strip():
                continue
            if str(pr.get("state") or "open") != "open":
                continue
            pr["title"] = title
            pr["body"] = body
            pr["updated_at"] = _utc_now_iso()
            self._write_state(data)
            return PullRequestResult(
                number=int(pr.get("number") or 0),
                state=str(pr.get("state") or "open"),
                html_url=str(pr.get("html_url") or ""),
            )

        pr_payload = {
            "issue_id": str(issue_id).strip(),
            "branch": str(branch).strip(),
            "base": str(base).strip() or "main",
            "title": title,
            "body": body,
            "state": "open",
            "author": self._viewer_login,
            "head_ref": str(branch).strip(),
            "updated_at": _utc_now_iso(),
            "comments": [],
            "reviews": [],
            "review_comments": [],
        }
        data = self._mutate_state(pr_update=pr_payload)
        number = int(pr_payload.get("number") or 0)
        pr = next((entry for entry in data["pull_requests"] if int(entry.get("number") or 0) == number), None)
        if pr is None:
            return None
        return PullRequestResult(
            number=number,
            state=str(pr.get("state") or "open"),
            html_url=str(pr.get("html_url") or ""),
        )

    def get_pr_state(self, *, pr_number: int) -> str:
        details = self.get_pr_details(pr_number=pr_number)
        if details is None:
            return ""
        return details.state

    def get_pr_details(self, *, pr_number: int) -> PullRequestDetails | None:
        data = self._read_state()
        for pr in data["pull_requests"]:
            if int(pr.get("number") or 0) != int(pr_number):
                continue
            state = str(pr.get("state") or "open")
            mergeable_state = "clean" if state == "open" else state
            return PullRequestDetails(
                number=int(pr.get("number") or 0),
                state=state,
                html_url=str(pr.get("html_url") or ""),
                mergeable_state=mergeable_state,
                author=str(pr.get("author") or self._viewer_login),
                head_ref=str(pr.get("head_ref") or ""),
                updated_at=str(pr.get("updated_at") or ""),
            )
        return None

    def add_pr_comment(self, *, pr_number: int, body: str) -> bool:
        return self._append_to_pr(
            pr_number=pr_number,
            field="comments",
            value={"id": self._next_event_id(), "author": self._viewer_login, "body": body, "created_at": _utc_now_iso()},
        )

    def approve_pr(self, *, pr_number: int, body: str = "") -> bool:
        return self._append_to_pr(
            pr_number=pr_number,
            field="reviews",
            value={
                "id": self._next_event_id(),
                "author": self._viewer_login,
                "body": body,
                "state": "APPROVED",
                "submitted_at": _utc_now_iso(),
            },
        )

    def merge_pr(self, *, pr_number: int, merge_method: str = "squash") -> bool:
        _ = merge_method
        return self._set_pr_state(pr_number=pr_number, state="merged")

    def close_pr(self, *, pr_number: int, comment: str = "") -> bool:
        if comment.strip():
            self.add_pr_comment(pr_number=pr_number, body=comment)
        return self._set_pr_state(pr_number=pr_number, state="closed")

    def delete_branch(self, *, branch: str) -> bool:
        _ = branch
        return True

    def list_pr_comments(self, *, pr_number: int) -> list[dict[str, Any]]:
        pr = self._get_pr(pr_number=pr_number)
        if pr is None:
            return []
        comments = pr.get("comments", [])
        return [entry for entry in comments if isinstance(entry, dict)]

    def list_pr_reviews(self, *, pr_number: int) -> list[dict[str, Any]]:
        pr = self._get_pr(pr_number=pr_number)
        if pr is None:
            return []
        reviews = pr.get("reviews", [])
        return [entry for entry in reviews if isinstance(entry, dict)]

    def list_pr_review_comments(self, *, pr_number: int) -> list[dict[str, Any]]:
        pr = self._get_pr(pr_number=pr_number)
        if pr is None:
            return []
        review_comments = pr.get("review_comments", [])
        return [entry for entry in review_comments if isinstance(entry, dict)]

    def viewer_login(self) -> str:
        return self._viewer_login

    def _append_to_issue(self, *, issue_id: str, field: str, value: Any) -> bool:
        data = self._read_state()
        for issue in data["issues"]:
            if str(issue.get("number")) != str(issue_id).strip():
                continue
            target = issue.setdefault(field, [])
            if not isinstance(target, list):
                issue[field] = [value]
            else:
                target.append(value)
            issue["updated_at"] = _utc_now_iso()
            self._write_state(data)
            return True
        return False

    def _append_to_pr(self, *, pr_number: int, field: str, value: Any) -> bool:
        data = self._read_state()
        for pr in data["pull_requests"]:
            if int(pr.get("number") or 0) != int(pr_number):
                continue
            target = pr.setdefault(field, [])
            if not isinstance(target, list):
                pr[field] = [value]
            else:
                target.append(value)
            pr["updated_at"] = _utc_now_iso()
            self._write_state(data)
            return True
        return False

    def _set_issue_state(self, *, issue_id: str, state: str) -> bool:
        data = self._read_state()
        for issue in data["issues"]:
            if str(issue.get("number")) != str(issue_id).strip():
                continue
            issue["state"] = state
            issue["updated_at"] = _utc_now_iso()
            self._write_state(data)
            return True
        return False

    def _set_pr_state(self, *, pr_number: int, state: str) -> bool:
        data = self._read_state()
        for pr in data["pull_requests"]:
            if int(pr.get("number") or 0) != int(pr_number):
                continue
            pr["state"] = state
            pr["updated_at"] = _utc_now_iso()
            self._write_state(data)
            return True
        return False

    def _get_pr(self, *, pr_number: int) -> dict[str, Any] | None:
        data = self._read_state()
        for pr in data["pull_requests"]:
            if int(pr.get("number") or 0) == int(pr_number):
                return pr
        return None

    def _next_event_id(self) -> int:
        data = self._read_state()
        next_event_id = int(data.get("next_event_id") or 1)
        data["next_event_id"] = next_event_id + 1
        self._write_state(data)
        return next_event_id

    def _mutate_state(
        self,
        *,
        issue_update: dict[str, Any] | None = None,
        pr_update: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = self._read_state()
        if issue_update is not None:
            next_number = int(data.get("next_issue_number") or 1)
            issue_update["number"] = next_number
            issue_update["html_url"] = f"local://issues/{next_number}"
            issue_update.setdefault("comments", [])
            issue_update.setdefault("reactions", [])
            data["issues"].append(issue_update)
            data["next_issue_number"] = next_number + 1
        if pr_update is not None:
            next_number = int(data.get("next_pr_number") or 1)
            pr_update["number"] = next_number
            pr_update["html_url"] = f"local://pulls/{next_number}"
            data["pull_requests"].append(pr_update)
            data["next_pr_number"] = next_number + 1
        self._write_state(data)
        return data

    def _read_state(self) -> dict[str, Any]:
        with self._lock:
            if not self._state_path.exists():
                return self._empty_state()
            try:
                payload = json.loads(self._state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return self._empty_state()
            if not isinstance(payload, dict):
                return self._empty_state()
            return {
                "next_issue_number": int(payload.get("next_issue_number") or 1),
                "next_pr_number": int(payload.get("next_pr_number") or 1),
                "next_event_id": int(payload.get("next_event_id") or 1),
                "issues": payload.get("issues") if isinstance(payload.get("issues"), list) else [],
                "pull_requests": payload.get("pull_requests") if isinstance(payload.get("pull_requests"), list) else [],
            }

    def _write_state(self, data: dict[str, Any]) -> None:
        with self._lock:
            self._state_root.mkdir(parents=True, exist_ok=True)
            temp_path = self._state_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
            temp_path.replace(self._state_path)

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "next_issue_number": 1,
            "next_pr_number": 1,
            "next_event_id": 1,
            "issues": [],
            "pull_requests": [],
        }

    @staticmethod
    def _priority_from_labels(labels: list[str]) -> int:
        normalized = {label.strip().lower() for label in labels if label.strip()}
        if "priority:p0" in normalized:
            return 0
        if "priority:p1" in normalized:
            return 1
        if "priority:p2" in normalized:
            return 2
        if "priority:p3" in normalized:
            return 3
        return 5
