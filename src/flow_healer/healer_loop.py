from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import signal
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .config import RelaySettings
from .healer_dispatcher import HealerDispatcher
from .healer_locks import canonicalize_lock_keys, diff_paths_to_lock_keys, predict_lock_set
from .healer_memory import HealerMemoryService
from .healer_preflight import (
    HealerPreflight,
    execution_root_for_language,
    preflight_report_to_test_summary,
)
from .healer_reconciler import HealerReconciler
from .healer_reviewer import HealerReviewer
from .healer_runner import HealerRunner, _stage_workspace_changes
from .healer_scan import FlowHealerScanner
from .healer_tracker import GitHubHealerTracker, HealerIssue, PullRequestDetails, PullRequestResult
from .healer_task_spec import compile_task_spec
from .healer_triage import classify_failure_family
from .healer_verifier import HealerVerifier
from .language_strategies import UnsupportedLanguageError
from .protocols import ConnectorProtocol
from .store import SQLiteStore

logger = logging.getLogger("apple_flow.healer_loop")

_TARGETED_TEST_RE = re.compile(
    r"\btests/[A-Za-z0-9_./\-]*test[A-Za-z0-9_./\-]*\.py\b"
)
_FLOW_COMMENT_PERSONA = (
    "Professional, concise status updates in Markdown, "
    "and always sign off with '-- Flow Healer'."
)
_INFRA_FAILURE_CLASSES = {
    "connector_unavailable",
    "connector_runtime_error",
    "github_rate_limited",
    "lease_expired",
    "preflight_failed",
    "sqlite_busy",
    "subprocess_timeout_hard_kill",
    "workspace_corrupt",
}
_ALWAYS_REQUEUE_FAILURE_CLASSES = {
    "empty_diff",
    "lock_conflict",
    "lock_upgrade_conflict",
    "malformed_diff",
    "no_patch",
    "no_workspace_change",
    "patch_apply_failed",
    "push_non_fast_forward",
    "no_code_diff",
}
_STUCK_PR_STATES = {"blocked", "dirty", "has_failure", "behind"}

_FAILURE_CLASS_STRATEGY: dict[str, dict[str, object]] = {
    "tests_failed":          {"backoff_multiplier": 0.5, "feedback_hint": "Previous attempt's tests failed. Focus on the failing test output and adjust the fix."},
    "verifier_failed":       {"backoff_multiplier": 1.5, "feedback_hint": "The verifier rejected the previous fix. Address the root cause, not symptoms."},
    "push_failed":           {"backoff_multiplier": 2.0, "feedback_hint": "Push failed on last attempt, likely transient."},
    "push_non_fast_forward": {"backoff_multiplier": 1.0, "feedback_hint": "The managed issue branch diverged remotely. Refresh the branch state and retry from the latest managed base."},
    "pr_open_failed":        {"backoff_multiplier": 2.0, "feedback_hint": "Could not open PR last time."},
    "lock_upgrade_conflict": {"backoff_multiplier": 1.0, "feedback_hint": "Previous fix expanded beyond predicted scope. Keep changes narrow."},
    "preflight_failed":      {"backoff_multiplier": 1.0, "feedback_hint": "Environment preflight failed. Wait for the runtime/tooling lane to recover before retrying."},
    "generated_artifact_contamination": {"backoff_multiplier": 1.0, "feedback_hint": "Previous attempt left generated artifacts in the worktree. Clean workspace noise before retrying."},
}


def _minutes_since(timestamp_str: str) -> float:
    """Return minutes elapsed since an ISO-8601 / SQLite CURRENT_TIMESTAMP string."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return (datetime.now(tz=UTC) - dt).total_seconds() / 60.0
    except (ValueError, TypeError):
        return 0.0


@dataclass(slots=True, frozen=True)
class CircuitBreakerStatus:
    open: bool
    window: int
    attempts_considered: int
    failures: int
    failure_rate: float
    threshold: float
    cooldown_seconds: int
    cooldown_remaining_seconds: int
    last_failure_at: str


class AutonomousHealerLoop:
    def __init__(
        self,
        *,
        settings: RelaySettings,
        store: SQLiteStore,
        connector: ConnectorProtocol,
        tracker: GitHubHealerTracker | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.connector = connector
        self.repo_path = Path(settings.healer_repo_path).expanduser().resolve()
        self.worker_id = f"healer_{uuid4().hex[:8]}"

        from .healer_workspace import HealerWorkspaceManager

        self.workspace_manager = HealerWorkspaceManager(repo_path=self.repo_path)
        self.tracker = tracker or GitHubHealerTracker(repo_path=self.repo_path)
        self.dispatcher = HealerDispatcher(
            store=store,
            worker_id=self.worker_id,
            lease_seconds=max(60, int(settings.healer_poll_interval_seconds * 3)),
            max_active_issues=max(1, int(settings.healer_max_concurrent_issues)),
            overlap_scope_queue_enabled=bool(getattr(settings, "healer_overlap_scope_queue_enabled", True)),
        )
        self.runner = HealerRunner(
            connector=connector,
            timeout_seconds=settings.healer_max_wall_clock_seconds_per_issue,
            test_gate_mode=settings.healer_test_gate_mode,
            local_gate_policy=settings.healer_local_gate_policy,
            language=settings.healer_language,
            docker_image=settings.healer_docker_image,
            test_command=settings.healer_test_command,
            install_command=settings.healer_install_command,
            auto_clean_generated_artifacts=settings.healer_auto_clean_generated_artifacts,
        )
        self.verifier = HealerVerifier(connector=connector, timeout_seconds=300)
        self.reviewer = HealerReviewer(connector=connector)
        self.scanner = FlowHealerScanner(
            repo_path=self.repo_path,
            store=store,
            tracker=self.tracker,
            severity_threshold=settings.healer_scan_severity_threshold,
            max_issues_per_run=settings.healer_scan_max_issues_per_run,
            default_labels=settings.healer_scan_default_labels,
            enable_issue_creation=settings.healer_scan_enable_issue_creation,
        )
        self._last_scan_started_at = 0.0
        self.reconciler = HealerReconciler(
            store=store,
            workspace_manager=self.workspace_manager,
        )
        self.memory = HealerMemoryService(
            store=store,
            enabled=settings.healer_learning_enabled,
        )
        self.preflight = HealerPreflight(
            store=store,
            runner=self.runner,
            repo_path=self.repo_path,
        )

    @property
    def enabled(self) -> bool:
        if not self.settings.enable_autonomous_healer:
            return False
        if not self.repo_path.exists():
            logger.warning("Autonomous healer repo path does not exist: %s", self.repo_path)
            return False
        if not self.tracker.enabled:
            logger.warning("Autonomous healer disabled: missing GitHub token or origin slug.")
            return False
        return True

    async def run_forever(self, is_shutdown: Callable[[], bool]) -> None:
        if not self.enabled:
            return
        logger.info(
            "Autonomous healer loop enabled (repo=%s, mode=%s, poll=%.0fs)",
            self.repo_path,
            self.settings.healer_mode,
            self.settings.healer_poll_interval_seconds,
        )
        while not is_shutdown():
            try:
                await asyncio.to_thread(self._tick_once)
            except Exception as exc:
                logger.exception("Autonomous healer tick failed: %s", exc)
            await asyncio.sleep(max(5.0, self.settings.healer_poll_interval_seconds))

    def _tick_once(self) -> None:
        if self.store.get_state("healer_paused") == "true":
            logger.info("Autonomous healer paused via system command; skipping cycle.")
            return
        self.reconciler.reconcile()
        self._maybe_run_scan()
        self._ingest_ready_issues()
        self.preflight.refresh_all(force=False)
        active_pr_rows = self._list_active_pr_rows(include_blocked=True)
        open_pr_rows = [
            row for row in active_pr_rows if str(row.get("state") or "").strip().lower() == "pr_open"
        ]
        self._reconcile_pr_outcomes(active_prs=active_pr_rows)
        self._auto_approve_open_prs(active_prs=open_pr_rows)
        self._auto_merge_open_prs(active_prs=open_pr_rows)
        self._reconcile_pr_outcomes()
        resumed_approved = self._resume_approved_pending_prs()
        self._ingest_pr_feedback()
        breaker = self._circuit_breaker_status()
        if breaker.open and resumed_approved == 0:
            logger.warning(
                "Healer circuit breaker open; skipping this cycle. "
                "(failures=%d/%d threshold=%.2f cooldown_remaining=%ss)",
                breaker.failures,
                breaker.attempts_considered,
                breaker.threshold,
                breaker.cooldown_remaining_seconds,
            )
            return
        if self._infra_pause_active():
            pause_until = self.store.get_state("healer_infra_pause_until") or ""
            pause_reason = self.store.get_state("healer_infra_pause_reason") or ""
            logger.warning(
                "Infra safety pause active; skipping claim cycle until %s (%s).",
                pause_until,
                pause_reason,
            )
            return
        connector_health = self._connector_health_snapshot()
        self._record_connector_health(connector_health)
        if not bool(connector_health.get("available")):
            logger.warning(
                "Healer connector unavailable; skipping claim cycle. reason=%s command=%s",
                str(connector_health.get("availability_reason") or ""),
                str(connector_health.get("configured_command") or ""),
            )
            return
        processed = 0
        while processed < max(1, self.settings.healer_max_concurrent_issues):
            connector_health = self._connector_health_snapshot()
            self._record_connector_health(connector_health)
            if not bool(connector_health.get("available")):
                logger.warning(
                    "Healer connector became unavailable mid-cycle; stopping claims. reason=%s command=%s",
                    str(connector_health.get("availability_reason") or ""),
                    str(connector_health.get("configured_command") or ""),
                )
                break
            issue = self.dispatcher.claim_next_issue()
            if not issue:
                break
            self._process_claimed_issue(issue)
            self._reconcile_pr_outcomes()
            processed += 1

    def _ingest_pr_feedback(self, active_prs: list[dict[str, object]] | None = None) -> None:
        active_prs = active_prs or self._list_active_pr_rows(include_blocked=False)
        self_actor = self.tracker.viewer_login().lower()
        details_cache: dict[int, PullRequestDetails | None] = {}
        for row in active_prs:
            pr_number = int(row.get("pr_number") or 0)
            if pr_number <= 0:
                continue

            issue_id = str(row.get("issue_id") or "")
            details = self._get_pr_details_cached(pr_number=pr_number, cache=details_cache)
            if details is None:
                continue
            current_updated_at = str(details.updated_at or "").strip()
            # Skip the 3 feedback list endpoints when GitHub says the PR has not changed.
            if (
                current_updated_at
                and current_updated_at == str(row.get("pr_last_seen_updated_at") or "").strip()
            ):
                continue
            last_issue_comment_id = int(row.get("last_issue_comment_id") or 0)
            last_review_id = int(row.get("last_review_id") or 0)
            last_review_comment_id = int(row.get("last_review_comment_id") or 0)

            try:
                issue_comments = self.tracker.list_pr_comments(pr_number=pr_number)
                reviews = self.tracker.list_pr_reviews(pr_number=pr_number)
                review_comments = self.tracker.list_pr_review_comments(pr_number=pr_number)
            except Exception as exc:
                logger.warning("Failed to ingest feedback for PR #%d: %s", pr_number, exc)
                continue

            new_feedback: list[tuple[str, int, str]] = []
            max_issue_comment_id = last_issue_comment_id
            max_review_id = last_review_id
            max_review_comment_id = last_review_comment_id

            for comment in issue_comments:
                comment_id = int(comment.get("id") or 0)
                if comment_id <= max_issue_comment_id:
                    continue
                max_issue_comment_id = max(max_issue_comment_id, comment_id)
                author = str(comment.get("author") or "").strip().lower()
                body = str(comment.get("body") or "").strip()
                if comment_id > last_issue_comment_id and body and _is_actionable_feedback_author(author, self_actor):
                    new_feedback.append(
                        (str(comment.get("created_at") or ""), comment_id, f"PR comment from @{author}: {body}")
                    )

            for review in reviews:
                review_id = int(review.get("id") or 0)
                if review_id <= max_review_id:
                    continue
                max_review_id = max(max_review_id, review_id)
                author = str(review.get("author") or "").strip().lower()
                body = str(review.get("body") or "").strip()
                state = str(review.get("state") or "").strip().lower()
                if review_id > last_review_id and body and _is_actionable_feedback_author(author, self_actor):
                    label = f"PR review ({state or 'commented'}) from @{author}: {body}"
                    new_feedback.append((str(review.get("created_at") or ""), review_id, label))

            for comment in review_comments:
                comment_id = int(comment.get("id") or 0)
                if comment_id <= max_review_comment_id:
                    continue
                max_review_comment_id = max(max_review_comment_id, comment_id)
                author = str(comment.get("author") or "").strip().lower()
                body = str(comment.get("body") or "").strip()
                path = str(comment.get("path") or "").strip()
                if comment_id > last_review_comment_id and body and _is_actionable_feedback_author(author, self_actor):
                    prefix = f"Inline review comment on {path}" if path else "Inline review comment"
                    new_feedback.append((str(comment.get("created_at") or ""), comment_id, f"{prefix} from @{author}: {body}"))

            if new_feedback:
                new_feedback.sort(key=lambda item: (item[0], item[1]))
                logger.info("Detected new feedback for PR #%d (Issue #%s)", pr_number, issue_id)
                existing_feedback = str(row.get("feedback_context") or "").strip()
                rendered_feedback = "\n".join(item[2] for item in new_feedback)
                combined_feedback = "\n\n".join(part for part in [existing_feedback, rendered_feedback] if part).strip()
                self.store.set_healer_issue_state(
                    issue_id=issue_id,
                    state=str(row.get("state") or "pr_open"),
                    last_issue_comment_id=max_issue_comment_id,
                    last_review_id=max_review_id,
                    last_review_comment_id=max_review_comment_id,
                    pr_last_seen_updated_at=current_updated_at,
                    feedback_context=combined_feedback,
                    clear_lease=True,
                )
                continue

            if (
                max_issue_comment_id > last_issue_comment_id
                or max_review_id > last_review_id
                or max_review_comment_id > last_review_comment_id
            ):
                self.store.set_healer_issue_state(
                    issue_id=issue_id,
                    state=str(row.get("state") or "pr_open"),
                    last_issue_comment_id=max_issue_comment_id,
                    last_review_id=max_review_id,
                    last_review_comment_id=max_review_comment_id,
                    pr_last_seen_updated_at=current_updated_at,
                )

    def _restore_open_pr_state(self, *, issue_id: str, pr_number: int, pr_state: str = "open") -> None:
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="pr_open",
            pr_number=pr_number,
            pr_state=(pr_state or "open"),
            clear_lease=True,
        )

    def _discover_open_pr_for_issue(self, *, issue_id: str) -> PullRequestResult | None:
        try:
            pr = self.tracker.find_pr_for_issue(issue_id=issue_id)
        except Exception as exc:
            logger.warning("Failed to discover PR for issue #%s: %s", issue_id, exc)
            return None
        if pr is None:
            return None
        if str(pr.state or "").strip().lower() != "open":
            return None
        if int(pr.number or 0) <= 0:
            return None
        return pr

    def _maybe_run_scan(self) -> dict[str, object] | None:
        if not self.settings.healer_scan_enable_issue_creation:
            return None
        interval = max(5.0, float(self.settings.healer_scan_poll_interval_seconds))
        now = time.monotonic()
        if self._last_scan_started_at and (now - self._last_scan_started_at) < interval:
            return None
        self._last_scan_started_at = now
        try:
            summary = self.scanner.run_scan(dry_run=False)
            logger.info(
                "Healer scan finished (repo=%s findings=%s created=%s)",
                self.settings.repo_name,
                summary.get("findings_over_threshold"),
                len(summary.get("created_issues") or []),
            )
            return summary
        except Exception as exc:
            logger.warning("Healer scan failed for repo %s: %s", self.settings.repo_name, exc)
            return None

    def _reconcile_pr_outcomes(self, active_prs: list[dict[str, object]] | None = None) -> int:
        active_prs = active_prs or self._list_active_pr_rows(include_blocked=True)
        details_cache: dict[int, PullRequestDetails | None] = {}
        resolved = 0
        for row in active_prs:
            issue_id = str(row.get("issue_id") or "")
            if not issue_id:
                continue
            current_state = str(row.get("state") or "").strip().lower()
            current_pr_state = str(row.get("pr_state") or "").strip().lower()
            current_pr_number = int(row.get("pr_number") or 0)
            pr_number = int(row.get("pr_number") or 0)
            pr_state = ""
            mergeable_state = ""
            head_ref = ""
            if pr_number > 0:
                pr_details = self._get_pr_details_cached(pr_number=pr_number, cache=details_cache)
                if pr_details is None:
                    continue
                pr_state = pr_details.state
                mergeable_state = pr_details.mergeable_state
                head_ref = pr_details.head_ref
                pr_state, mergeable_state, refreshed = self._recheck_conflict_state(
                    pr_number=pr_number,
                    current_state=pr_state,
                    current_mergeable_state=mergeable_state,
                )
                if refreshed is not None:
                    details_cache[pr_number] = refreshed
                    head_ref = refreshed.head_ref
            else:
                discovered_pr = self.tracker.find_pr_for_issue(issue_id=issue_id)
                if discovered_pr is None:
                    continue
                pr_number = discovered_pr.number
                pr_state = discovered_pr.state.strip().lower()
                head_ref = ""

            if pr_state == "conflict":
                stuck_since = str(row.get("stuck_since") or "").strip()
                debounce_seconds = max(0, int(getattr(self.settings, "healer_conflict_requeue_debounce_seconds", 120)))
                if debounce_seconds > 0 and not stuck_since:
                    self.store.mark_pr_stuck(issue_id=issue_id, pr_number=pr_number)
                    continue
                if debounce_seconds > 0 and _minutes_since(stuck_since) < (debounce_seconds / 60.0):
                    continue
                auto_resolve = getattr(self.settings, "healer_auto_resolve_conflicts", True)
                if auto_resolve and self._attempt_conflict_resolution(issue_id=issue_id, pr_number=pr_number, row=row):
                    resolved += 1
                else:
                    auto_requeue = bool(getattr(self.settings, "healer_conflict_auto_requeue_enabled", True))
                    if auto_requeue:
                        handled = self._close_conflicted_pr_and_requeue_issue(
                            issue_id=issue_id,
                            pr_number=pr_number,
                            head_ref=head_ref,
                        )
                    else:
                        handled = self._close_conflicted_pr_and_issue(
                            issue_id=issue_id,
                            pr_number=pr_number,
                            head_ref=head_ref,
                        )
                    if not handled:
                        self._block_conflicted_pr(issue_id=issue_id, pr_number=pr_number)
                continue

            if pr_state == "closed" and current_pr_state == "conflict":
                snapshot = self.tracker.get_issue(issue_id=issue_id)
                remote_state = str((snapshot or {}).get("state") or "").strip().lower()
                if remote_state and remote_state != "open":
                    self.store.set_healer_issue_state(
                        issue_id=issue_id,
                        state="archived",
                        pr_number=pr_number,
                        pr_state="closed",
                        clear_lease=True,
                    )
                    self._cleanup_managed_remote_branch(branch=head_ref)
                    continue
                self._requeue_closed_conflicted_pr(issue_id=issue_id, pr_number=pr_number, head_ref=head_ref)
                continue

            # Stuck-PR detection: re-queue issues whose PR has been non-mergeable too long
            if mergeable_state in _STUCK_PR_STATES:
                stuck_since = str(row.get("stuck_since") or "").strip()
                timeout_minutes = getattr(self.settings, "healer_stuck_pr_timeout_minutes", 60)
                if not stuck_since:
                    self.store.mark_pr_stuck(issue_id=issue_id, pr_number=pr_number)
                elif _minutes_since(stuck_since) >= timeout_minutes:
                    self._close_and_requeue_stuck_pr(
                        issue_id=issue_id,
                        pr_number=pr_number,
                        mergeable_state=mergeable_state,
                        head_ref=head_ref,
                    )
                continue

            # If mergeable_state recovered, clear stuck_since
            if str(row.get("stuck_since") or "").strip():
                self.store.clear_pr_stuck(issue_id=issue_id)

            if pr_state != "merged":
                if pr_state and (
                    pr_state != current_pr_state
                    or current_state != "pr_open"
                    or current_pr_number != pr_number
                ):
                    self.store.set_healer_issue_state(
                        issue_id=issue_id,
                        state="pr_open",
                        pr_number=pr_number,
                        pr_state=pr_state,
                        last_failure_class="" if current_pr_state == "conflict" else None,
                        last_failure_reason="" if current_pr_state == "conflict" else None,
                    )
                continue

            close_issue_key = self._mutation_key(action="close_issue", issue_id=issue_id)
            close_issue_ok = self._run_idempotent_mutation(
                mutation_key=close_issue_key,
                action=lambda: self.tracker.close_issue(issue_id=issue_id),
            )
            if not close_issue_ok:
                logger.warning(
                    "PR #%d is merged but Flow Healer could not close issue #%s yet.",
                    pr_number,
                    issue_id,
                )
                self.store.set_healer_issue_state(
                    issue_id=issue_id,
                    state="pr_open",
                    pr_number=pr_number,
                    pr_state="merged",
                )
                continue

            self.store.set_healer_issue_state(
                issue_id=issue_id,
                state="resolved",
                pr_number=pr_number,
                pr_state="merged",
                clear_lease=True,
            )
            self._cleanup_managed_remote_branch(branch=head_ref)
            self._post_issue_status(
                issue_id=issue_id,
                body=self._format_flow_status_comment(
                    "Issue resolved",
                    "The pull request was merged into the base branch, so this issue is now complete.",
                    [
                        "Status: `resolved`",
                        f"PR: `#{pr_number}`",
                    ],
                ),
            )
            self._reset_infra_failure_streak()
            resolved += 1
        return resolved

    def _list_active_pr_rows(self, *, include_blocked: bool) -> list[dict[str, object]]:
        states = ["pr_open", "pr_pending_approval"]
        if include_blocked:
            states.append("blocked")
        return self.store.list_healer_issues(states=states, limit=100)

    def _get_pr_details_cached(
        self,
        *,
        pr_number: int,
        cache: dict[int, PullRequestDetails | None],
    ) -> PullRequestDetails | None:
        if pr_number not in cache:
            cache[pr_number] = self.tracker.get_pr_details(pr_number=pr_number)
        return cache[pr_number]

    @staticmethod
    def _is_conflict_blocked_row(row: dict[str, object], *, pr_number: int) -> bool:
        return (
            str(row.get("state") or "").strip().lower() == "blocked"
            and str(row.get("pr_state") or "").strip().lower() == "conflict"
            and int(row.get("pr_number") or 0) == pr_number
        )

    def _block_conflicted_pr(self, *, issue_id: str, pr_number: int) -> None:
        reason = f"PR #{pr_number} has merge conflicts and needs manual resolution or closure."
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="blocked",
            pr_number=pr_number,
            pr_state="conflict",
            last_failure_class="pr_conflict",
            last_failure_reason=reason[:500],
            clear_lease=True,
        )
        self._post_issue_status(
            issue_id=issue_id,
            body=self._format_flow_status_comment(
                "Merge conflict requires manual resolution",
                "This pull request is blocked on merge conflicts, so automation is paused until it is resolved or closed.",
                [
                    "Status: `blocked`",
                    f"PR: `#{pr_number}`",
                    "PR state: `conflict`",
                ],
                outro="Resolve the conflicts in that PR, or close it if you want me to queue a fresh attempt.",
            ),
        )

    def _cleanup_managed_remote_branch(self, *, branch: str) -> None:
        normalized = str(branch or "").strip()
        if not _is_managed_healer_branch(normalized):
            return
        try:
            deleted = self.tracker.delete_branch(branch=normalized)
        except Exception as exc:
            logger.warning("Failed to delete managed remote branch %s: %s", normalized, exc)
            return
        if not deleted:
            logger.warning("Managed remote branch %s could not be deleted cleanly.", normalized)

    def _close_conflicted_pr_and_requeue_issue(self, *, issue_id: str, pr_number: int, head_ref: str = "") -> bool:
        close_pr_comment = self._format_flow_status_comment(
            "Closing stale conflicted pull request",
            "This appears to be a stale-branch conflict after newer base-branch changes landed.",
            [
                "Status: `closed`",
                f"PR: `#{pr_number}`",
                "Reason: base branch moved first",
            ],
            outro="Flow Healer will retry this same issue from the latest base branch.",
        )
        close_pr_key = self._mutation_key(
            action="close_pr_conflict_requeue",
            issue_id=issue_id,
            pr_number=pr_number,
            body=close_pr_comment,
        )
        if not self._run_idempotent_mutation(
            mutation_key=close_pr_key,
            action=lambda: self.tracker.close_pr(pr_number=pr_number, comment=close_pr_comment),
        ):
            logger.warning("Failed to close conflicted PR #%d for issue #%s", pr_number, issue_id)
            return False
        self._cleanup_managed_remote_branch(branch=head_ref)

        requeue_count = self.store.increment_conflict_requeue_count(issue_id)
        max_attempts = max(1, int(getattr(self.settings, "healer_conflict_auto_requeue_max_attempts", 3)))
        if requeue_count > max_attempts:
            reason = (
                f"PR #{pr_number} hit stale-branch conflicts {requeue_count} times, "
                f"exceeding max auto-requeue attempts ({max_attempts})."
            )
            self.store.set_healer_issue_state(
                issue_id=issue_id,
                state="blocked",
                pr_number=0,
                pr_state="",
                last_failure_class="pr_conflict_retry_exhausted",
                last_failure_reason=reason[:500],
                feedback_context=reason[:500],
                clear_lease=True,
            )
            self._post_issue_status(
                issue_id=issue_id,
                body=self._format_flow_status_comment(
                    "Auto-requeue limit reached for stale conflicts",
                    "This issue exceeded the conflict retry cap and is now paused for review.",
                    [
                        "Status: `blocked`",
                        f"Previous PR: `#{pr_number}`",
                        f"Conflict retries: `{requeue_count}` / `{max_attempts}`",
                    ],
                    outro="Review scope overlap and reopen/requeue when ready.",
                ),
            )
            return True

        delay_seconds = 30
        backoff_until = (datetime.now(UTC) + timedelta(seconds=delay_seconds)).strftime("%Y-%m-%d %H:%M:%S")
        reason = (
            f"PR #{pr_number} was closed due to stale-branch conflict; "
            f"queued fresh retry {requeue_count}/{max_attempts}."
        )
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="queued",
            backoff_until=backoff_until,
            pr_number=0,
            pr_state="",
            last_failure_class="pr_conflict_requeued",
            last_failure_reason=reason[:500],
            feedback_context=reason[:500],
            clear_lease=True,
        )
        self._post_issue_status(
            issue_id=issue_id,
            body=self._format_flow_status_comment(
                "Queued fresh retry after stale conflict",
                "The conflicted PR was closed and this issue was queued for a fresh attempt on latest base.",
                [
                    "Status: `queued`",
                    f"Closed PR: `#{pr_number}`",
                    f"Conflict retries: `{requeue_count}` / `{max_attempts}`",
                    f"Next retry not before: `{backoff_until} UTC`",
                ],
            ),
        )
        return True

    def _close_conflicted_pr_and_issue(self, *, issue_id: str, pr_number: int, head_ref: str = "") -> bool:
        reason = (
            f"PR #{pr_number} hit a normal line-level merge conflict after newer changes landed on the base branch."
        )
        pr_comment = self._format_flow_status_comment(
            "Closing stale conflicted pull request",
            "This appears to be a stale-branch conflict after newer base-branch changes landed.",
            [
                "Status: `closed`",
                f"PR: `#{pr_number}`",
                "Reason: base branch moved first",
            ],
            outro=(
                "Closing this PR to keep the queue clean. If the follow-up still matters, queue a fresh issue "
                "against the latest `main`."
            ),
        )
        issue_comment = self._format_flow_status_comment(
            "Archiving issue after stale pull request conflict",
            "This is a normal line-level merge conflict caused by newer base-branch changes landing first.",
            [
                "Status: `archived`",
                f"PR: `#{pr_number}`",
                "Why: not a semantic conflict, just a stale branch",
            ],
            outro=(
                "The real fix is to start from current `main` and keep both sets of valid changes together. "
                "Open a fresh issue if that follow-up is still needed."
            ),
        )
        close_pr_key = self._mutation_key(action="close_pr", issue_id=issue_id, pr_number=pr_number, body=pr_comment)
        if not self._run_idempotent_mutation(
            mutation_key=close_pr_key,
            action=lambda: self.tracker.close_pr(pr_number=pr_number, comment=pr_comment),
        ):
            logger.warning("Failed to close conflicted PR #%d for issue #%s", pr_number, issue_id)
            return False
        self._cleanup_managed_remote_branch(branch=head_ref)
        self._post_issue_status(issue_id=issue_id, body=issue_comment)
        close_issue_key = self._mutation_key(action="close_issue", issue_id=issue_id)
        if not self._run_idempotent_mutation(
            mutation_key=close_issue_key,
            action=lambda: self.tracker.close_issue(issue_id=issue_id),
        ):
            logger.warning("Closed conflicted PR #%d but could not close issue #%s", pr_number, issue_id)
            return False
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="archived",
            pr_number=pr_number,
            pr_state="closed",
            last_failure_class="pr_conflict_superseded",
            last_failure_reason=reason[:500],
            clear_lease=True,
        )
        return True

    def _attempt_conflict_resolution(self, *, issue_id: str, pr_number: int, row: dict) -> bool:
        """Try to automatically resolve merge conflicts via rebase + AI-assisted resolution."""
        workspace_path = str(row.get("workspace_path") or "").strip()
        if not workspace_path or not Path(workspace_path).is_dir():
            return False
        issue_snapshot = row or {}
        if not str(issue_snapshot.get("title") or "").strip():
            issue_snapshot = self.store.get_healer_issue(issue_id) or row
        issue_title = str(issue_snapshot.get("title") or "").strip()
        issue_body = str(issue_snapshot.get("body") or "").strip()
        task_spec = compile_task_spec(issue_title=issue_title, issue_body=issue_body)
        try:
            resolved_execution = self.runner.resolve_execution(workspace=Path(workspace_path), task_spec=task_spec)
        except UnsupportedLanguageError:
            return False
        targeted_tests = _collect_targeted_tests(
            issue_body=issue_body,
            output_targets=list(task_spec.output_targets),
            workspace=Path(workspace_path),
            language=resolved_execution.language_effective,
            execution_root=resolved_execution.execution_root,
        )
        pr_details = self.tracker.get_pr_details(pr_number=pr_number)
        if pr_details is None or not pr_details.head_ref:
            return False
        head_ref = pr_details.head_ref
        repo_path = Path(self.settings.healer_repo_path).resolve()
        base_branch = self._detect_base_branch(repo_path)

        try:
            subprocess.run(
                ["git", "fetch", "origin"],
                cwd=workspace_path, capture_output=True, text=True, timeout=60,
            )
            subprocess.run(
                ["git", "checkout", head_ref],
                cwd=workspace_path, capture_output=True, text=True, timeout=30,
            )
            rebase = subprocess.run(
                ["git", "rebase", f"origin/{base_branch}"],
                cwd=workspace_path, capture_output=True, text=True, timeout=120,
            )
            if rebase.returncode == 0:
                test_summary = self.runner.validate_workspace(
                    Path(workspace_path),
                    task_spec=task_spec,
                    targeted_tests=targeted_tests,
                )
                if int(test_summary.get("failed_tests", 0)) > 0:
                    subprocess.run(["git", "rebase", "--abort"], cwd=workspace_path, capture_output=True, timeout=10)
                    return False
                push = subprocess.run(
                    ["git", "push", "--force-with-lease"],
                    cwd=workspace_path, capture_output=True, text=True, timeout=60,
                )
                if push.returncode == 0:
                    self.tracker.add_pr_comment(
                        pr_number=pr_number,
                        body=self._format_flow_status_comment(
                            "Merge conflicts resolved automatically",
                            "A clean rebase onto the base branch succeeded and validation passed.",
                            [
                                "Status: `resolved`",
                                f"PR: `#{pr_number}`",
                            ],
                        ),
                    )
                    logger.info("Issue #%s: clean rebase resolved conflicts for PR #%d", issue_id, pr_number)
                    return True
                subprocess.run(["git", "rebase", "--abort"], cwd=workspace_path, capture_output=True, timeout=10)
                return False

            # Rebase had conflicts — try AI-assisted resolution
            conflict_check = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                cwd=workspace_path, capture_output=True, text=True, timeout=30,
            )
            conflicted_files = [f.strip() for f in conflict_check.stdout.strip().splitlines() if f.strip()]
            if not conflicted_files or len(conflicted_files) > 5:
                subprocess.run(["git", "rebase", "--abort"], cwd=workspace_path, capture_output=True, timeout=10)
                return False

            thread_id = self.connector.get_or_create_thread(f"conflict-{issue_id}")
            for filepath in conflicted_files:
                full_path = Path(workspace_path) / filepath
                if not full_path.is_file():
                    subprocess.run(["git", "rebase", "--abort"], cwd=workspace_path, capture_output=True, timeout=10)
                    return False
                conflict_content = full_path.read_text(encoding="utf-8", errors="replace")
                prompt = (
                    f"Resolve the merge conflicts in this file. Return ONLY the resolved file content, "
                    f"no explanations or fences.\n\nFile: {filepath}\n\n{conflict_content}"
                )
                try:
                    resolved = self.connector.run_turn(thread_id, prompt, timeout_seconds=120)
                except Exception:
                    subprocess.run(["git", "rebase", "--abort"], cwd=workspace_path, capture_output=True, timeout=10)
                    return False
                resolved_text = resolved.strip()
                if not resolved_text or "<<<<<<<" in resolved_text or ">>>>>>>" in resolved_text:
                    subprocess.run(["git", "rebase", "--abort"], cwd=workspace_path, capture_output=True, timeout=10)
                    return False
                full_path.write_text(resolved_text, encoding="utf-8")
                subprocess.run(["git", "add", filepath], cwd=workspace_path, capture_output=True, timeout=10)

            cont = subprocess.run(
                ["git", "-c", "core.editor=true", "rebase", "--continue"],
                cwd=workspace_path, capture_output=True, text=True, timeout=60,
            )
            if cont.returncode != 0:
                subprocess.run(["git", "rebase", "--abort"], cwd=workspace_path, capture_output=True, timeout=10)
                return False

            test_summary = self.runner.validate_workspace(
                Path(workspace_path),
                task_spec=task_spec,
                targeted_tests=targeted_tests,
            )
            if int(test_summary.get("failed_tests", 0)) > 0:
                subprocess.run(
                    ["git", "rebase", "--abort"],
                    cwd=workspace_path, capture_output=True, timeout=10,
                )
                # Reset to pre-rebase state
                subprocess.run(
                    ["git", "reset", "--hard", f"origin/{head_ref}"],
                    cwd=workspace_path, capture_output=True, timeout=30,
                )
                return False

            push = subprocess.run(
                ["git", "push", "--force-with-lease"],
                cwd=workspace_path, capture_output=True, text=True, timeout=60,
            )
            if push.returncode != 0:
                subprocess.run(
                    ["git", "reset", "--hard", f"origin/{head_ref}"],
                    cwd=workspace_path, capture_output=True, timeout=30,
                )
                return False

            self.tracker.add_pr_comment(
                pr_number=pr_number,
                body=self._format_flow_status_comment(
                    "Merge conflicts resolved automatically",
                    "An AI-assisted rebase conflict resolution completed successfully and validation passed.",
                    [
                        "Status: `resolved`",
                        f"PR: `#{pr_number}`",
                    ],
                ),
            )
            logger.info("Issue #%s: AI-resolved conflicts for PR #%d", issue_id, pr_number)
            return True

        except Exception as exc:
            logger.warning("Issue #%s: conflict resolution failed: %s", issue_id, exc)
            try:
                subprocess.run(["git", "rebase", "--abort"], cwd=workspace_path, capture_output=True, timeout=10)
            except Exception:
                pass
            return False

    @staticmethod
    def _detect_base_branch(repo_path: Path) -> str:
        try:
            result = subprocess.run(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                cwd=str(repo_path), capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                ref = result.stdout.strip()
                return ref.rsplit("/", 1)[-1] if "/" in ref else ref
        except Exception:
            pass
        return "main"

    def _requeue_closed_conflicted_pr(self, *, issue_id: str, pr_number: int, head_ref: str = "") -> None:
        self._cleanup_managed_remote_branch(branch=head_ref)
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="queued",
            pr_number=0,
            pr_state="",
            clear_lease=True,
        )
        self._post_issue_status(
            issue_id=issue_id,
            body=self._format_flow_status_comment(
                "Queued a fresh retry",
                "The conflicted pull request was closed without merge, so this issue has been requeued for a clean retry.",
                [
                    "Status: `queued`",
                    f"Previous PR: `#{pr_number}`",
                ],
            ),
        )

    def _close_and_requeue_stuck_pr(self, *, issue_id: str, pr_number: int, mergeable_state: str, head_ref: str = "") -> None:
        reason = f"PR #{pr_number} has been stuck in `{mergeable_state}` state past the timeout."
        close_body = self._format_flow_status_comment(
            "Closing stale pull request",
            "This pull request has remained non-mergeable past the configured timeout.",
            [
                "Status: `closed`",
                f"PR: `#{pr_number}`",
                f"Mergeable state: `{mergeable_state}`",
            ],
            outro="Flow Healer will queue a fresh attempt from the latest base branch.",
        )
        close_pr_key = self._mutation_key(action="close_pr", issue_id=issue_id, pr_number=pr_number, body=close_body)
        self._run_idempotent_mutation(
            mutation_key=close_pr_key,
            action=lambda: self.tracker.close_pr(pr_number=pr_number, comment=close_body),
        )
        self._cleanup_managed_remote_branch(branch=head_ref)
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="queued",
            pr_number=0,
            pr_state="",
            feedback_context=reason[:500],
            clear_lease=True,
        )
        self._post_issue_status(
            issue_id=issue_id,
            body=self._format_flow_status_comment(
                "Closed stuck pull request and requeued issue",
                f"PR #{pr_number} remained non-mergeable (`{mergeable_state}`) past the configured timeout, so it was closed and this issue was requeued.",
                [
                    "Status: `queued`",
                    f"Closed PR: `#{pr_number}`",
                    f"Reason: `{mergeable_state}`",
                ],
            ),
        )

    def _auto_approve_open_prs(self, active_prs: list[dict[str, object]] | None = None) -> int:
        if not getattr(self.settings, "healer_pr_auto_approve_clean", True):
            return 0
        viewer_login = self.tracker.viewer_login().strip().lower()
        active_prs = active_prs or self.store.list_healer_issues(states=["pr_open"], limit=100)
        details_cache: dict[int, PullRequestDetails | None] = {}
        approved = 0
        for row in active_prs:
            pr_number = int(row.get("pr_number") or 0)
            if pr_number <= 0:
                continue
            details = self._get_pr_details_cached(pr_number=pr_number, cache=details_cache)
            approved += int(self._maybe_auto_approve_pr(pr_number=pr_number, viewer_login=viewer_login, details=details))
        return approved

    def _maybe_auto_approve_pr(
        self,
        *,
        pr_number: int,
        viewer_login: str | None = None,
        details: PullRequestDetails | None = None,
    ) -> bool:
        if not getattr(self.settings, "healer_pr_auto_approve_clean", True):
            return False
        details = details if details is not None else self.tracker.get_pr_details(pr_number=pr_number)
        if details is None or details.state != "open":
            return False
        if details.mergeable_state not in {"clean", "has_hooks", "unstable"}:
            return False
        reviewer = (viewer_login if viewer_login is not None else self.tracker.viewer_login()).strip().lower()
        if reviewer and details.author.strip().lower() == reviewer:
            return False
        for review in self.tracker.list_pr_reviews(pr_number=pr_number):
            author = str(review.get("author") or "").strip().lower()
            state = str(review.get("state") or "").strip().lower()
            if reviewer and author == reviewer and state == "approved":
                return False
        try:
            return self.tracker.approve_pr(
                pr_number=pr_number,
                body="Auto-approving clean PR with no merge conflicts.",
            )
        except Exception as exc:
            logger.warning("Failed to auto-approve PR #%d: %s", pr_number, exc)
            return False

    def _auto_merge_open_prs(self, active_prs: list[dict[str, object]] | None = None) -> int:
        if not getattr(self.settings, "healer_pr_auto_merge_clean", True):
            return 0
        active_prs = active_prs or self.store.list_healer_issues(states=["pr_open"], limit=100)
        details_cache: dict[int, PullRequestDetails | None] = {}
        merged = 0
        for row in active_prs:
            pr_number = int(row.get("pr_number") or 0)
            if pr_number <= 0:
                continue
            details = self._get_pr_details_cached(pr_number=pr_number, cache=details_cache)
            merged += int(self._maybe_auto_merge_pr(pr_number=pr_number, details=details))
        return merged

    def _maybe_auto_merge_pr(self, *, pr_number: int, details: PullRequestDetails | None = None) -> bool:
        if not getattr(self.settings, "healer_pr_auto_merge_clean", True):
            return False
        details = details if details is not None else self.tracker.get_pr_details(pr_number=pr_number)
        if details is None or details.state != "open":
            return False
        if details.mergeable_state not in {"clean", "has_hooks", "unstable"}:
            return False
        try:
            return self.tracker.merge_pr(
                pr_number=pr_number,
                merge_method=str(getattr(self.settings, "healer_pr_merge_method", "squash") or "squash"),
            )
        except Exception as exc:
            logger.warning("Failed to auto-merge PR #%d: %s", pr_number, exc)
            return False

    @staticmethod
    def _normalize_repo_path(value: str) -> str:
        text = (value or "").strip().replace("\\", "/")
        text = text.lstrip("./").strip("/")
        return text.lower()

    def _issue_scope_key(self, *, task_spec, prediction) -> str:
        execution_root = self._normalize_repo_path(str(getattr(task_spec, "execution_root", "") or ""))
        if execution_root:
            return f"path:{execution_root}"
        for key in canonicalize_lock_keys(list(getattr(prediction, "keys", []) or [])):
            if key.startswith(("path:", "dir:", "module:", "repo:")):
                return key
        return "repo:*"

    def _issue_dedupe_key(self, *, task_spec, scope_key: str) -> str:
        targets = [
            self._normalize_repo_path(str(path))
            for path in list(getattr(task_spec, "output_targets", ()) or [])
            if self._normalize_repo_path(str(path))
        ]
        commands = [
            re.sub(r"\s+", " ", str(command or "").strip()).lower()
            for command in list(getattr(task_spec, "validation_commands", ()) or [])
            if str(command or "").strip()
        ]
        if not targets and not commands:
            return ""
        material = "|".join(
            [
                scope_key or "repo:*",
                str(getattr(task_spec, "task_kind", "") or "").strip().lower(),
                ",".join(sorted(targets)),
                ",".join(sorted(commands)),
            ]
        )
        return hashlib.sha1(material.encode("utf-8")).hexdigest()[:24]

    def _maybe_coalesce_duplicate_issue(self, *, issue: HealerIssue, canonical_issue: dict[str, object]) -> bool:
        if not bool(getattr(self.settings, "healer_dedupe_close_duplicates", True)):
            return False
        canonical_issue_id = str(canonical_issue.get("issue_id") or "").strip()
        if not canonical_issue_id or canonical_issue_id == issue.issue_id:
            return False

        repo_slug = str(getattr(self.tracker, "repo_slug", "") or "").strip()
        canonical_ref = (
            f"[#{canonical_issue_id}](https://github.com/{repo_slug}/issues/{canonical_issue_id})"
            if repo_slug
            else f"#{canonical_issue_id}"
        )
        self._post_issue_status(
            issue_id=issue.issue_id,
            body=self._format_flow_status_comment(
                "Duplicate issue coalesced into active work item",
                "This issue overlaps an existing active issue, so it was coalesced to avoid conflicting parallel PRs.",
                [
                    "Status: `archived`",
                    f"Canonical issue: {canonical_ref}",
                ],
                outro="Follow the canonical issue for updates. Open a new issue only if scope changes materially.",
            ),
        )

        close_key = self._mutation_key(action="close_issue_duplicate", issue_id=issue.issue_id)
        if not self._run_idempotent_mutation(
            mutation_key=close_key,
            action=lambda: self.tracker.close_issue(issue_id=issue.issue_id),
        ):
            logger.warning(
                "Failed to close duplicate issue #%s (canonical=%s).",
                issue.issue_id,
                canonical_issue_id,
            )
            return False

        reason = f"Issue coalesced into active issue #{canonical_issue_id} to avoid overlap conflicts."
        self.store.set_healer_issue_state(
            issue_id=issue.issue_id,
            state="archived",
            pr_state="closed",
            last_failure_class="duplicate_superseded",
            last_failure_reason=reason[:500],
            superseded_by_issue_id=canonical_issue_id,
            clear_lease=True,
        )
        canonical_state = str(canonical_issue.get("state") or "queued").strip().lower() or "queued"
        existing_feedback = str(canonical_issue.get("feedback_context") or "").strip()
        coalesce_note = f"Coalesced duplicate issue #{issue.issue_id}: {self._clean_comment_text(issue.title, max_chars=180)}"
        merged_feedback = "\n".join(part for part in [existing_feedback, coalesce_note] if part)[:500]
        self.store.set_healer_issue_state(
            issue_id=canonical_issue_id,
            state=canonical_state,
            feedback_context=merged_feedback,
        )
        return True

    def _ingest_ready_issues(self) -> None:
        issues = self.tracker.list_ready_issues(
            required_labels=self.settings.healer_issue_required_labels,
            trusted_actors=self.settings.healer_trusted_actors,
            limit=max(10, self.settings.healer_max_concurrent_issues * 5),
        )
        for issue in issues:
            task_spec = compile_task_spec(issue_title=issue.title, issue_body=issue.body)
            prediction = predict_lock_set(issue_text=f"{issue.title}\n{issue.body}")
            scope_key = self._issue_scope_key(task_spec=task_spec, prediction=prediction)
            dedupe_key = self._issue_dedupe_key(task_spec=task_spec, scope_key=scope_key)
            existing_issue = self.store.get_healer_issue(issue.issue_id)
            self.store.upsert_healer_issue(
                issue_id=issue.issue_id,
                repo=issue.repo,
                title=issue.title,
                body=issue.body,
                author=issue.author,
                labels=issue.labels,
                priority=issue.priority,
                scope_key=scope_key,
                dedupe_key=dedupe_key,
            )
            discovered_pr = self._discover_open_pr_for_issue(issue_id=issue.issue_id)
            if existing_issue is not None:
                existing_state = str(existing_issue.get("state") or "").strip().lower()
                existing_pr_state = str(existing_issue.get("pr_state") or "").strip().lower()
                if discovered_pr is not None:
                    self._restore_open_pr_state(
                        issue_id=issue.issue_id,
                        pr_number=discovered_pr.number,
                        pr_state=discovered_pr.state,
                    )
                    continue
                if existing_state == "archived" or (
                    existing_state == "blocked" and existing_pr_state != "conflict"
                ) or (
                    existing_state == "resolved" and existing_pr_state == "closed"
                ):
                    self.store.set_healer_issue_state(
                        issue_id=issue.issue_id,
                        state="queued",
                        backoff_until="",
                        pr_state="",
                        last_failure_class="",
                        last_failure_reason="",
                        conflict_requeue_count=0,
                        superseded_by_issue_id="",
                        clear_lease=True,
                    )
            if bool(getattr(self.settings, "healer_dedupe_enabled", True)) and dedupe_key:
                canonical_issue = self.store.find_active_issue_by_dedupe_key(
                    dedupe_key=dedupe_key,
                    exclude_issue_id=issue.issue_id,
                )
                if canonical_issue is not None and self._maybe_coalesce_duplicate_issue(
                    issue=issue,
                    canonical_issue=canonical_issue,
                ):
                    continue
            if existing_issue is None:
                try:
                    self.tracker.add_issue_reaction(issue_id=issue.issue_id, reaction="eyes")
                except Exception as exc:
                    logger.warning("Failed to add reaction for issue #%s: %s", issue.issue_id, exc)

    def _resume_approved_pending_prs(self) -> int:
        pending = self.store.list_healer_issues(states=["pr_pending_approval"], limit=100)
        resumed = 0
        for row in pending:
            issue_id = str(row.get("issue_id") or "")
            if not issue_id:
                continue
            pr_number = int(row.get("pr_number") or 0)
            if not self._issue_has_approval_label(
                issue_id=issue_id,
                pr_number=pr_number,
                local_labels=row.get("labels"),
            ):
                continue
            self.store.set_healer_issue_state(
                issue_id=issue_id,
                state="queued",
                backoff_until="",
                clear_lease=True,
            )
            self._post_issue_status(
                issue_id=issue_id,
                body=self._format_flow_status_comment(
                    "Approval label detected; issue requeued",
                    "A required approval label is now present, so this issue is back in the queue.",
                    [
                        f"Status: `queued`",
                        f"Approval label found: `{self.settings.healer_pr_required_label}`",
                    ],
                ),
            )
            resumed += 1
        return resumed

    def _has_pr_approved_label(self, *, issue_id: str, pr_number: int, required_label: str) -> bool:
        if not required_label:
            return False
        try:
            if self.tracker.issue_has_label(issue_id=issue_id, label=required_label):
                return True
        except Exception:
            return False

        if pr_number <= 0:
            return False
        try:
            pr_issue = self.tracker.get_issue(issue_id=str(pr_number))
            if not isinstance(pr_issue, dict):
                return False
            pr_labels = {
                str((entry or {}).get("name") or "").strip()
                for entry in (pr_issue.get("labels") or [])
            }
            return required_label in pr_labels
        except Exception:
            return False

    def _process_claimed_issue(self, row: dict[str, object]) -> None:
        issue = HealerIssue(
            issue_id=str(row.get("issue_id") or ""),
            repo=str(row.get("repo") or ""),
            title=str(row.get("title") or ""),
            body=str(row.get("body") or ""),
            author=str(row.get("author") or ""),
            labels=list(row.get("labels") or []),  # type: ignore[arg-type]
            priority=int(row.get("priority") or 100),
            html_url="",
        )
        if not self._claim_is_actionable(issue):
            return
        logger.info("Claimed issue #%s (%s)", issue.issue_id, issue.title[:120])
        task_spec = compile_task_spec(issue_title=issue.title, issue_body=issue.body)
        prediction = predict_lock_set(issue_text=f"{issue.title}\n{issue.body}")
        scope_key = self._issue_scope_key(task_spec=task_spec, prediction=prediction)
        dedupe_key = self._issue_dedupe_key(task_spec=task_spec, scope_key=scope_key)
        self.store.set_healer_issue_state(
            issue_id=issue.issue_id,
            state="claimed",
            scope_key=scope_key,
            dedupe_key=dedupe_key,
        )
        proposed_attempt_no = max(1, int(row.get("attempt_count") or 0) + 1)
        lease_stop = threading.Event()
        lease_lost = threading.Event()
        lease_thread = threading.Thread(
            target=self._lease_heartbeat,
            args=(issue.issue_id, lease_stop, lease_lost),
            daemon=True,
        )
        lease_thread.start()
        attempt_no = 0
        attempt_id = ""
        actual_diff: list[str] = []
        test_summary: dict[str, object] = {}
        verifier_summary: dict[str, object] = {}
        failure_class = ""
        failure_reason = ""
        proposer_output_excerpt = ""
        issue_state = "claimed"
        attempt_state = "failed"
        workspace = None

        def _attempt_label() -> int:
            return max(1, attempt_no or proposed_attempt_no)

        def _abort_for_lost_lease() -> bool:
            nonlocal failure_class, failure_reason, issue_state
            if not lease_lost.is_set():
                return False
            failure_class = "lease_expired"
            failure_reason = "Lease lost during processing; aborting to avoid race."
            issue_state = self._backoff_or_fail(
                issue_id=issue.issue_id,
                attempt_no=_attempt_label(),
                failure_class=failure_class,
                failure_reason=failure_reason,
            )
            return True

        def _fail_without_attempt(*, failure_class_value: str, failure_reason_value: str) -> None:
            nonlocal failure_class, failure_reason, issue_state
            failure_class = failure_class_value
            failure_reason = failure_reason_value
            issue_state = "failed"
            self.store.set_healer_issue_state(
                issue_id=issue.issue_id,
                state="failed",
                last_failure_class=failure_class_value,
                last_failure_reason=failure_reason_value[:500],
                clear_lease=True,
            )

        try:
            try:
                resolved_execution = self.runner.resolve_execution(workspace=self.repo_path, task_spec=task_spec)
            except UnsupportedLanguageError as exc:
                _fail_without_attempt(
                    failure_class_value="unsupported_language",
                    failure_reason_value=str(exc),
                )
                return
            detected_language = resolved_execution.language_effective or resolved_execution.language_detected or ""
            preflight_execution_root = (
                resolved_execution.execution_root
                or execution_root_for_language(detected_language)
            )
            should_run_preflight = bool(preflight_execution_root) and (
                self.repo_path / preflight_execution_root
            ).is_dir()
            if detected_language and should_run_preflight:
                report = self.preflight.ensure_language_ready(
                    language=detected_language,
                    execution_root=preflight_execution_root,
                )
                if report.status != "ready":
                    failure_class = "preflight_failed"
                    failure_reason = report.summary
                    test_summary = preflight_report_to_test_summary(report)
                    logger.info(
                        "Issue #%s attempt %s blocked by %s preflight: %s",
                        issue.issue_id,
                        _attempt_label(),
                        detected_language,
                        failure_reason,
                    )
                    issue_state = self._backoff_or_fail(
                        issue_id=issue.issue_id,
                        attempt_no=_attempt_label(),
                        failure_class=failure_class,
                        failure_reason=failure_reason,
                    )
                    return
            if _abort_for_lost_lease():
                return
            try:
                workspace = self.workspace_manager.ensure_workspace(
                    issue_id=issue.issue_id,
                    title=issue.title,
                )
                self.workspace_manager.prepare_workspace(
                    workspace_path=workspace.path,
                    branch=workspace.branch,
                    base_branch=self.settings.healer_default_branch,
                )
            except Exception as exc:
                failure_class = "workspace_corrupt"
                failure_reason = f"Workspace unavailable or corrupt: {exc}"
                logger.warning(
                    "Issue #%s workspace preparation failed before attempt start: %s",
                    issue.issue_id,
                    failure_reason,
                )
                issue_state = self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=_attempt_label(),
                    failure_class=failure_class,
                    failure_reason=failure_reason,
                )
                return
            if _abort_for_lost_lease():
                return
            try:
                resolved_execution = self.runner.resolve_execution(workspace=workspace.path, task_spec=task_spec)
            except UnsupportedLanguageError as exc:
                _fail_without_attempt(
                    failure_class_value="unsupported_language",
                    failure_reason_value=str(exc),
                )
                return
            detected_language = resolved_execution.language_effective or resolved_execution.language_detected or ""
            lock_result = self.dispatcher.acquire_prediction_locks(issue_id=issue.issue_id, lock_keys=prediction.keys)
            if not lock_result.acquired:
                failure_class = "lock_conflict"
                failure_reason = lock_result.reason
                logger.info(
                    "Issue #%s blocked by prediction lock conflict (%s)",
                    issue.issue_id,
                    failure_reason,
                )
                issue_state = self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=_attempt_label(),
                    failure_class=failure_class,
                    failure_reason=failure_reason,
                )
                return
            attempt_no = self.store.increment_healer_attempt(issue.issue_id)

            attempt_id = f"hat_{uuid4().hex[:10]}"
            self.store.create_healer_attempt(
                attempt_id=attempt_id,
                issue_id=issue.issue_id,
                attempt_no=attempt_no,
                state="running",
                prediction_source=prediction.source,
                predicted_lock_set=prediction.keys,
                task_kind=task_spec.task_kind,
                output_targets=list(task_spec.output_targets),
                tool_policy=task_spec.tool_policy,
                validation_profile=task_spec.validation_profile,
            )
            self.store.set_healer_issue_state(
                issue_id=issue.issue_id,
                state="running",
                workspace_path=str(workspace.path),
                branch_name=workspace.branch,
                task_kind=task_spec.task_kind,
                output_targets=list(task_spec.output_targets),
                tool_policy=task_spec.tool_policy,
                validation_profile=task_spec.validation_profile,
                scope_key=scope_key,
                dedupe_key=dedupe_key,
            )
            logger.info(
                "Issue #%s attempt %s running in %s",
                issue.issue_id,
                attempt_no,
                workspace.branch,
            )
            self._post_issue_status(
                issue_id=issue.issue_id,
                body=self._format_flow_status_comment(
                    "Started automated fix attempt",
                    "Beginning a new automated pass for this issue.",
                    [
                        f"Attempt: `{attempt_no}`",
                        f"Branch: `{workspace.branch}`",
                        f"Task kind: `{task_spec.task_kind}`",
                        f"Execution mode: `{_execution_mode_for_task(connector=self.connector, task_spec=task_spec)}`",
                        f"Targets: `{self._clean_comment_text(', '.join(task_spec.output_targets) if task_spec.output_targets else 'inferred in code', max_chars=220)}`",
                        f"Test gate mode: `{self.runner.test_gate_mode}`",
                    ],
                ),
            )
            targeted_tests = _collect_targeted_tests(
                issue_body=issue.body,
                output_targets=list(task_spec.output_targets),
                workspace=workspace.path,
                language=resolved_execution.language_effective,
                execution_root=resolved_execution.execution_root,
            )
            learned_context = self.memory.build_prompt_context(
                issue_text=f"{issue.title}\n{issue.body}",
                predicted_lock_set=prediction.keys,
                last_failure_class=str(row.get("last_failure_class") or ""),
                task_kind=task_spec.task_kind,
                validation_profile=task_spec.validation_profile,
                output_targets=list(task_spec.output_targets),
                issue_id=issue.issue_id,
            )
            feedback_context = str(row.get("feedback_context") or "").strip()
            run_result = self.runner.run_attempt(
                issue_id=issue.issue_id,
                issue_title=issue.title,
                issue_body=issue.body,
                task_spec=task_spec,
                learned_context=learned_context,
                feedback_context=feedback_context,
                workspace=workspace.path,
                max_diff_files=self.settings.healer_max_diff_files,
                max_diff_lines=self.settings.healer_max_diff_lines,
                max_failed_tests_allowed=self.settings.healer_max_failed_tests_allowed,
                targeted_tests=targeted_tests,
            )
            actual_diff = run_result.diff_paths
            test_summary = run_result.test_summary
            proposer_output_excerpt = (run_result.proposer_output or "")[:1500]
            if not run_result.success:
                failure_class = run_result.failure_class
                failure_reason = run_result.failure_reason
                logger.info(
                    "Issue #%s attempt %s proposer/test phase failed (%s): %s",
                    issue.issue_id,
                    attempt_no,
                    failure_class,
                    failure_reason,
                )
                self._record_failure_fingerprint(
                    issue_id=issue.issue_id,
                    failure_class=failure_class,
                    failure_fingerprint=run_result.failure_fingerprint,
                    workspace_status=run_result.workspace_status,
                )
                if self._maybe_quarantine_failure_loop(
                    issue_id=issue.issue_id,
                    failure_class=failure_class,
                    failure_reason=failure_reason,
                    failure_fingerprint=run_result.failure_fingerprint,
                    workspace_status=run_result.workspace_status,
                ):
                    issue_state = "blocked"
                    attempt_state = "blocked"
                    return
                issue_state = self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class=run_result.failure_class,
                    failure_reason=run_result.failure_reason,
                )
                return

            if _abort_for_lost_lease():
                return

            upgrade = self.dispatcher.upgrade_locks(
                issue_id=issue.issue_id,
                lock_keys=diff_paths_to_lock_keys(run_result.diff_paths),
            )
            if not upgrade.acquired:
                failure_class = "lock_upgrade_conflict"
                failure_reason = upgrade.reason
                logger.info(
                    "Issue #%s attempt %s failed while upgrading locks: %s",
                    issue.issue_id,
                    attempt_no,
                    failure_reason,
                )
                issue_state = self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class="lock_upgrade_conflict",
                    failure_reason=upgrade.reason,
                )
                return

            verification = self.verifier.verify(
                issue_id=issue.issue_id,
                issue_title=issue.title,
                issue_body=issue.body,
                task_spec=task_spec,
                diff_paths=run_result.diff_paths,
                test_summary=run_result.test_summary,
                proposer_output=run_result.proposer_output,
                learned_context=learned_context,
                language=detected_language,
                workspace_status=run_result.workspace_status,
            )
            verifier_summary = {
                "passed": verification.passed,
                "summary": verification.summary,
                "verdict": getattr(verification, "verdict", "pass" if verification.passed else "hard_fail"),
                "hard_failure": bool(getattr(verification, "hard_failure", not verification.passed)),
                "parse_error": bool(getattr(verification, "parse_error", False)),
                "policy": _verifier_policy_for_settings(self.settings),
            }
            if _should_block_on_verification(self.settings, verification):
                failure_class = "verifier_failed"
                failure_reason = verification.summary
                logger.info(
                    "Issue #%s attempt %s failed verification: %s",
                    issue.issue_id,
                    attempt_no,
                    failure_reason,
                )
                issue_state = self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class="verifier_failed",
                    failure_reason=verification.summary,
                )
                return

            if _abort_for_lost_lease():
                return

            if (
                self.settings.healer_pr_actions_require_approval
                and not self._issue_has_approval_label(
                    issue_id=issue.issue_id,
                    local_labels=row.get("labels"),
                )
            ):
                self.store.set_healer_issue_state(
                    issue_id=issue.issue_id,
                    state="pr_pending_approval",
                    clear_lease=True,
                )
                self._post_issue_status(
                    issue_id=issue.issue_id,
                    body=self._format_flow_status_comment(
                        "Patch is ready for approval",
                        "The patch and validation passed. Approval is required before pull-request actions continue.",
                        [
                            "Status: `pr_pending_approval`",
                            f"Required label to continue: `{self.settings.healer_pr_required_label}`",
                            f"Verifier mode: `{_verifier_mode_label(self.settings, verification)}`",
                            f"Verifier: {self._clean_comment_text(verification.summary, max_chars=260)}",
                            *self._format_test_summary_bullets(run_result.test_summary),
                        ],
                        outro="Add the approval label to continue automatic pull-request actions.",
                    ),
                )
                issue_state = "pr_pending_approval"
                attempt_state = "pr_pending_approval"
                logger.info("Issue #%s is waiting for PR approval label", issue.issue_id)
                return

            if _abort_for_lost_lease():
                return

            commit_ok, commit_reason = self._commit_and_push(
                workspace.path,
                issue_id=issue.issue_id,
                branch=workspace.branch,
                issue_title=issue.title,
                issue_body=issue.body,
                task_spec=task_spec,
                language=detected_language,
            )
            if not commit_ok:
                failure_class = _classify_push_failure(commit_reason)
                failure_reason = commit_reason
                logger.info(
                    "Issue #%s attempt %s failed during commit/push: %s",
                    issue.issue_id,
                    attempt_no,
                    failure_reason,
                )
                issue_state = self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class=failure_class,
                    failure_reason=commit_reason,
                )
                return

            if _abort_for_lost_lease():
                return

            pr = self.tracker.open_or_update_pr(
                issue_id=issue.issue_id,
                branch=workspace.branch,
                title=f"healer: fix issue #{issue.issue_id} - {issue.title[:80]}",
                body=self._format_pr_description(
                    issue_id=issue.issue_id,
                    verifier_summary=verification.summary,
                    test_summary=run_result.test_summary,
                ),
                base=self.settings.healer_default_branch,
            )
            if pr is None:
                failure_class = "pr_open_failed"
                failure_reason = "Failed to create/update pull request."
                logger.info("Issue #%s attempt %s could not open PR", issue.issue_id, attempt_no)
                issue_state = self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class="pr_open_failed",
                    failure_reason="Failed to create/update pull request.",
                )
                return

            self.store.set_healer_issue_state(
                issue_id=issue.issue_id,
                state="pr_open",
                pr_number=pr.number,
                pr_state=pr.state,
                clear_lease=True,
            )
            self._post_issue_status(
                issue_id=issue.issue_id,
                body=self._format_flow_status_comment(
                    "Pull request opened or updated",
                    "I opened or updated the pull request for this issue.",
                    [
                        f"PR: [#{pr.number}]({pr.html_url})",
                        f"Execution mode: `{_execution_mode_for_task(connector=self.connector, task_spec=task_spec)}`",
                        f"Verifier mode: `{_verifier_mode_label(self.settings, verification)}`",
                        f"Verifier verdict: `{getattr(verification, 'verdict', 'pass' if verification.passed else 'hard_fail')}`",
                        *self._format_test_summary_bullets(run_result.test_summary),
                    ],
                ),
            )
            issue_state = "pr_open"
            attempt_state = "pr_open"
            self._maybe_auto_approve_pr(pr_number=pr.number)
            self._maybe_auto_merge_pr(pr_number=pr.number)
            logger.info("Issue #%s opened/updated PR #%s", issue.issue_id, pr.number)
            if self.settings.healer_enable_review:
                try:
                    review = self.reviewer.review(
                        issue_id=issue.issue_id,
                        issue_title=issue.title,
                        issue_body=issue.body,
                        diff_paths=run_result.diff_paths,
                        test_summary=run_result.test_summary,
                        proposer_output=run_result.proposer_output,
                        verifier_summary=verification.summary,
                        learned_context=learned_context,
                    )
                    self.tracker.add_pr_comment(pr_number=pr.number, body=review.review_body)
                except Exception as exc:
                    logger.warning("Failed to generate or post code review for PR #%d: %s", pr.number, exc)
        finally:
            lease_stop.set()
            lease_thread.join(timeout=1.0)
            if attempt_id:
                self.store.finish_healer_attempt(
                    attempt_id=attempt_id,
                    state=attempt_state,
                    actual_diff_set=actual_diff,
                    test_summary=test_summary,
                    verifier_summary=verifier_summary,
                    failure_class=failure_class,
                    failure_reason=failure_reason,
                    proposer_output_excerpt=proposer_output_excerpt,
                )
                self.memory.maybe_record_lesson(
                    issue=issue,
                    attempt_id=attempt_id,
                    final_state=attempt_state,
                    predicted_lock_set=prediction.keys,
                    actual_diff_set=actual_diff,
                    test_summary=test_summary,
                    verifier_summary=verifier_summary,
                    failure_class=failure_class,
                    failure_reason=failure_reason,
                )
            try:
                self.store.release_healer_locks(issue_id=issue.issue_id)
            except Exception as exc:
                logger.error("Failed to release locks for issue #%s: %s", issue.issue_id, exc)
            if workspace is not None:
                self._cleanup_workspace(issue_id=issue.issue_id, state=issue_state, workspace_path=workspace.path)
            logger.info("Issue #%s attempt finished with state=%s", issue.issue_id, attempt_state)
            if attempt_state == "failed" and failure_class and issue_state in {"failed", "blocked"}:
                self._post_issue_status(
                    issue_id=issue.issue_id,
                    body=self._format_flow_status_comment(
                        "Attempt failed",
                        None,
                        [
                            f"Attempt state: `{attempt_state}`",
                            f"Failure class: `{failure_class}`",
                            f"Reason: {self._clean_comment_text(failure_reason, max_chars=320)}",
                        ],
                        outro="Failure details were saved so the next pass can reuse the context.",
                        ),
                )

    def _claim_is_actionable(self, issue: HealerIssue) -> bool:
        if not issue.issue_id:
            return False
        try:
            snapshot = self.tracker.get_issue(issue_id=issue.issue_id)
        except Exception as exc:
            logger.warning(
                "Failed to refresh remote state for issue #%s; proceeding with local claim: %s",
                issue.issue_id,
                exc,
            )
            return True
        if not isinstance(snapshot, dict):
            return True

        remote_state = str(snapshot.get("state") or "").strip().lower()
        remote_labels = {
            str(label).strip().lower()
            for label in (snapshot.get("labels") or [])
            if str(label).strip()
        }
        if remote_state and remote_state != "open":
            self.store.set_healer_issue_state(
                issue_id=issue.issue_id,
                state="archived",
                pr_state="closed",
                last_failure_class="",
                last_failure_reason="",
                clear_lease=True,
            )
            logger.info("Skipping issue #%s because GitHub issue is %s.", issue.issue_id, remote_state)
            return False

        required_labels = [label for label in self.settings.healer_issue_required_labels if label.strip()]
        normalized_required = [self._normalize_label(label) for label in required_labels]
        missing_labels = [
            required
            for required, normalized in zip(required_labels, normalized_required)
            if normalized not in remote_labels
        ]
        if missing_labels:
            self.store.set_healer_issue_state(
                issue_id=issue.issue_id,
                state="blocked",
                last_failure_class="",
                last_failure_reason="",
                clear_lease=True,
            )
            logger.info(
                "Skipping issue #%s because required labels are missing: %s",
                issue.issue_id,
                ", ".join(missing_labels),
            )
            return False
        open_pr = self._discover_open_pr_for_issue(issue_id=issue.issue_id)
        if open_pr is not None:
            self._restore_open_pr_state(
                issue_id=issue.issue_id,
                pr_number=open_pr.number,
                pr_state=open_pr.state,
            )
            logger.info(
                "Skipping issue #%s because PR #%s is already open.",
                issue.issue_id,
                open_pr.number,
            )
            return False
        return True

    @staticmethod
    def _normalize_label(label: str) -> str:
        return (label or "").strip().lower()

    def _issue_has_approval_label(
        self,
        *,
        issue_id: str,
        pr_number: int = 0,
        local_labels: object | None = None,
    ) -> bool:
        required_label = self._normalize_label(self.settings.healer_pr_required_label)
        if not required_label:
            return True
        if required_label in self._normalize_labels(local_labels):
            return True
        try:
            if self.tracker.issue_has_label(issue_id=issue_id, label=required_label):
                return True
        except Exception as exc:
            logger.warning("Failed to verify approval label for issue #%s: %s", issue_id, exc)
        if pr_number <= 0:
            return False
        try:
            pr_issue = self.tracker.get_issue(issue_id=str(pr_number))
        except Exception as exc:
            logger.warning("Failed to load PR #%s while checking approval label: %s", pr_number, exc)
            return False
        if not isinstance(pr_issue, dict):
            return False
        pr_labels = {
            self._normalize_label(str((entry or {}).get("name") or ""))
            for entry in (pr_issue.get("labels") or [])
        }
        return required_label in pr_labels

    @staticmethod
    def _normalize_labels(labels: object | None) -> set[str]:
        if labels is None:
            return set()
        if isinstance(labels, str):
            return {
                normalized
                for label in labels.split(",")
                if (normalized := (label or "").strip().lower())
            }
        if not isinstance(labels, (list, tuple, set)):
            return set()
        return {
            normalized
            for label in labels
            if (normalized := str(label or "").strip().lower())
        }

    def _lease_heartbeat(
        self,
        issue_id: str,
        stop_event: threading.Event,
        lease_lost: threading.Event,
    ) -> None:
        interval = max(15.0, float(self.dispatcher.lease_seconds) / 2.0)
        while not stop_event.wait(interval):
            renewed = self.store.renew_healer_issue_lease(
                issue_id=issue_id,
                worker_id=self.worker_id,
                lease_seconds=self.dispatcher.lease_seconds,
            )
            if not renewed:
                logger.warning("Lease heartbeat stopped for issue #%s; lease could not be renewed.", issue_id)
                lease_lost.set()
                return

    def _backoff_or_fail(
        self,
        *,
        issue_id: str,
        attempt_no: int,
        failure_class: str,
        failure_reason: str,
    ) -> str:
        is_infra = failure_class in _INFRA_FAILURE_CLASSES
        counts_against_trust = _counts_against_issue_trust(failure_class=failure_class, failure_reason=failure_reason)
        is_always_requeue = is_infra or (failure_class in _ALWAYS_REQUEUE_FAILURE_CLASSES) or not counts_against_trust

        if is_always_requeue:
            if is_infra:
                delay = max(15, min(300, int(self.settings.healer_backoff_initial_seconds)))
            elif failure_class in {"lock_conflict", "lock_upgrade_conflict"}:
                delay = 15
            else:
                delay = min(
                    self.settings.healer_backoff_max_seconds,
                    self.settings.healer_backoff_initial_seconds * (2 ** max(0, attempt_no - 1)),
                )
            backoff_until = (datetime.now(UTC) + timedelta(seconds=delay)).strftime("%Y-%m-%d %H:%M:%S")
            self.store.set_healer_issue_state(
                issue_id=issue_id,
                state="queued",
                backoff_until=backoff_until,
                last_failure_class=failure_class,
                last_failure_reason=failure_reason[:500],
                clear_lease=True,
            )
            if is_infra:
                now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                self.store.set_state("healer_connector_last_error_class", failure_class)
                self.store.set_state("healer_connector_last_error_reason", failure_reason[:500])
                self.store.set_state("healer_connector_last_error_at", now_str)
            logger.info(
                "Issue #%s requeued after attempt %s with backoff until %s (%s)",
                issue_id,
                attempt_no,
                backoff_until,
                failure_class,
            )
            self._post_issue_status(
                issue_id=issue_id,
                body=self._format_flow_status_comment(
                    "Issue requeued automatically",
                    "This failure class is configured for automatic requeue.",
                    [
                        f"Attempt: `{attempt_no}`",
                        f"Failure class: `{failure_class}`",
                        f"Reason: {self._clean_comment_text(failure_reason, max_chars=260)}",
                        f"Next retry not before: `{backoff_until} UTC`",
                    ],
                ),
            )
            return "queued"

        if attempt_no >= self.settings.healer_retry_budget:
            self.store.set_healer_issue_state(
                issue_id=issue_id,
                state="failed",
                last_failure_class=failure_class,
                last_failure_reason=failure_reason[:500],
                clear_lease=True,
            )
            logger.info(
                "Issue #%s reached retry budget and is now failed (%s): %s",
                issue_id,
                failure_class,
                failure_reason,
            )
            return "failed"

        delay = min(
            self.settings.healer_backoff_max_seconds,
            self.settings.healer_backoff_initial_seconds * (2 ** max(0, attempt_no - 1)),
        )
        strategy = _FAILURE_CLASS_STRATEGY.get(failure_class, {})
        multiplier = float(strategy.get("backoff_multiplier", 1.0))
        delay = max(15, int(delay * multiplier))
        feedback_hint = str(strategy.get("feedback_hint", "")).strip()
        backoff_until = (datetime.now(UTC) + timedelta(seconds=delay)).strftime("%Y-%m-%d %H:%M:%S")
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="queued",
            backoff_until=backoff_until,
            last_failure_class=failure_class,
            last_failure_reason=failure_reason[:500],
            feedback_context=feedback_hint if feedback_hint else None,
            clear_lease=True,
        )
        logger.info(
                "Issue #%s requeued after attempt %s with backoff until %s (%s)",
                issue_id,
                attempt_no,
                backoff_until,
                failure_class,
            )
        self._post_issue_status(
            issue_id=issue_id,
            body=self._format_flow_status_comment(
                "Issue requeued for another attempt",
                "This attempt failed, but the issue is still within retry budget.",
                [
                    f"Attempt: `{attempt_no}`",
                    f"Failure class: `{failure_class}`",
                    f"Reason: {self._clean_comment_text(failure_reason, max_chars=260)}",
                    f"Next retry not before: `{backoff_until} UTC`",
                    f"Retry budget: `{self.settings.healer_retry_budget}`",
                ],
            ),
        )
        return "queued"

    def _connector_health_snapshot(self) -> dict[str, str | bool]:
        try:
            self.connector.ensure_started()
        except Exception as exc:
            return {
                "available": False,
                "configured_command": "",
                "resolved_command": "",
                "availability_reason": f"connector ensure_started failed: {exc}",
                "last_health_error": str(exc),
            }
        if hasattr(self.connector, "health_snapshot"):
            try:
                health = self.connector.health_snapshot()  # type: ignore[attr-defined]
                return {
                    "available": bool(health.get("available")),
                    "configured_command": str(health.get("configured_command") or ""),
                    "resolved_command": str(health.get("resolved_command") or ""),
                    "availability_reason": str(health.get("availability_reason") or ""),
                    "last_health_error": str(health.get("last_health_error") or ""),
                }
            except Exception as exc:
                return {
                    "available": False,
                    "configured_command": "",
                    "resolved_command": "",
                    "availability_reason": f"connector health snapshot failed: {exc}",
                    "last_health_error": str(exc),
                }
        return {
            "available": True,
            "configured_command": "",
            "resolved_command": "",
            "availability_reason": "",
            "last_health_error": "",
        }

    def _record_connector_health(self, health: dict[str, str | bool]) -> None:
        available = "true" if bool(health.get("available")) else "false"
        self.store.set_state("healer_connector_available", available)
        self.store.set_state("healer_connector_configured_command", str(health.get("configured_command") or ""))
        self.store.set_state("healer_connector_resolved_command", str(health.get("resolved_command") or ""))
        self.store.set_state("healer_connector_availability_reason", str(health.get("availability_reason") or ""))
        self.store.set_state("healer_connector_last_checked_at", datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"))

    def _record_failure_fingerprint(
        self,
        *,
        issue_id: str,
        failure_class: str,
        failure_fingerprint: str,
        workspace_status: dict[str, object] | None,
    ) -> None:
        if not failure_fingerprint:
            return
        self.store.set_state("healer_last_failure_fingerprint", failure_fingerprint)
        self.store.set_state("healer_last_failure_fingerprint_issue_id", issue_id)
        self.store.set_state("healer_last_failure_fingerprint_class", failure_class)
        contamination = workspace_status or {}
        contamination_paths = contamination.get("contamination_paths") or contamination.get("cleaned_paths") or []
        rendered = ", ".join(str(item).strip() for item in contamination_paths if str(item).strip())
        self.store.set_state("healer_last_contamination_paths", rendered)

    def _maybe_quarantine_failure_loop(
        self,
        *,
        issue_id: str,
        failure_class: str,
        failure_reason: str,
        failure_fingerprint: str,
        workspace_status: dict[str, object] | None,
    ) -> bool:
        if not failure_fingerprint:
            return False
        threshold = max(2, int(getattr(self.settings, "healer_failure_fingerprint_quarantine_threshold", 2)))
        attempts = self.store.list_healer_attempts(issue_id=issue_id, limit=max(threshold, 5))
        matches = 1
        for attempt in attempts:
            summary = attempt.get("test_summary") or {}
            if str(summary.get("failure_fingerprint") or "").strip() != failure_fingerprint:
                break
            matches += 1
            if matches >= threshold:
                break
        if matches < threshold:
            return False
        self._record_failure_fingerprint(
            issue_id=issue_id,
            failure_class=failure_class,
            failure_fingerprint=failure_fingerprint,
            workspace_status=workspace_status,
        )
        reason = f"{failure_reason} Repeated failure fingerprint hit threshold={threshold}."
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="blocked",
            last_failure_class=failure_class,
            last_failure_reason=reason[:500],
            feedback_context=f"Repeated failure fingerprint: {failure_fingerprint}"[:500],
            clear_lease=True,
        )
        contamination = workspace_status or {}
        contamination_paths = contamination.get("contamination_paths") or contamination.get("cleaned_paths") or []
        details = [
            "Status: `blocked`",
            f"Failure class: `{failure_class}`",
            f"Fingerprint: `{failure_fingerprint}`",
        ]
        if contamination_paths:
            details.append(f"Contamination: `{', '.join(str(item) for item in contamination_paths)}`")
        self._post_issue_status(
            issue_id=issue_id,
            body=self._format_flow_status_comment(
                "Repeated failure pattern detected; issue paused",
                "The same deterministic failure repeated, so this issue is blocked instead of retrying indefinitely.",
                details,
                outro="Clear the workspace hygiene issue or adjust the guardrails, then requeue for another pass.",
            ),
        )
        return True

    def _circuit_breaker_status(self) -> CircuitBreakerStatus:
        window = max(5, self.settings.healer_circuit_breaker_window)
        attempts = self.store.list_recent_healer_attempts(limit=window)
        if len(attempts) < window:
            return CircuitBreakerStatus(
                open=False,
                window=window,
                attempts_considered=len(attempts),
                failures=0,
                failure_rate=0.0,
                threshold=float(self.settings.healer_circuit_breaker_failure_rate),
                cooldown_seconds=max(60, int(self.settings.healer_circuit_breaker_cooldown_seconds)),
                cooldown_remaining_seconds=0,
                last_failure_at="",
            )
        failures = 0
        latest_failure_at: datetime | None = None
        for attempt in attempts:
            state = str(attempt.get("state") or "").lower()
            if state not in {"pr_open", "resolved", "pr_pending_approval", "interrupted"}:
                issue = self.store.get_healer_issue(str(attempt.get("issue_id") or ""))
                family = classify_failure_family(issue, attempt)
                if family != "product":
                    continue
                failures += 1
                finished_at = _parse_store_timestamp(str(attempt.get("finished_at") or ""))
                if finished_at is not None and (latest_failure_at is None or finished_at > latest_failure_at):
                    latest_failure_at = finished_at
        failure_rate = failures / float(max(1, len(attempts)))
        threshold = float(self.settings.healer_circuit_breaker_failure_rate)
        cooldown_seconds = max(60, int(self.settings.healer_circuit_breaker_cooldown_seconds))
        if failure_rate < threshold:
            return CircuitBreakerStatus(
                open=False,
                window=window,
                attempts_considered=len(attempts),
                failures=failures,
                failure_rate=failure_rate,
                threshold=threshold,
                cooldown_seconds=cooldown_seconds,
                cooldown_remaining_seconds=0,
                last_failure_at=_format_store_timestamp(latest_failure_at),
            )

        cooldown_remaining_seconds = 0
        if latest_failure_at is not None:
            elapsed = (datetime.now(UTC) - latest_failure_at).total_seconds()
            cooldown_remaining_seconds = max(0, int(cooldown_seconds - elapsed))
        return CircuitBreakerStatus(
            open=cooldown_remaining_seconds > 0,
            window=window,
            attempts_considered=len(attempts),
            failures=failures,
            failure_rate=failure_rate,
            threshold=threshold,
            cooldown_seconds=cooldown_seconds,
            cooldown_remaining_seconds=cooldown_remaining_seconds,
            last_failure_at=_format_store_timestamp(latest_failure_at),
        )

    def _circuit_breaker_open(self) -> bool:
        return self._circuit_breaker_status().open

    def _mutation_key(self, *, action: str, issue_id: str = "", pr_number: int = 0, body: str = "") -> str:
        body_hash = hashlib.sha1((body or "").encode("utf-8")).hexdigest()[:16] if body else ""
        return "|".join(
            [
                "gh_mutation",
                self.settings.repo_name,
                action.strip(),
                str(issue_id or ""),
                str(int(pr_number) if pr_number else 0),
                body_hash,
            ]
        )

    def _run_idempotent_mutation(self, *, mutation_key: str, action: Callable[[], bool]) -> bool:
        claim = self.store.claim_healer_mutation(mutation_key=mutation_key)
        if claim in {"already_success", "inflight"}:
            return True
        ok = False
        try:
            ok = bool(action())
        except Exception as exc:
            logger.warning("GitHub mutation %s failed with exception: %s", mutation_key, exc)
            ok = False
        self.store.complete_healer_mutation(mutation_key=mutation_key, success=ok)
        return ok

    def _tracker_last_error(self) -> tuple[str, str]:
        try:
            return self.tracker.get_last_error()
        except Exception:
            return "", ""

    def _note_infra_failure(self, *, failure_class: str, failure_reason: str) -> None:
        if failure_class not in _INFRA_FAILURE_CLASSES:
            return
        streak = self._coerce_int(self.store.get_state("healer_infra_failure_streak"), default=0) + 1
        self.store.set_state("healer_infra_failure_streak", str(streak))
        threshold = max(1, int(getattr(self.settings, "healer_infra_dlq_threshold", 8)))
        if streak < threshold:
            return
        cooldown_seconds = max(60, int(getattr(self.settings, "healer_infra_dlq_cooldown_seconds", 3600)))
        pause_until = datetime.now(UTC) + timedelta(seconds=cooldown_seconds)
        pause_until_str = pause_until.strftime("%Y-%m-%d %H:%M:%S")
        self.store.set_state("healer_infra_pause_until", pause_until_str)
        self.store.set_state("healer_infra_pause_reason", f"{failure_class}: {failure_reason[:300]}")
        logger.warning(
            "Infra failure streak reached %d/%d. Pausing claims until %s.",
            streak,
            threshold,
            pause_until_str,
        )

    def _reset_infra_failure_streak(self) -> None:
        self.store.set_state("healer_infra_failure_streak", "0")
        self.store.set_state("healer_infra_pause_until", "")
        self.store.set_state("healer_infra_pause_reason", "")

    def _infra_pause_active(self) -> bool:
        raw = str(self.store.get_state("healer_infra_pause_until") or "").strip()
        if not raw:
            return False
        try:
            pause_until = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            return False
        return datetime.now(UTC) < pause_until

    def _recheck_conflict_state(
        self,
        *,
        pr_number: int,
        current_state: str,
        current_mergeable_state: str,
    ) -> tuple[str, str, PullRequestDetails | None]:
        if current_state != "conflict":
            return current_state, current_mergeable_state, None
        delay = max(1, int(getattr(self.settings, "healer_mergeability_recheck_delay_seconds", 2)))
        time.sleep(delay)
        details = self.tracker.get_pr_details(pr_number=pr_number)
        if details is None:
            return current_state, current_mergeable_state, None
        if details.state != "conflict":
            logger.info(
                "PR #%d conflict cleared on recheck (state=%s mergeable_state=%s).",
                pr_number,
                details.state,
                details.mergeable_state,
            )
        return details.state, details.mergeable_state, details

    def _post_issue_status(self, *, issue_id: str, body: str) -> None:
        mutation_key = self._mutation_key(action="issue_comment", issue_id=issue_id, body=body)
        for attempt in range(2):
            try:
                if self._run_idempotent_mutation(
                    mutation_key=mutation_key,
                    action=lambda: self.tracker.add_issue_comment(issue_id=issue_id, body=body),
                ):
                    return
                last_error_class, last_error_reason = self._tracker_last_error()
                if last_error_class == "github_rate_limited":
                    self._note_infra_failure(
                        failure_class="github_rate_limited",
                        failure_reason=last_error_reason or "GitHub rate limit while posting issue status.",
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to post issue comment for issue #%s (attempt %d): %s",
                    issue_id,
                    attempt + 1,
                    exc,
                )
                if attempt == 0:
                    time.sleep(2)

    @staticmethod
    def _format_flow_status_comment(
        title: str,
        intro: str | None,
        bullets: list[str],
        *,
        outro: str | None = None,
    ) -> str:
        lines = [f"### {title.strip()}", ""]
        if intro:
            lines.extend([intro.strip(), ""])
        lines.extend(f"- {item}" for item in bullets if item.strip())
        if outro:
            lines.extend(["", outro.strip()])
        lines.extend(["", "-- Flow Healer"])
        return "\n".join(lines)

    @staticmethod
    def _clean_comment_text(value: object, *, max_chars: int = 240) -> str:
        text = re.sub(r"\s+", " ", str(value or "").strip())
        if not text:
            return ""
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3].rstrip()}..."

    @staticmethod
    def _coerce_int(value: object, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _format_full_gate_bullet(cls, summary: dict[str, object], *, runner: str) -> str:
        status = cls._clean_comment_text(summary.get(f"{runner}_full_status") or "", max_chars=40)
        exit_code_raw = summary.get(f"{runner}_full_exit_code")
        exit_code = cls._clean_comment_text(exit_code_raw, max_chars=20) if exit_code_raw not in (None, "") else ""
        reason = cls._clean_comment_text(summary.get(f"{runner}_full_reason") or "", max_chars=120)
        if not status and not exit_code:
            return ""
        if not status:
            status = "passed" if cls._coerce_int(exit_code_raw, default=1) == 0 else "failed"
        details: list[str] = []
        if exit_code:
            details.append(f"exit `{exit_code}`")
        if reason:
            details.append(f"reason `{reason}`")
        suffix = f" ({', '.join(details)})" if details else ""
        return f"{runner.capitalize()} full gate: `{status}`{suffix}"

    @classmethod
    def _format_test_summary_bullets(cls, summary: dict[str, object] | None) -> list[str]:
        if not summary:
            return ["Test gates: `not reported`"]
        failed_tests = cls._coerce_int(summary.get("failed_tests"), default=0)
        overall_status = "passed" if failed_tests == 0 else "failed"
        bullets = [
            f"Test gates: `{overall_status}`",
            f"Failed tests: `{failed_tests}`",
        ]
        mode = cls._clean_comment_text(summary.get("mode") or "", max_chars=40)
        if mode:
            bullets.append(f"Gate mode: `{mode}`")
        language = cls._clean_comment_text(
            summary.get("language_effective") or summary.get("language_detected") or "",
            max_chars=40,
        )
        if language:
            bullets.append(f"Language: `{language}`")
        execution_root = cls._clean_comment_text(summary.get("execution_root") or "", max_chars=80)
        if execution_root:
            bullets.append(f"Execution root: `{execution_root}`")
        targeted_raw = summary.get("targeted_tests")
        if isinstance(targeted_raw, list):
            targeted: list[str] = []
            for item in targeted_raw:
                cleaned = cls._clean_comment_text(item, max_chars=90)
                if cleaned:
                    targeted.append(cleaned)
            if targeted:
                preview = ", ".join(f"`{item}`" for item in targeted[:3])
                if len(targeted) > 3:
                    preview = f"{preview} (+{len(targeted) - 3} more)"
                bullets.append(f"Targeted tests: {preview}")
        for runner in ("local", "docker"):
            gate_bullet = cls._format_full_gate_bullet(summary, runner=runner)
            if gate_bullet:
                bullets.append(gate_bullet)
        return bullets

    @classmethod
    def _format_pr_description(
        cls,
        *,
        issue_id: str,
        verifier_summary: str,
        test_summary: dict[str, object],
    ) -> str:
        verifier_line = cls._clean_comment_text(verifier_summary or "passed", max_chars=260) or "passed"
        lines = [
            f"Automated Flow Healer proposal for issue #{issue_id}.",
            "",
            "### Verification",
            f"- Verifier: `{verifier_line}`",
            "",
            "### Test Summary",
        ]
        lines.extend(f"- {item}" for item in cls._format_test_summary_bullets(test_summary))
        return "\n".join(lines) + "\n"

    def _cleanup_workspace(self, *, issue_id: str, state: str, workspace_path: Path) -> None:
        try:
            self.workspace_manager.remove_workspace(workspace_path=workspace_path)
        except Exception as exc:
            logger.error("Failed to clean workspace for issue #%s: %s", issue_id, exc)
            self.store.set_state("healer_last_workspace_cleanup_error", str(exc)[:500])
            return
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state=state,
            workspace_path="",
            branch_name="",
        )

    @staticmethod
    def _commit_and_push(
        workspace: Path,
        *,
        issue_id: str,
        branch: str,
        issue_title: str,
        issue_body: str,
        task_spec: HealerTaskSpec,
        language: str,
    ) -> tuple[bool, str]:
        if not _stage_workspace_changes(
            workspace,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            language=language,
        ):
            return False, "No non-artifact staged changes remained after artifact filtering."

        diff = subprocess.run(
            ["git", "-C", str(workspace), "diff", "--cached", "--quiet"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if diff.returncode == 0:
            return False, "No staged changes to commit."

        commit = subprocess.run(
            ["git", "-C", str(workspace), "commit", "-m", f"healer: fix issue #{issue_id}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
        if commit.returncode != 0:
            return False, (commit.stderr or commit.stdout or "git commit failed").strip()

        push = _push_issue_branch(workspace=workspace, branch=branch)
        if push.returncode != 0:
            return False, (push.stderr or push.stdout or "git push failed").strip()
        return True, ""


def _parse_store_timestamp(raw: str) -> datetime | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _format_store_timestamp(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _is_actionable_feedback_author(author: str, self_actor: str) -> bool:
    normalized = (author or "").strip().lower()
    if not normalized or normalized == (self_actor or "").strip().lower():
        return False
    if normalized.endswith("[bot]"):
        return False
    return True


def _execution_mode_for_task(*, connector: ConnectorProtocol, task_spec: Any) -> str:
    if str(getattr(task_spec, "validation_profile", "") or "") == "artifact_only":
        return "artifact_synthesis"
    if connector.__class__.__name__ == "CodexAppServerConnector":
        return "workspace_edit"
    return "serialized_patch"


def _verifier_policy_for_settings(settings: RelaySettings) -> str:
    policy = str(getattr(settings, "healer_verifier_policy", "advisory") or "advisory").strip().lower()
    return "required" if policy == "required" else "advisory"


def _should_block_on_verification(settings: RelaySettings, verification: Any) -> bool:
    if bool(getattr(verification, "passed", False)):
        return False
    if bool(getattr(verification, "hard_failure", False)):
        return True
    return _verifier_policy_for_settings(settings) == "required"


def _verifier_mode_label(settings: RelaySettings, verification: Any) -> str:
    policy = _verifier_policy_for_settings(settings)
    if bool(getattr(verification, "hard_failure", False)):
        return "required"
    return policy


def _is_managed_healer_branch(branch: str) -> bool:
    normalized = str(branch or "").strip()
    return normalized.startswith("healer/issue-")


def _classify_push_failure(reason: str) -> str:
    lowered = str(reason or "").lower()
    if "non-fast-forward" in lowered:
        return "push_non_fast_forward"
    return "push_failed"


def _counts_against_issue_trust(*, failure_class: str, failure_reason: str) -> bool:
    family = classify_failure_family(
        {"state": "failed", "last_failure_class": failure_class, "last_failure_reason": failure_reason},
        {"failure_class": failure_class, "failure_reason": failure_reason},
    )
    return family == "product"


def _push_issue_branch(*, workspace: Path, branch: str) -> subprocess.CompletedProcess[str]:
    branch_name = str(branch or "").strip()
    target_ref = f"HEAD:refs/heads/{branch_name}"
    if not _is_managed_healer_branch(branch_name):
        return subprocess.run(
            ["git", "-C", str(workspace), "push", "-u", "origin", target_ref],
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def _managed_push(expected_sha: str) -> subprocess.CompletedProcess[str]:
        cmd = ["git", "-C", str(workspace), "push"]
        if expected_sha:
            cmd.append(f"--force-with-lease=refs/heads/{branch_name}:{expected_sha}")
        cmd.extend(["-u", "origin", target_ref])
        return subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )

    expected_sha = _ls_remote_branch_sha(workspace=workspace, branch=branch_name)
    push = _managed_push(expected_sha)
    if push.returncode == 0:
        return push
    if "non-fast-forward" not in ((push.stderr or "") + (push.stdout or "")).lower():
        return push
    refreshed_sha = _ls_remote_branch_sha(workspace=workspace, branch=branch_name)
    if refreshed_sha == expected_sha:
        return push
    return _managed_push(refreshed_sha)


def _ls_remote_branch_sha(*, workspace: Path, branch: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(workspace), "ls-remote", "--heads", "origin", branch],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        return ""
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return ""
    return line[0].split()[0].strip() if line[0].split() else ""


def _collect_targeted_tests(
    *,
    issue_body: str,
    output_targets: list[str] | tuple[str, ...],
    workspace: Path,
    language: str,
    execution_root: str = "",
) -> list[str]:
    explicit = {path.strip() for path in _TARGETED_TEST_RE.findall(issue_body or "") if path.strip()}
    candidates = {
        normalized
        for path in explicit
        if (normalized := _normalize_targeted_test_path(path=path, workspace=workspace, execution_root=execution_root))
    }
    if not explicit:
        candidates.update(
            _infer_targeted_tests_from_targets(
                output_targets=output_targets,
                workspace=workspace,
                language=language,
                execution_root=execution_root,
            )
        )
    return sorted(path for path in candidates if path)


def _infer_targeted_tests_from_targets(
    *,
    output_targets: list[str] | tuple[str, ...],
    workspace: Path,
    language: str,
    execution_root: str = "",
) -> set[str]:
    normalized_language = (language or "").strip().lower()
    if normalized_language != "python":
        return set()
    execution_path = workspace / execution_root if execution_root else workspace
    inferred: set[str] = set()
    for raw_target in output_targets or ():
        target = str(raw_target or "").strip()
        if not target:
            continue
        target_path = Path(target)
        local_target = _strip_execution_root_prefix(target=target, execution_root=execution_root)
        local_path = Path(local_target)
        if normalized_language == "python":
            if local_target.startswith("tests/") and (execution_path / local_path).exists():
                inferred.add(local_target)
                continue
            if not local_target.startswith("src/") or local_path.suffix != ".py":
                continue
            src_relative = local_path.relative_to("src")
            candidates = [
                Path("tests") / f"test_{local_path.stem}.py",
                Path("tests") / src_relative.parent / f"test_{local_path.stem}.py",
            ]
            for candidate in candidates:
                if (execution_path / candidate).exists():
                    inferred.add(candidate.as_posix())
            continue
    return inferred


def _normalize_targeted_test_path(*, path: str, workspace: Path, execution_root: str) -> str:
    cleaned = str(path or "").strip().lstrip("./")
    if not cleaned:
        return ""
    if execution_root and cleaned.startswith(f"{execution_root}/"):
        return cleaned[len(execution_root) + 1 :]
    if execution_root and (workspace / execution_root / cleaned).exists():
        return cleaned
    if (workspace / cleaned).exists():
        return cleaned
    return cleaned[len(execution_root) + 1 :] if execution_root and cleaned.startswith(f"{execution_root}/") else cleaned


def _strip_execution_root_prefix(*, target: str, execution_root: str) -> str:
    cleaned = str(target or "").strip().lstrip("./")
    if execution_root and cleaned.startswith(f"{execution_root}/"):
        return cleaned[len(execution_root) + 1 :]
    return cleaned
