from __future__ import annotations

import json
import logging
import os
import random
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True, frozen=True)
class PullRequestResult:
    number: int
    state: str
    html_url: str


@dataclass(slots=True, frozen=True)
class PullRequestDetails:
    number: int
    state: str
    html_url: str
    mergeable_state: str
    author: str
    head_ref: str = ""
    updated_at: str = ""


@dataclass(slots=True, frozen=True)
class TrackerRequestMetric:
    method: str
    path: str
    status: str
    duration_ms: int


class GitHubHealerTracker:
    """Minimal GitHub issue + PR adapter for autonomous healer flows."""

    def __init__(
        self,
        *,
        repo_path: Path,
        token: str | None = None,
        api_base_url: str = "https://api.github.com",
        mutation_min_interval_ms: int = 1000,
        retry_respect_retry_after: bool = True,
        retry_jitter_mode: str = "full_jitter",
        retry_max_backoff_seconds: int = 300,
        poll_use_conditional_requests: bool = True,
        poll_etag_ttl_seconds: int = 300,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.token = (token or os.getenv("GITHUB_TOKEN", "")).strip()
        self.api_base_url = api_base_url.rstrip("/")
        self.repo_slug = self._infer_repo_slug(self.repo_path)
        self._viewer_login: str | None = None
        self.mutation_min_interval_ms = max(0, int(mutation_min_interval_ms))
        self.retry_respect_retry_after = bool(retry_respect_retry_after)
        self.retry_jitter_mode = str(retry_jitter_mode or "full_jitter").strip().lower()
        if self.retry_jitter_mode not in {"full_jitter", "none"}:
            self.retry_jitter_mode = "full_jitter"
        self.retry_max_backoff_seconds = max(5, int(retry_max_backoff_seconds))
        self.poll_use_conditional_requests = bool(poll_use_conditional_requests)
        self.poll_etag_ttl_seconds = max(60, int(poll_etag_ttl_seconds))
        self._mutation_lock = threading.Lock()
        self._last_mutation_at = 0.0
        self._etag_cache: dict[str, tuple[str, Any, float]] = {}
        self._last_error_class = ""
        self._last_error_reason = ""
        self._request_metrics_lock = threading.Lock()
        self._request_counts_by_key: dict[str, int] = {}
        self._request_duration_ms_by_key: dict[str, int] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.repo_slug)

    def get_last_error(self) -> tuple[str, str]:
        return self._last_error_class, self._last_error_reason

    def request_metrics_snapshot(self) -> dict[str, dict[str, int]]:
        with self._request_metrics_lock:
            return {
                "counts": dict(self._request_counts_by_key),
                "durations_ms": dict(self._request_duration_ms_by_key),
            }

    def _set_last_error(self, *, error_class: str, reason: str) -> None:
        self._last_error_class = str(error_class or "").strip()
        self._last_error_reason = str(reason or "").strip()[:500]

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
        trusted = {actor.strip().lower() for actor in trusted_actors if actor.strip()}
        request_limit = max(1, int(limit))
        per_page = min(max(20, request_limit), 100)
        page = 1
        out: list[HealerIssue] = []
        while len(out) < request_limit:
            payload = self._request_json(
                f"/repos/{self.repo_slug}/issues?state=open&page={page}&per_page={per_page}"
                + (f"&labels={quote(labels_query)}" if labels_query else "")
            )
            items = payload if isinstance(payload, list) else []
            if not items:
                break
            for item in items:
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
                out.append(
                    HealerIssue(
                        issue_id=str(item.get("number")),
                        repo=self.repo_slug,
                        title=str(item.get("title") or ""),
                        body=str(item.get("body") or ""),
                        author=author,
                        labels=label_names,
                        priority=self._priority_from_labels(label_names),
                        html_url=str(item.get("html_url") or ""),
                        created_at=str(item.get("created_at") or ""),
                        updated_at=str(item.get("updated_at") or ""),
                    )
                )
            if len(items) < per_page:
                break
            page += 1
        out.sort(key=self._issue_sort_key)
        return out[:request_limit]

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
        target = (label or "").strip().lower()
        normalized = {entry.lower() for entry in labels if entry}
        return target in normalized

    def get_issue(self, *, issue_id: str) -> dict[str, Any] | None:
        if not self.enabled or not issue_id.strip():
            return None
        payload = self._request_json(f"/repos/{self.repo_slug}/issues/{quote(issue_id.strip())}")
        if not isinstance(payload, dict):
            return None
        number = int(payload.get("number") or 0)
        if number <= 0:
            return None
        labels = [
            str((entry or {}).get("name") or "").strip()
            for entry in (payload.get("labels") or [])
            if isinstance(entry, dict)
        ]
        return {
            "issue_id": str(number),
            "state": str(payload.get("state") or ""),
            "title": str(payload.get("title") or ""),
            "body": str(payload.get("body") or ""),
            "labels": labels,
        }

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

    def add_issue_reaction(self, *, issue_id: str, reaction: str = "eyes") -> bool:
        if not self.enabled or not issue_id.strip() or not reaction.strip():
            return False
        payload = self._request_json(
            f"/repos/{self.repo_slug}/issues/{quote(issue_id.strip())}/reactions",
            method="POST",
            body={"content": reaction.strip()},
        )
        return isinstance(payload, dict) and "id" in payload

    def add_issue_comment(self, *, issue_id: str, body: str) -> bool:
        if not self.enabled or not issue_id.strip() or not body.strip():
            return False
        payload = self._request_json(
            f"/repos/{self.repo_slug}/issues/{quote(issue_id.strip())}/comments",
            method="POST",
            body={"body": body},
        )
        return isinstance(payload, dict) and "id" in payload

    def close_issue(self, *, issue_id: str) -> bool:
        if not self.enabled or not issue_id.strip():
            return False
        payload = self._request_json(
            f"/repos/{self.repo_slug}/issues/{quote(issue_id.strip())}",
            method="PATCH",
            body={"state": "closed"},
        )
        return isinstance(payload, dict) and str(payload.get("state") or "").lower() == "closed"

    def add_issue_label(self, *, issue_id: str, label: str) -> bool:
        normalized_issue = str(issue_id or "").strip()
        normalized_label = str(label or "").strip()
        if not self.enabled or not normalized_issue or not normalized_label:
            return False
        payload = self._request_json(
            f"/repos/{self.repo_slug}/issues/{quote(normalized_issue)}/labels",
            method="POST",
            body={"labels": [normalized_label]},
        )
        if not isinstance(payload, list):
            return False
        labels = {
            str((entry or {}).get("name") or "").strip().lower()
            for entry in payload
            if isinstance(entry, dict)
        }
        return normalized_label.lower() in labels

    def remove_issue_label(self, *, issue_id: str, label: str) -> bool:
        normalized_issue = str(issue_id or "").strip()
        normalized_label = str(label or "").strip()
        if not self.enabled or not normalized_issue or not normalized_label:
            return False
        payload = self._request_json(
            f"/repos/{self.repo_slug}/issues/{quote(normalized_issue)}/labels/{quote(normalized_label, safe='')}",
            method="DELETE",
        )
        return isinstance(payload, list)

    def find_pr_for_issue(self, *, issue_id: str, limit: int = 100) -> PullRequestResult | None:
        if not self.enabled or not issue_id.strip():
            return None
        query = f'repo:{self.repo_slug} is:pr "issue #{issue_id.strip()}"'
        payload = self._request_json(
            f"/search/issues?q={quote(query)}&per_page={int(max(1, min(limit, 20)))}"
        )
        if not isinstance(payload, dict):
            return None
        items = payload.get("items")
        if not isinstance(items, list):
            return None
        matches: list[tuple[str, PullRequestResult]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            pr_number = int(item.get("number") or 0)
            if pr_number <= 0:
                continue
            state = str(item.get("state") or "").strip().lower()
            html_url = str(item.get("html_url") or "")
            updated_at = str(item.get("closed_at") or item.get("updated_at") or "")
            if state == "closed":
                details = self.get_pr_details(pr_number=pr_number)
                if details is None:
                    continue
                matches.append(
                    (
                        updated_at or str(details.updated_at or ""),
                        PullRequestResult(
                            number=pr_number,
                            state=details.state,
                            html_url=details.html_url or html_url,
                        ),
                    )
                )
                continue
            matches.append(
                (
                    updated_at,
                    PullRequestResult(
                        number=pr_number,
                        state=state or "open",
                        html_url=html_url,
                    ),
                )
            )
        if not matches:
            return None
        matches.sort(key=lambda item: item[0], reverse=True)
        return matches[0][1]

    def open_or_update_pr(
        self,
        *,
        issue_id: str,
        branch: str,
        title: str,
        body: str,
        base: str = "main",
    ) -> PullRequestResult | None:
        if not self.token:
            self._set_last_error(
                error_class="github_auth_missing",
                reason="GITHUB_TOKEN is missing; cannot create or update pull requests.",
            )
            return None
        if not self.repo_slug:
            self._set_last_error(
                error_class="github_repo_unconfigured",
                reason="Repository slug is missing; cannot create or update pull requests.",
            )
            return None

        existing = self._request_json(
            f"/repos/{self.repo_slug}/pulls?state=open&head={quote(self.repo_slug.split('/')[0] + ':' + branch)}"
        )
        if isinstance(existing, list) and existing:
            pr = existing[0] if isinstance(existing[0], dict) else {}
            pr_number = int(pr.get("number") or 0)
            if pr_number <= 0:
                self._set_last_error(
                    error_class="github_api_error",
                    reason="GitHub returned an open-PR payload without a valid PR number.",
                )
                return None
            return PullRequestResult(
                number=pr_number,
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
            self._set_last_error(
                error_class=self._last_error_class or "github_api_error",
                reason=self._last_error_reason or "GitHub returned an unexpected response while opening a PR.",
            )
            return None
        pr_number = int(payload.get("number") or 0)
        if pr_number <= 0:
            message = str(payload.get("message") or "").strip()
            self._set_last_error(
                error_class="github_api_error",
                reason=message or "GitHub did not return a valid PR number while opening a PR.",
            )
            return None
        return PullRequestResult(
            number=pr_number,
            state=str(payload.get("state") or "open"),
            html_url=str(payload.get("html_url") or ""),
        )

    def get_pr_state(self, *, pr_number: int) -> str:
        details = self.get_pr_details(pr_number=pr_number)
        return details.state if details is not None else ""

    def get_pr_details(self, *, pr_number: int) -> PullRequestDetails | None:
        if not self.enabled or pr_number <= 0:
            return None
        payload = self._request_json(f"/repos/{self.repo_slug}/pulls/{int(pr_number)}")
        if not isinstance(payload, dict):
            return None
        number = int(payload.get("number") or 0)
        if number <= 0:
            return None
        return PullRequestDetails(
            number=number,
            state=self._pr_state_from_payload(payload),
            html_url=str(payload.get("html_url") or ""),
            mergeable_state=str(payload.get("mergeable_state") or "").strip().lower(),
            author=str((payload.get("user") or {}).get("login") or "").strip(),
            head_ref=str(payload.get("head", {}).get("ref", "") or "").strip(),
            updated_at=str(payload.get("updated_at") or "").strip(),
        )

    def add_pr_comment(self, *, pr_number: int, body: str) -> bool:
        if not self.enabled or pr_number <= 0 or not body.strip():
            return False
        payload = self._request_json(
            f"/repos/{self.repo_slug}/issues/{int(pr_number)}/comments",
            method="POST",
            body={"body": body},
        )
        return isinstance(payload, dict) and "id" in payload

    def approve_pr(self, *, pr_number: int, body: str = "") -> bool:
        if not self.enabled or pr_number <= 0:
            return False
        payload = self._request_json(
            f"/repos/{self.repo_slug}/pulls/{int(pr_number)}/reviews",
            method="POST",
            body={
                "event": "APPROVE",
                "body": body.strip(),
            },
        )
        return isinstance(payload, dict) and "id" in payload

    def merge_pr(self, *, pr_number: int, merge_method: str = "squash") -> bool:
        if not self.enabled or pr_number <= 0:
            return False
        method = merge_method.strip().lower() or "squash"
        payload = self._request_json(
            f"/repos/{self.repo_slug}/pulls/{int(pr_number)}/merge",
            method="PUT",
            body={"merge_method": method},
        )
        return bool(payload.get("merged")) if isinstance(payload, dict) else False

    def close_pr(self, *, pr_number: int, comment: str = "") -> bool:
        if not self.enabled or pr_number <= 0:
            return False
        if comment.strip():
            self.add_pr_comment(pr_number=pr_number, body=comment)
        payload = self._request_json(
            f"/repos/{self.repo_slug}/pulls/{int(pr_number)}",
            method="PATCH",
            body={"state": "closed"},
        )
        return isinstance(payload, dict) and str(payload.get("state") or "") == "closed"

    def delete_branch(self, *, branch: str) -> bool:
        normalized = str(branch or "").strip().strip("/")
        if not self.enabled or not normalized:
            return False
        payload = self._request_json(
            f"/repos/{self.repo_slug}/git/refs/heads/{quote(normalized, safe='')}",
            method="DELETE",
        )
        return payload == {} or payload is None

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

    def _pr_state_from_payload(self, payload: dict[str, Any]) -> str:
        if bool(payload.get("merged")) or str(payload.get("merged_at") or "").strip():
            return "merged"
        state = str(payload.get("state") or "").strip().lower()
        if state == "closed":
            return "closed"
        mergeable_state = str(payload.get("mergeable_state") or "").strip().lower()
        if mergeable_state == "dirty":
            return "conflict"
        return state

    def _request_json(self, path: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
        self._last_error_class = ""
        self._last_error_reason = ""
        method_upper = method.strip().upper() or "GET"
        url = f"{self.api_base_url}{path}"
        started_at = time.monotonic()
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        is_mutating = method_upper in {"POST", "PUT", "PATCH", "DELETE"}
        max_attempts = 3 if is_mutating else 4
        use_conditional = (
            method_upper == "GET"
            and body is None
            and self.poll_use_conditional_requests
        )
        cache_key = f"{method_upper}:{path}"
        cached_etag = ""
        cached_payload: Any = None
        if use_conditional:
            cached = self._etag_cache.get(cache_key)
            if cached is not None:
                etag, payload, cached_at = cached
                if (time.monotonic() - float(cached_at)) <= float(self.poll_etag_ttl_seconds):
                    cached_etag = etag
                    cached_payload = payload
                else:
                    self._etag_cache.pop(cache_key, None)

        for attempt in range(max_attempts):
            if is_mutating:
                self._enforce_mutation_spacing()
            req = Request(url, method=method_upper, data=data)
            req.add_header("Accept", "application/vnd.github+json")
            req.add_header("User-Agent", "apple-flow-healer")
            req.add_header("Authorization", f"Bearer {self.token}")
            if data is not None:
                req.add_header("Content-Type", "application/json")
            if use_conditional and cached_etag:
                req.add_header("If-None-Match", cached_etag)
            try:
                with urlopen(req, timeout=20) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    payload = json.loads(raw) if raw else {}
                    if use_conditional:
                        etag = str(resp.headers.get("ETag") or "").strip()
                        if etag:
                            self._etag_cache[cache_key] = (etag, payload, time.monotonic())
                    self._record_request_metric(method=method_upper, path=path, status=str(resp.status), started_at=started_at)
                    return payload
            except HTTPError as exc:
                if use_conditional and exc.code == 304 and cached_payload is not None:
                    self._record_request_metric(method=method_upper, path=path, status="304", started_at=started_at)
                    return cached_payload
                reason = self._http_error_reason(exc)
                if self._is_missing_label_delete_noop(
                    method=method_upper,
                    path=path,
                    status_code=int(exc.code),
                    reason=reason,
                ):
                    # Deleting a label that does not exist is idempotently successful.
                    self._record_request_metric(method=method_upper, path=path, status=str(exc.code), started_at=started_at)
                    return []
                is_rate_limited = self._is_rate_limited_error(exc=exc, reason=reason)
                self._last_error_class = "github_rate_limited" if is_rate_limited else "github_api_error"
                self._last_error_reason = reason[:500]
                retryable = exc.code in {403, 429, 500, 502, 503, 504}
                if retryable and attempt < (max_attempts - 1):
                    self._record_request_metric(method=method_upper, path=path, status=str(exc.code), started_at=started_at)
                    delay = self._retry_delay_seconds(attempt=attempt, headers=dict(exc.headers or {}))
                    logger.warning(
                        "GitHub API %s %s failed (status=%s). Retrying in %.2fs (%d/%d).",
                        method_upper,
                        path,
                        exc.code,
                        delay,
                        attempt + 1,
                        max_attempts,
                    )
                    time.sleep(delay)
                    started_at = time.monotonic()
                    continue
                self._record_request_metric(method=method_upper, path=path, status=str(exc.code), started_at=started_at)
                logger.warning("GitHub API %s %s failed: %s", method_upper, path, reason)
                return {}
            except URLError as exc:
                self._last_error_class = "github_network_error"
                self._last_error_reason = str(exc)[:500]
                if attempt < (max_attempts - 1):
                    self._record_request_metric(method=method_upper, path=path, status="network_error", started_at=started_at)
                    delay = self._retry_delay_seconds(attempt=attempt, headers={})
                    logger.warning(
                        "GitHub API network error for %s %s: %s. Retrying in %.2fs (%d/%d).",
                        method_upper,
                        path,
                        exc,
                        delay,
                        attempt + 1,
                        max_attempts,
                    )
                    time.sleep(delay)
                    started_at = time.monotonic()
                    continue
                self._record_request_metric(method=method_upper, path=path, status="network_error", started_at=started_at)
                logger.warning("GitHub API network error for %s %s: %s", method_upper, path, exc)
                return {}
            except json.JSONDecodeError:
                self._last_error_class = "github_parse_error"
                self._last_error_reason = f"GitHub API returned non-JSON response for {method_upper} {path}"
                self._record_request_metric(method=method_upper, path=path, status="parse_error", started_at=started_at)
                logger.warning(self._last_error_reason)
                return {}
        return {}

    @staticmethod
    def _is_missing_label_delete_noop(*, method: str, path: str, status_code: int, reason: str) -> bool:
        if method != "DELETE" or status_code != 404:
            return False
        if not re.search(r"/issues/[^/]+/labels/[^/]+$", path or ""):
            return False
        return "label does not exist" in (reason or "").lower()

    def _record_request_metric(self, *, method: str, path: str, status: str, started_at: float) -> None:
        normalized_path = self._normalize_metric_path(path)
        key = f"{method} {normalized_path} {status}"
        elapsed_ms = max(0, int((time.monotonic() - started_at) * 1000.0))
        with self._request_metrics_lock:
            self._request_counts_by_key[key] = self._request_counts_by_key.get(key, 0) + 1
            self._request_duration_ms_by_key[key] = self._request_duration_ms_by_key.get(key, 0) + elapsed_ms

    @staticmethod
    def _normalize_metric_path(path: str) -> str:
        normalized = re.sub(r"/pulls/\d+", "/pulls/:id", path)
        normalized = re.sub(r"/issues/\d+", "/issues/:id", normalized)
        normalized = re.sub(r"/comments/\d+", "/comments/:id", normalized)
        return normalized

    def _enforce_mutation_spacing(self) -> None:
        if self.mutation_min_interval_ms <= 0:
            return
        with self._mutation_lock:
            now = time.monotonic()
            min_interval = float(self.mutation_min_interval_ms) / 1000.0
            wait_seconds = (self._last_mutation_at + min_interval) - now
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            self._last_mutation_at = time.monotonic()

    def _retry_delay_seconds(self, *, attempt: int, headers: dict[str, Any]) -> float:
        if self.retry_respect_retry_after:
            retry_after = self._parse_retry_after(headers)
            if retry_after is not None:
                return retry_after
        capped = min(self.retry_max_backoff_seconds, max(1, 2 ** max(0, int(attempt))))
        if self.retry_jitter_mode == "none":
            return float(capped)
        return random.uniform(0.0, float(capped))

    @staticmethod
    def _parse_retry_after(headers: dict[str, Any]) -> float | None:
        raw = str(headers.get("Retry-After") or "").strip()
        if not raw:
            return None
        if raw.isdigit():
            return max(0.0, float(raw))
        try:
            parsed = parsedate_to_datetime(raw)
        except Exception:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delay = (parsed - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, float(delay))

    @staticmethod
    def _http_error_reason(exc: HTTPError) -> str:
        payload = ""
        try:
            payload = exc.read().decode("utf-8", errors="replace")
        except Exception:
            payload = ""
        payload = payload.strip()
        if payload:
            return f"{exc} body={payload[:280]}"
        return str(exc)

    @staticmethod
    def _is_rate_limited_error(*, exc: HTTPError, reason: str) -> bool:
        lowered = (reason or "").lower()
        if exc.code == 429:
            return True
        if exc.code == 403 and ("rate limit" in lowered or "secondary rate limit" in lowered):
            return True
        return False

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
    def _issue_sort_key(issue: HealerIssue) -> tuple[int, str, str, int]:
        created = str(issue.created_at or "").strip()
        updated = str(issue.updated_at or "").strip()
        timestamp = created or updated or "9999-12-31T23:59:59Z"
        try:
            issue_number = int(issue.issue_id)
        except ValueError:
            issue_number = 0
        return (int(issue.priority), timestamp, updated, issue_number)

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
