from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import random
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger("apple_flow.healer_tracker")

_ALLOWED_ARTIFACT_SUFFIXES = {
    ".gif",
    ".jpeg",
    ".jpg",
    ".json",
    ".jsonl",
    ".log",
    ".png",
    ".txt",
    ".webp",
}
_MAX_ARTIFACT_BYTES = 5 * 1024 * 1024
_ARTIFACT_CONTENT_TYPES = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".log": "text/plain",
    ".png": "image/png",
    ".txt": "text/plain",
    ".webp": "image/webp",
}


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
    head_sha: str = ""
    updated_at: str = ""


@dataclass(slots=True, frozen=True)
class TrackerRequestMetric:
    method: str
    path: str
    status: str
    duration_ms: int


@dataclass(slots=True, frozen=True)
class PublishedArtifact:
    name: str
    branch: str
    remote_path: str
    html_url: str
    download_url: str
    markdown_url: str
    content_type: str
    sha: str = ""


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
            updated_payload = self._request_json(
                f"/repos/{self.repo_slug}/pulls/{pr_number}",
                method="PATCH",
                body={
                    "title": title,
                    "body": body,
                    "base": base,
                },
            )
            payload = updated_payload if isinstance(updated_payload, dict) else pr
            number = int(payload.get("number") or pr_number)
            if number <= 0:
                self._set_last_error(
                    error_class=self._last_error_class or "github_api_error",
                    reason=self._last_error_reason or "GitHub returned an unexpected response while updating a PR.",
                )
                return None
            return PullRequestResult(
                number=number,
                state=str(payload.get("state") or pr.get("state") or "open"),
                html_url=str(payload.get("html_url") or pr.get("html_url") or ""),
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

    def publish_artifact_files(
        self,
        *,
        issue_id: str,
        files: list[str | Path],
        branch: str = "flow-healer-artifacts",
        source_branch: str = "main",
        run_key: str = "latest",
        retention_days: int = 30,
        metadata: dict[str, Any] | None = None,
        max_file_bytes: int | None = None,
        max_run_bytes: int | None = None,
        max_branch_bytes: int | None = None,
    ) -> list[PublishedArtifact]:
        normalized_issue = self._sanitize_artifact_segment(issue_id)
        normalized_branch = str(branch or "").strip().strip("/")
        normalized_source_branch = str(source_branch or "").strip().strip("/")
        normalized_run_key = self._sanitize_artifact_segment(run_key or "latest")
        if not self.enabled or not normalized_issue or not normalized_branch or not normalized_source_branch:
            return []
        if not self._ensure_branch_exists(branch=normalized_branch, source_branch=normalized_source_branch):
            return []
        self._prune_expired_artifact_runs(
            branch=normalized_branch,
            issue_id=normalized_issue,
        )
        file_size_limit = max(1, int(max_file_bytes or _MAX_ARTIFACT_BYTES))
        run_size_limit = max(0, int(max_run_bytes or 0))
        branch_size_limit = max(0, int(max_branch_bytes or 0))
        artifact_candidates: list[tuple[Path, str, int]] = []
        run_total_bytes = 0
        published: list[PublishedArtifact] = []
        for raw_file in files:
            local_path = Path(raw_file).expanduser()
            if not local_path.exists() or not local_path.is_file():
                logger.warning("Skipping missing artifact publish candidate: %s", local_path)
                continue
            if not self._artifact_file_is_publishable(local_path, max_bytes=file_size_limit):
                logger.warning("Skipping unsupported artifact publish candidate: %s", local_path)
                continue
            artifact_name = self._sanitize_artifact_filename(local_path.name)
            if not artifact_name:
                logger.warning("Skipping artifact with unsupported name: %s", local_path)
                continue
            artifact_size = int(local_path.stat().st_size)
            run_total_bytes += artifact_size
            artifact_candidates.append((local_path, artifact_name, artifact_size))
        if run_size_limit and run_total_bytes > run_size_limit:
            logger.warning(
                "Artifact run for issue #%s exceeds configured run-size guardrail (%s > %s bytes).",
                normalized_issue,
                run_total_bytes,
                run_size_limit,
            )
        if branch_size_limit:
            projected_branch_bytes = self._artifact_branch_total_bytes(branch=normalized_branch) + run_total_bytes
            if projected_branch_bytes > branch_size_limit:
                logger.warning(
                    "Artifact branch %s exceeds configured size guardrail (%s > %s bytes).",
                    normalized_branch,
                    projected_branch_bytes,
                    branch_size_limit,
                )
        for local_path, artifact_name, _artifact_size in artifact_candidates:
            remote_path = (
                f"flow-healer/evidence/issue-{normalized_issue}/{normalized_run_key}/{artifact_name}"
            )
            existing_sha = self._get_content_sha(branch=normalized_branch, remote_path=remote_path)
            encoded_content = base64.b64encode(local_path.read_bytes()).decode("ascii")
            payload: dict[str, Any] = {
                "message": f"chore: publish flow-healer evidence for issue #{normalized_issue}",
                "content": encoded_content,
                "branch": normalized_branch,
            }
            if existing_sha:
                payload["sha"] = existing_sha
            response = self._request_json(
                f"/repos/{self.repo_slug}/contents/{quote(remote_path)}",
                method="PUT",
                body=payload,
            )
            if not isinstance(response, dict):
                continue
            content = response.get("content")
            if not isinstance(content, dict):
                continue
            published_path = str(content.get("path") or remote_path).strip() or remote_path
            sha = str(content.get("sha") or "").strip()
            html_url = self._artifact_blob_url(branch=normalized_branch, remote_path=published_path)
            download_url = str(content.get("download_url") or "").strip() or self._artifact_download_url(
                branch=normalized_branch,
                remote_path=published_path,
            )
            published.append(
                PublishedArtifact(
                    name=artifact_name,
                    branch=normalized_branch,
                    remote_path=published_path,
                    html_url=html_url,
                    download_url=download_url,
                    markdown_url=download_url,
                    content_type=self._artifact_content_type(artifact_name),
                    sha=sha,
                )
            )
        metadata_payload = dict(metadata or {})
        metadata_payload["issue_id"] = normalized_issue
        metadata_payload.setdefault("attempt_id", normalized_run_key)
        metadata_payload["run_key"] = normalized_run_key
        metadata_payload["generated_at"] = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        metadata_payload["retention_until"] = (
            datetime.now(tz=UTC) + timedelta(days=max(1, int(retention_days or 30)))
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        if published:
            metadata_payload["artifacts"] = [
                {"name": artifact.name, "remote_path": artifact.remote_path, "content_type": artifact.content_type}
                for artifact in published
            ]
        meta_remote_path = f"flow-healer/evidence/issue-{normalized_issue}/{normalized_run_key}/_meta.json"
        published_meta = self._publish_artifact_content(
            branch=normalized_branch,
            issue_id=normalized_issue,
            remote_path=meta_remote_path,
            content=json.dumps(metadata_payload, sort_keys=True, indent=2).encode("utf-8"),
        )
        if published_meta is not None:
            published.append(published_meta)
        return published

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
            head_sha=str(payload.get("head", {}).get("sha", "") or "").strip(),
            updated_at=str(payload.get("updated_at") or "").strip(),
        )

    def get_pr_ci_status_summary(self, *, pr_number: int, head_sha: str = "") -> dict[str, Any]:
        if not self.enabled or pr_number <= 0:
            return {}
        resolved_head_sha = str(head_sha or "").strip()
        if not resolved_head_sha:
            details = self.get_pr_details(pr_number=pr_number)
            if details is None:
                return {}
            resolved_head_sha = str(details.head_sha or "").strip()
        if not resolved_head_sha:
            return {}

        check_runs_payload = self._request_json(
            f"/repos/{self.repo_slug}/commits/{quote(resolved_head_sha, safe='')}/check-runs?per_page=100"
        )
        status_payload = self._request_json(
            f"/repos/{self.repo_slug}/commits/{quote(resolved_head_sha, safe='')}/status"
        )
        workflow_runs_payload = self._request_json(
            f"/repos/{self.repo_slug}/actions/runs?head_sha={quote(resolved_head_sha, safe='')}&per_page=100"
        )

        check_runs_summary = self._summarize_check_runs(check_runs_payload)
        status_checks_summary = self._summarize_status_checks(status_payload)
        workflow_runs_summary = self._summarize_workflow_runs(workflow_runs_payload)
        overall_state = self._derive_ci_overall_state(
            check_runs=check_runs_summary,
            status_checks=status_checks_summary,
            workflow_runs=workflow_runs_summary,
        )
        return {
            "head_sha": resolved_head_sha,
            "overall_state": overall_state,
            "check_runs": check_runs_summary["counts"],
            "status_checks": status_checks_summary["counts"],
            "workflow_runs": workflow_runs_summary["counts"],
            "failure_buckets": sorted(
                {
                    *check_runs_summary["failure_buckets"],
                    *status_checks_summary["failure_buckets"],
                    *workflow_runs_summary["failure_buckets"],
                }
            ),
            "pending_buckets": sorted(
                {
                    *check_runs_summary["pending_buckets"],
                    *status_checks_summary["pending_buckets"],
                    *workflow_runs_summary["pending_buckets"],
                }
            ),
            "failing_contexts": sorted(
                {
                    *check_runs_summary["failing_contexts"],
                    *status_checks_summary["failing_contexts"],
                    *workflow_runs_summary["failing_contexts"],
                }
            ),
            "transient_failure_contexts": sorted(
                {
                    *check_runs_summary["transient_failure_contexts"],
                    *status_checks_summary["transient_failure_contexts"],
                    *workflow_runs_summary["transient_failure_contexts"],
                }
            ),
            "deterministic_failure_contexts": sorted(
                {
                    *check_runs_summary["deterministic_failure_contexts"],
                    *status_checks_summary["deterministic_failure_contexts"],
                    *workflow_runs_summary["deterministic_failure_contexts"],
                }
            ),
            "failing_entries": self._merge_ci_entries(
                check_runs_summary["failure_entries"],
                status_checks_summary["failure_entries"],
                workflow_runs_summary["failure_entries"],
            ),
            "transient_failure_entries": self._merge_ci_entries(
                check_runs_summary["transient_failure_entries"],
                status_checks_summary["transient_failure_entries"],
                workflow_runs_summary["transient_failure_entries"],
            ),
            "deterministic_failure_entries": self._merge_ci_entries(
                check_runs_summary["deterministic_failure_entries"],
                status_checks_summary["deterministic_failure_entries"],
                workflow_runs_summary["deterministic_failure_entries"],
            ),
            "pending_contexts": sorted(
                {
                    *check_runs_summary["pending_contexts"],
                    *status_checks_summary["pending_contexts"],
                    *workflow_runs_summary["pending_contexts"],
                }
            ),
            "pending_entries": self._merge_ci_entries(
                check_runs_summary["pending_entries"],
                status_checks_summary["pending_entries"],
                workflow_runs_summary["pending_entries"],
            ),
            "updated_at": self._latest_timestamp(
                check_runs_summary["updated_at"],
                status_checks_summary["updated_at"],
                workflow_runs_summary["updated_at"],
            ),
        }

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

    def _ensure_branch_exists(self, *, branch: str, source_branch: str) -> bool:
        existing = self._request_json(
            f"/repos/{self.repo_slug}/git/ref/heads/{quote(branch, safe='')}"
        )
        if isinstance(existing, dict) and str((existing.get("object") or {}).get("sha") or "").strip():
            return True
        source = self._request_json(
            f"/repos/{self.repo_slug}/git/ref/heads/{quote(source_branch, safe='')}"
        )
        source_sha = str((source.get("object") or {}).get("sha") or "").strip() if isinstance(source, dict) else ""
        if not source_sha:
            self._set_last_error(
                error_class=self._last_error_class or "github_api_error",
                reason=self._last_error_reason or f"GitHub did not return a commit SHA for branch {source_branch}.",
            )
            return False
        created = self._request_json(
            f"/repos/{self.repo_slug}/git/refs",
            method="POST",
            body={
                "ref": f"refs/heads/{branch}",
                "sha": source_sha,
            },
        )
        return isinstance(created, dict) and str(created.get("ref") or "").strip() == f"refs/heads/{branch}"

    def _get_content_sha(self, *, branch: str, remote_path: str) -> str:
        payload = self._request_json(
            f"/repos/{self.repo_slug}/contents/{quote(remote_path)}?ref={quote(branch)}"
        )
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("sha") or "").strip()

    def _publish_artifact_content(
        self,
        *,
        branch: str,
        issue_id: str,
        remote_path: str,
        content: bytes,
    ) -> PublishedArtifact | None:
        existing_sha = self._get_content_sha(branch=branch, remote_path=remote_path)
        payload: dict[str, Any] = {
            "message": f"chore: publish flow-healer evidence for issue #{issue_id}",
            "content": base64.b64encode(content).decode("ascii"),
            "branch": branch,
        }
        if existing_sha:
            payload["sha"] = existing_sha
        response = self._request_json(
            f"/repos/{self.repo_slug}/contents/{quote(remote_path)}",
            method="PUT",
            body=payload,
        )
        if not isinstance(response, dict):
            return None
        content_payload = response.get("content")
        if not isinstance(content_payload, dict):
            return None
        published_path = str(content_payload.get("path") or remote_path).strip() or remote_path
        artifact_name = Path(published_path).name
        sha = str(content_payload.get("sha") or "").strip()
        return PublishedArtifact(
            name=artifact_name,
            branch=branch,
            remote_path=published_path,
            html_url=self._artifact_blob_url(branch=branch, remote_path=published_path),
            download_url=str(content_payload.get("download_url") or "").strip()
            or self._artifact_download_url(branch=branch, remote_path=published_path),
            markdown_url=str(content_payload.get("download_url") or "").strip()
            or self._artifact_download_url(branch=branch, remote_path=published_path),
            content_type=self._artifact_content_type(artifact_name),
            sha=sha,
        )

    def _prune_expired_artifact_runs(self, *, branch: str, issue_id: str) -> None:
        issue_root = f"flow-healer/evidence/issue-{issue_id}"
        for entry in self._list_artifact_directory(branch=branch, remote_path=issue_root):
            if str(entry.get("type") or "").strip().lower() != "dir":
                continue
            run_root = str(entry.get("path") or "").strip()
            if not run_root:
                continue
            meta_path = f"{run_root}/_meta.json"
            meta_payload = self._request_json(
                f"/repos/{self.repo_slug}/contents/{quote(meta_path)}?ref={quote(branch)}"
            )
            retention_until = self._artifact_retention_until(meta_payload)
            if retention_until is None or datetime.now(tz=UTC) < retention_until:
                continue
            for run_entry in self._list_artifact_directory(branch=branch, remote_path=run_root):
                if str(run_entry.get("type") or "").strip().lower() != "file":
                    continue
                file_path = str(run_entry.get("path") or "").strip()
                file_sha = str(run_entry.get("sha") or "").strip()
                if not file_path or not file_sha:
                    continue
                self._request_json(
                    f"/repos/{self.repo_slug}/contents/{quote(file_path)}",
                    method="DELETE",
                    body={
                        "message": f"chore: prune expired flow-healer evidence for issue #{issue_id}",
                        "sha": file_sha,
                        "branch": branch,
                    },
                )

    def _artifact_branch_total_bytes(self, *, branch: str) -> int:
        total = 0
        pending = ["flow-healer/evidence"]
        while pending:
            current = pending.pop()
            for entry in self._list_artifact_directory(branch=branch, remote_path=current):
                entry_type = str(entry.get("type") or "").strip().lower()
                entry_path = str(entry.get("path") or "").strip()
                if entry_type == "dir" and entry_path:
                    pending.append(entry_path)
                    continue
                if entry_type == "file":
                    total += int(entry.get("size") or 0)
        return total

    def _list_artifact_directory(self, *, branch: str, remote_path: str) -> list[dict[str, Any]]:
        payload = self._request_json(
            f"/repos/{self.repo_slug}/contents/{quote(remote_path)}?ref={quote(branch)}"
        )
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        return []

    @staticmethod
    def _artifact_retention_until(payload: Any) -> datetime | None:
        if not isinstance(payload, dict):
            return None
        raw_content = payload.get("content")
        if not raw_content:
            return None
        try:
            decoded = base64.b64decode(str(raw_content).encode("ascii")).decode("utf-8")
            meta = json.loads(decoded)
        except (ValueError, OSError, json.JSONDecodeError):
            return None
        raw_until = str(meta.get("retention_until") or "").strip()
        if not raw_until:
            return None
        try:
            return datetime.strptime(raw_until, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        except ValueError:
            return None

    def _artifact_blob_url(self, *, branch: str, remote_path: str) -> str:
        web_base = self._repo_web_base_url().rstrip("/")
        quoted_path = "/".join(quote(part, safe="") for part in remote_path.split("/") if part)
        return f"{web_base}/{self.repo_slug}/blob/{quote(branch, safe='')}/{quoted_path}"

    def _artifact_download_url(self, *, branch: str, remote_path: str) -> str:
        quoted_path = "/".join(quote(part, safe="") for part in remote_path.split("/") if part)
        web_base = self._repo_web_base_url().rstrip("/")
        if web_base == "https://github.com":
            return f"https://raw.githubusercontent.com/{self.repo_slug}/{quote(branch, safe='')}/{quoted_path}"
        return f"{web_base}/{self.repo_slug}/raw/{quote(branch, safe='')}/{quoted_path}"

    def _repo_web_base_url(self) -> str:
        api_base = self.api_base_url.rstrip("/")
        if api_base == "https://api.github.com":
            return "https://github.com"
        if api_base.endswith("/api/v3"):
            return api_base[: -len("/api/v3")]
        if "://" in api_base:
            scheme, rest = api_base.split("://", 1)
            if rest.startswith("api."):
                return f"{scheme}://{rest[4:]}"
        return "https://github.com"

    @staticmethod
    def _sanitize_artifact_segment(value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
        normalized = normalized.strip(".-")
        return normalized[:120]

    @staticmethod
    def _sanitize_artifact_filename(value: str) -> str:
        if not value:
            return ""
        name = Path(value).name
        if not name or name in {".", ".."}:
            return ""
        parts = name.split(".")
        if len(parts) > 1:
            stem = ".".join(parts[:-1])
            suffix = parts[-1]
            normalized_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-")
            normalized_suffix = re.sub(r"[^A-Za-z0-9]+", "", suffix).strip().lower()
            if normalized_stem and normalized_suffix:
                return f"{normalized_stem}.{normalized_suffix}"[:180]
        return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")[:180]

    @staticmethod
    def _artifact_content_type(filename: str) -> str:
        suffix = Path(filename).suffix.strip().lower()
        if suffix in _ARTIFACT_CONTENT_TYPES:
            return _ARTIFACT_CONTENT_TYPES[suffix]
        content_type, _ = mimetypes.guess_type(filename)
        return str(content_type or "application/octet-stream")

    @staticmethod
    def _artifact_file_is_publishable(path: Path, *, max_bytes: int = _MAX_ARTIFACT_BYTES) -> bool:
        suffix = path.suffix.strip().lower()
        if suffix not in _ALLOWED_ARTIFACT_SUFFIXES:
            return False
        try:
            return path.stat().st_size <= max(1, int(max_bytes))
        except OSError:
            return False

    @classmethod
    def _summarize_check_runs(cls, payload: Any) -> dict[str, Any]:
        entries = payload.get("check_runs") if isinstance(payload, dict) else []
        return cls._summarize_ci_entries(
            entries=entries if isinstance(entries, list) else [],
            name_key="name",
            status_key="status",
            conclusion_key="conclusion",
            updated_at_keys=("completed_at", "started_at"),
            pending_states={"queued", "in_progress", "pending", "requested", "waiting"},
            success_conclusions={"success"},
            neutral_conclusions={"neutral", "skipped"},
            failure_conclusions={"action_required", "cancelled", "failure", "startup_failure", "timed_out"},
            state_key="",
            source_label="check_run",
        )

    @classmethod
    def _summarize_status_checks(cls, payload: Any) -> dict[str, Any]:
        entries = payload.get("statuses") if isinstance(payload, dict) else []
        return cls._summarize_ci_entries(
            entries=entries if isinstance(entries, list) else [],
            name_key="context",
            status_key="",
            conclusion_key="",
            updated_at_keys=("updated_at", "created_at"),
            pending_states=set(),
            success_conclusions=set(),
            neutral_conclusions=set(),
            failure_conclusions=set(),
            state_key="state",
            source_label="status_check",
        )

    @classmethod
    def _summarize_workflow_runs(cls, payload: Any) -> dict[str, Any]:
        entries = payload.get("workflow_runs") if isinstance(payload, dict) else []
        return cls._summarize_ci_entries(
            entries=entries if isinstance(entries, list) else [],
            name_key="name",
            status_key="status",
            conclusion_key="conclusion",
            updated_at_keys=("updated_at", "run_started_at", "created_at"),
            pending_states={"queued", "in_progress", "pending", "requested", "waiting"},
            success_conclusions={"success"},
            neutral_conclusions={"neutral", "skipped"},
            failure_conclusions={"action_required", "cancelled", "failure", "startup_failure", "timed_out"},
            state_key="",
            source_label="workflow_run",
        )

    @classmethod
    def _summarize_ci_entries(
        cls,
        *,
        entries: list[Any],
        name_key: str,
        status_key: str,
        conclusion_key: str,
        updated_at_keys: tuple[str, ...],
        pending_states: set[str],
        success_conclusions: set[str],
        neutral_conclusions: set[str],
        failure_conclusions: set[str],
        state_key: str,
        source_label: str,
    ) -> dict[str, Any]:
        counts = {"total": 0, "success": 0, "pending": 0, "failure": 0, "neutral": 0}
        failing_contexts: list[str] = []
        pending_contexts: list[str] = []
        failure_entries: list[dict[str, str]] = []
        pending_entries: list[dict[str, str]] = []
        transient_failure_contexts: list[str] = []
        deterministic_failure_contexts: list[str] = []
        transient_failure_entries: list[dict[str, str]] = []
        deterministic_failure_entries: list[dict[str, str]] = []
        failure_buckets: set[str] = set()
        pending_buckets: set[str] = set()
        updated_values: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            counts["total"] += 1
            name = str(entry.get(name_key) or "").strip() if name_key else ""
            updated_at = ""
            for key in updated_at_keys:
                timestamp = str(entry.get(key) or "").strip()
                if timestamp:
                    updated_at = timestamp
                    updated_values.append(timestamp)
                    break
            normalized_state = ""
            if state_key:
                normalized_state = cls._normalize_status_check_state(str(entry.get(state_key) or ""))
            else:
                normalized_status = str(entry.get(status_key) or "").strip().lower() if status_key else ""
                normalized_conclusion = str(entry.get(conclusion_key) or "").strip().lower() if conclusion_key else ""
                normalized_state = cls._normalize_ci_state(
                    status=normalized_status,
                    conclusion=normalized_conclusion,
                    pending_states=pending_states,
                    success_conclusions=success_conclusions,
                    neutral_conclusions=neutral_conclusions,
                    failure_conclusions=failure_conclusions,
                )
            if normalized_state == "failure":
                counts["failure"] += 1
                if name:
                    failing_contexts.append(name)
                bucket = cls._classify_ci_failure_bucket(name)
                failure_buckets.add(bucket)
                failure_kind = cls._classify_ci_failure_kind(
                    name=name,
                    bucket=bucket,
                    source_label=source_label,
                    status=normalized_status if status_key else "",
                    conclusion=normalized_conclusion if conclusion_key else "",
                )
                failure_entry = {
                    "source": source_label,
                    "name": name,
                    "state": normalized_state,
                    "bucket": bucket,
                    "failure_kind": failure_kind,
                    "updated_at": updated_at,
                }
                failure_entries.append(failure_entry)
                if failure_kind == "transient_infra":
                    if name:
                        transient_failure_contexts.append(name)
                    transient_failure_entries.append(dict(failure_entry))
                elif failure_kind == "deterministic_code":
                    if name:
                        deterministic_failure_contexts.append(name)
                    deterministic_failure_entries.append(dict(failure_entry))
            elif normalized_state == "pending":
                counts["pending"] += 1
                if name:
                    pending_contexts.append(name)
                bucket = cls._classify_ci_failure_bucket(name)
                pending_buckets.add(bucket)
                pending_entries.append(
                    {
                        "source": source_label,
                        "name": name,
                        "state": normalized_state,
                        "bucket": bucket,
                        "updated_at": updated_at,
                    }
                )
            elif normalized_state == "success":
                counts["success"] += 1
            elif normalized_state == "neutral":
                counts["neutral"] += 1
        return {
            "counts": counts,
            "failing_contexts": failing_contexts,
            "pending_contexts": pending_contexts,
            "failure_entries": failure_entries,
            "pending_entries": pending_entries,
            "transient_failure_contexts": transient_failure_contexts,
            "deterministic_failure_contexts": deterministic_failure_contexts,
            "transient_failure_entries": transient_failure_entries,
            "deterministic_failure_entries": deterministic_failure_entries,
            "failure_buckets": sorted(failure_buckets),
            "pending_buckets": sorted(pending_buckets),
            "updated_at": cls._latest_timestamp(*updated_values),
        }

    @staticmethod
    def _classify_ci_failure_bucket(name: str) -> str:
        normalized = re.sub(r"[_/:-]+", " ", str(name or "").strip().lower())
        if not normalized:
            return "unknown"
        if any(token in normalized for token in ("flake", "flaky", "intermittent", "quarantine", "non deterministic", "non-deterministic", "retry")):
            return "flake"
        if any(token in normalized for token in ("deploy", "preview", "release", "vercel", "netlify", "render", "cloudflare", "pages")):
            return "deploy_blocked"
        if any(token in normalized for token in ("setup", "bootstrap", "install", "dependency", "dependencies", "provision", "container", "docker build", "image build")):
            return "setup"
        if any(token in normalized for token in ("typecheck", "type check", "typing", "mypy", "pyright", "tsc")):
            return "typecheck"
        if any(token in normalized for token in ("lint", "eslint", "ruff", "flake8", "format", "style")):
            return "lint"
        if any(token in normalized for token in ("test", "pytest", "unit", "integration", "e2e", "rspec", "jest", "vitest", "playwright", "mocha", "cypress")):
            return "test"
        return "unknown"

    @staticmethod
    def _classify_ci_failure_kind(
        *,
        name: str,
        bucket: str,
        source_label: str,
        status: str,
        conclusion: str,
    ) -> str:
        normalized = re.sub(r"[_/:-]+", " ", str(name or "").strip().lower())
        normalized_status = str(status or "").strip().lower()
        normalized_conclusion = str(conclusion or "").strip().lower()
        if normalized_conclusion in {"timed_out", "startup_failure"}:
            return "transient_infra"
        if normalized_conclusion == "cancelled" and source_label in {"check_run", "workflow_run"}:
            return "transient_infra"
        if normalized_status in {"requested", "waiting"}:
            return "transient_infra"
        if any(
            token in normalized
            for token in (
                "artifact upload",
                "bootstrap timeout",
                "connection reset",
                "connection refused",
                "dns",
                "network",
                "rate limit",
                "runner",
                "service unavailable",
                "timed out",
                "timeout",
            )
        ):
            return "transient_infra"
        if bucket in {"lint", "setup", "test", "typecheck"}:
            return "deterministic_code"
        return "unknown"

    @staticmethod
    def _merge_ci_entries(*entry_groups: list[dict[str, str]]) -> list[dict[str, str]]:
        merged: list[dict[str, str]] = []
        seen: set[tuple[str, str, str, str, str, str]] = set()
        for group in entry_groups:
            for entry in group:
                source = str(entry.get("source") or "").strip()
                name = str(entry.get("name") or "").strip()
                state = str(entry.get("state") or "").strip()
                bucket = str(entry.get("bucket") or "").strip()
                failure_kind = str(entry.get("failure_kind") or "").strip()
                updated_at = str(entry.get("updated_at") or "").strip()
                key = (source, name, state, bucket, failure_kind, updated_at)
                if key in seen:
                    continue
                seen.add(key)
                merged_entry = {
                    "source": source,
                    "name": name,
                    "state": state,
                    "bucket": bucket,
                    "updated_at": updated_at,
                }
                if failure_kind:
                    merged_entry["failure_kind"] = failure_kind
                merged.append(merged_entry)
        return sorted(
            merged,
            key=lambda item: (
                str(item.get("source") or ""),
                str(item.get("name") or ""),
                str(item.get("updated_at") or ""),
            ),
        )

    @staticmethod
    def _normalize_ci_state(
        *,
        status: str,
        conclusion: str,
        pending_states: set[str],
        success_conclusions: set[str],
        neutral_conclusions: set[str],
        failure_conclusions: set[str],
    ) -> str:
        if status in pending_states:
            return "pending"
        if status == "completed":
            if conclusion in success_conclusions:
                return "success"
            if conclusion in neutral_conclusions:
                return "neutral"
            if conclusion in failure_conclusions:
                return "failure"
        return "unknown"

    @staticmethod
    def _normalize_status_check_state(state: str) -> str:
        normalized = str(state or "").strip().lower()
        if normalized in {"error", "failure"}:
            return "failure"
        if normalized == "pending":
            return "pending"
        if normalized == "success":
            return "success"
        return "unknown"

    @staticmethod
    def _derive_ci_overall_state(
        *,
        check_runs: dict[str, Any],
        status_checks: dict[str, Any],
        workflow_runs: dict[str, Any],
    ) -> str:
        failure = sum(
            int(source.get("counts", {}).get("failure", 0) or 0)
            for source in (check_runs, status_checks, workflow_runs)
        )
        if failure > 0:
            return "failure"
        pending = sum(
            int(source.get("counts", {}).get("pending", 0) or 0)
            for source in (check_runs, status_checks, workflow_runs)
        )
        if pending > 0:
            return "pending"
        total = sum(
            int(source.get("counts", {}).get("total", 0) or 0)
            for source in (check_runs, status_checks, workflow_runs)
        )
        if total <= 0:
            return "unknown"
        return "success"

    @staticmethod
    def _latest_timestamp(*values: str) -> str:
        timestamps = [str(value or "").strip() for value in values if str(value or "").strip()]
        if not timestamps:
            return ""
        return max(timestamps)

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
                if self._is_expected_artifact_publish_miss(
                    method=method_upper,
                    path=path,
                    status_code=int(exc.code),
                ):
                    self._last_error_class = "github_api_error"
                    self._last_error_reason = reason[:500]
                    self._record_request_metric(method=method_upper, path=path, status=str(exc.code), started_at=started_at)
                    return {}
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

    @staticmethod
    def _is_expected_artifact_publish_miss(*, method: str, path: str, status_code: int) -> bool:
        if method != "GET" or status_code != 404:
            return False
        if re.search(r"/repos/[^/]+/[^/]+/git/ref/heads/[^/?]+$", path or ""):
            return True
        return bool(re.search(r"/repos/[^/]+/[^/]+/contents/.+\?ref=[^&]+$", path or ""))

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
