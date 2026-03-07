from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .config import RelaySettings
from .healer_dispatcher import HealerDispatcher
from .healer_locks import diff_paths_to_lock_keys, predict_lock_set
from .healer_memory import HealerMemoryService
from .healer_reconciler import HealerReconciler
from .healer_reviewer import HealerReviewer
from .healer_runner import HealerRunner
from .healer_scan import FlowHealerScanner
from .healer_tracker import GitHubHealerTracker, HealerIssue
from .healer_task_spec import compile_task_spec
from .healer_verifier import HealerVerifier
from .protocols import ConnectorProtocol
from .store import SQLiteStore

logger = logging.getLogger("apple_flow.healer_loop")

_TARGETED_TEST_RE = re.compile(r"\btests/[A-Za-z0-9_./\-]*test[A-Za-z0-9_./\-]*\.py\b")
_FLOW_COMMENT_PERSONA = (
    "Laid-back tech bro vibes, light emoji use, concise status updates, "
    "and always sign off with '-- Flow 🌊'."
)
_INFRA_FAILURE_CLASSES = {"connector_unavailable", "connector_runtime_error"}
_ALWAYS_REQUEUE_FAILURE_CLASSES = {
    "no_patch",
    "no_workspace_change",
    "patch_apply_failed",
    "no_code_diff",
}


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
        )
        self.runner = HealerRunner(
            connector=connector,
            timeout_seconds=settings.healer_max_wall_clock_seconds_per_issue,
            test_gate_mode=settings.healer_test_gate_mode,
        )
        self.verifier = HealerVerifier(connector=connector)
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
            issue = self.dispatcher.claim_next_issue()
            if not issue:
                break
            self._process_claimed_issue(issue)
            processed += 1

    def _ingest_pr_feedback(self) -> None:
        active_prs = self.store.list_healer_issues(states=["pr_open", "pr_pending_approval"], limit=100)
        self_actor = self.tracker.viewer_login().lower()
        for row in active_prs:
            pr_number = int(row.get("pr_number") or 0)
            if pr_number <= 0:
                continue

            issue_id = str(row.get("issue_id") or "")
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
                    state="queued",
                    last_issue_comment_id=max_issue_comment_id,
                    last_review_id=max_review_id,
                    last_review_comment_id=max_review_comment_id,
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
                )

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

    def _reconcile_pr_outcomes(self) -> int:
        active_prs = self.store.list_healer_issues(states=["pr_open"], limit=100)
        resolved = 0
        for row in active_prs:
            pr_number = int(row.get("pr_number") or 0)
            if pr_number <= 0:
                continue

            pr_state = self.tracker.get_pr_state(pr_number=pr_number).strip().lower()
            if pr_state != "merged":
                if pr_state and pr_state != str(row.get("pr_state") or "").strip().lower():
                    self.store.set_healer_issue_state(
                        issue_id=str(row.get("issue_id") or ""),
                        state="pr_open",
                        pr_state=pr_state,
                    )
                continue

            issue_id = str(row.get("issue_id") or "")
            if not issue_id:
                continue

            if not self.tracker.close_issue(issue_id=issue_id):
                logger.warning(
                    "PR #%d is merged but Flow Healer could not close issue #%s yet.",
                    pr_number,
                    issue_id,
                )
                self.store.set_healer_issue_state(
                    issue_id=issue_id,
                    state="pr_open",
                    pr_state="merged",
                )
                continue

            self.store.set_healer_issue_state(
                issue_id=issue_id,
                state="resolved",
                pr_state="merged",
                clear_lease=True,
            )
            self._post_issue_status(
                issue_id=issue_id,
                body=self._format_flow_status_comment(
                    "Merged and wrapped up 🌊",
                    "The PR landed on the base branch, so I'm closing this one out.",
                    [
                        "Status: `resolved`",
                        f"PR: `#{pr_number}`",
                    ],
                ),
            )
            resolved += 1
        return resolved

    def _ingest_ready_issues(self) -> None:
        issues = self.tracker.list_ready_issues(
            required_labels=self.settings.healer_issue_required_labels,
            trusted_actors=self.settings.healer_trusted_actors,
            limit=max(10, self.settings.healer_max_concurrent_issues * 5),
        )
        for issue in issues:
            existing_issue = self.store.get_healer_issue(issue.issue_id)
            self.store.upsert_healer_issue(
                issue_id=issue.issue_id,
                repo=issue.repo,
                title=issue.title,
                body=issue.body,
                author=issue.author,
                labels=issue.labels,
                priority=issue.priority,
            )
            if existing_issue is not None:
                existing_state = str(existing_issue.get("state") or "").strip().lower()
                existing_pr_state = str(existing_issue.get("pr_state") or "").strip().lower()
                if existing_state in {"archived", "blocked"} or (
                    existing_state == "resolved" and existing_pr_state == "closed"
                ):
                    self.store.set_healer_issue_state(
                        issue_id=issue.issue_id,
                        state="queued",
                        pr_state="",
                        last_failure_class="",
                        last_failure_reason="",
                        clear_lease=True,
                    )
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
            if not self._issue_has_label(
                issue_id=issue_id,
                label=self.settings.healer_pr_required_label,
            ):
                continue
            self.store.set_healer_issue_state(
                issue_id=issue_id,
                state="queued",
                clear_lease=True,
            )
            self._post_issue_status(
                issue_id=issue_id,
                body=self._format_flow_status_comment(
                    "Approval's in, we're back on the move 🌊",
                    "Picking this up again now that the PR label is on the issue.",
                    [
                        f"Status: `queued`",
                        f"Approval label found: `{self.settings.healer_pr_required_label}`",
                    ],
                ),
            )
            resumed += 1
        return resumed

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
        self.store.set_healer_issue_state(issue_id=issue.issue_id, state="running")
        lease_stop = threading.Event()
        lease_thread = threading.Thread(
            target=self._lease_heartbeat,
            args=(issue.issue_id, lease_stop),
            daemon=True,
        )
        lease_thread.start()
        attempt_no = self.store.increment_healer_attempt(issue.issue_id)
        prediction = predict_lock_set(issue_text=f"{issue.title}\n{issue.body}")
        lock_result = self.dispatcher.acquire_prediction_locks(issue_id=issue.issue_id, lock_keys=prediction.keys)
        if not lock_result.acquired:
            logger.info(
                "Issue #%s blocked by prediction lock conflict (%s)",
                issue.issue_id,
                lock_result.reason,
            )
            final_state = self._backoff_or_fail(
                issue_id=issue.issue_id,
                attempt_no=attempt_no,
                failure_class="lock_conflict",
                failure_reason=lock_result.reason,
            )
            return

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
        actual_diff: list[str] = []
        test_summary: dict[str, object] = {}
        verifier_summary: dict[str, object] = {}
        failure_class = ""
        failure_reason = ""
        proposer_output_excerpt = ""
        issue_state = "failed"
        attempt_state = "failed"
        workspace = None
        try:
            workspace = self.workspace_manager.ensure_workspace(
                issue_id=issue.issue_id,
                title=issue.title,
            )
            self.workspace_manager.prepare_workspace(
                workspace_path=workspace.path,
                branch=workspace.branch,
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
                    "Yo, Flow's on it 👀",
                    "Kicking off a fresh pass now.",
                    [
                        f"Attempt: `{attempt_no}`",
                        f"Branch: `{workspace.branch}`",
                        f"Task kind: `{task_spec.task_kind}`",
                        f"Targets: `{', '.join(task_spec.output_targets) if task_spec.output_targets else 'inferred in code'}`",
                        f"Test gate mode: `{self.runner.test_gate_mode}`",
                    ],
                ),
            )
            targeted_tests = sorted(set(_TARGETED_TEST_RE.findall(issue.body or "")))
            learned_context = self.memory.build_prompt_context(
                issue_text=f"{issue.title}\n{issue.body}",
                predicted_lock_set=prediction.keys,
                last_failure_class=str(row.get("last_failure_class") or ""),
                task_kind=task_spec.task_kind,
                validation_profile=task_spec.validation_profile,
                output_targets=list(task_spec.output_targets),
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
                issue_state = self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class=run_result.failure_class,
                    failure_reason=run_result.failure_reason,
                )
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
            )
            verifier_summary = {"passed": verification.passed, "summary": verification.summary}
            if not verification.passed:
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

            if (
                self.settings.healer_pr_actions_require_approval
                and not self._issue_has_label(
                    issue_id=issue.issue_id,
                    label=self.settings.healer_pr_required_label,
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
                        "Nice, this one's looking clean ✅",
                        "Patch is in, checks passed, and I'm ready to keep it moving.",
                        [
                            "Status: `pr_pending_approval`",
                            f"Required label to continue: `{self.settings.healer_pr_required_label}`",
                            f"Test summary: `{run_result.test_summary}`",
                            f"Verifier: {verification.summary}",
                        ],
                        outro="Drop that approval label on here and I'll take it the rest of the way.",
                    ),
                )
                issue_state = "pr_pending_approval"
                attempt_state = "pr_pending_approval"
                logger.info("Issue #%s is waiting for PR approval label", issue.issue_id)
                return

            commit_ok, commit_reason = self._commit_and_push(workspace.path, issue_id=issue.issue_id, branch=workspace.branch)
            if not commit_ok:
                failure_class = "push_failed"
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
                    failure_class="push_failed",
                    failure_reason=commit_reason,
                )
                return

            pr = self.tracker.open_or_update_pr(
                issue_id=issue.issue_id,
                branch=workspace.branch,
                title=f"healer: fix issue #{issue.issue_id} - {issue.title[:80]}",
                body=(
                    f"Automated healer proposal for issue #{issue.issue_id}.\n\n"
                    f"- Verifier: passed\n"
                    f"- Targeted/full test gates: {run_result.test_summary}\n"
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
                    "PR is up and cruising 🚀",
                    "I opened or updated the PR for this issue.",
                    [
                        f"PR: #{pr.number}",
                        f"URL: {pr.html_url}",
                        f"Test summary: `{run_result.test_summary}`",
                    ],
                ),
            )
            issue_state = "pr_open"
            attempt_state = "pr_open"
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
            self.store.release_healer_locks(issue_id=issue.issue_id)
            if workspace is not None:
                self._cleanup_workspace(issue_id=issue.issue_id, state=issue_state, workspace_path=workspace.path)
            logger.info("Issue #%s attempt finished with state=%s", issue.issue_id, attempt_state)
            if attempt_state == "failed" and failure_class:
                self._post_issue_status(
                    issue_id=issue.issue_id,
                    body=self._format_flow_status_comment(
                        "Quick heads-up: this pass hit a snag ⚠️",
                        None,
                        [
                            f"Attempt state: `{attempt_state}`",
                            f"Failure class: `{failure_class}`",
                            f"Reason: {failure_reason}",
                        ],
                        outro="I saved the failure details so the next pass has better context.",
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

        required_labels = [
            str(label).strip()
            for label in self.settings.healer_issue_required_labels
            if str(label).strip()
        ]
        missing_labels = [
            label for label in required_labels if label.lower() not in remote_labels
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
        return True

    def _issue_has_label(self, *, issue_id: str, label: str) -> bool:
        requested_label = (label or "").strip()
        if not requested_label:
            return True
        target = requested_label.lower()
        try:
            snapshot = self.tracker.get_issue(issue_id=issue_id)
            if isinstance(snapshot, dict):
                labels = {
                    str(entry or "").strip().lower()
                    for entry in (snapshot.get("labels") or [])
                    if str(entry or "").strip()
                }
                if target in labels:
                    return True
        except Exception as exc:
            logger.warning(
                "Failed to check approval label on issue #%s from issue endpoint; using fallback: %s",
                issue_id,
                exc,
            )

        return self.tracker.issue_has_label(issue_id=issue_id, label=requested_label)

    def _lease_heartbeat(self, issue_id: str, stop_event: threading.Event) -> None:
        interval = max(15.0, float(self.dispatcher.lease_seconds) / 2.0)
        while not stop_event.wait(interval):
            renewed = self.store.renew_healer_issue_lease(
                issue_id=issue_id,
                worker_id=self.worker_id,
                lease_seconds=self.dispatcher.lease_seconds,
            )
            if not renewed:
                logger.warning("Lease heartbeat stopped for issue #%s; lease could not be renewed.", issue_id)
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
        is_always_requeue = is_infra or (failure_class in _ALWAYS_REQUEUE_FAILURE_CLASSES)

        if is_always_requeue:
            if is_infra:
                delay = max(15, min(300, int(self.settings.healer_backoff_initial_seconds)))
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
                    "Auto-retrying this one 🔁",
                    "This failure class is configured to requeue automatically.",
                    [
                        f"Attempt: `{attempt_no}`",
                        f"Failure class: `{failure_class}`",
                        f"Reason: {failure_reason}",
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
        backoff_until = (datetime.now(UTC) + timedelta(seconds=delay)).strftime("%Y-%m-%d %H:%M:%S")
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="queued",
            backoff_until=backoff_until,
            last_failure_class=failure_class,
            last_failure_reason=failure_reason[:500],
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
                "Queueing another pass 🔁",
                "This attempt failed, but we're still under retry budget.",
                [
                    f"Attempt: `{attempt_no}`",
                    f"Failure class: `{failure_class}`",
                    f"Reason: {failure_reason}",
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

    def _post_issue_status(self, *, issue_id: str, body: str) -> None:
        try:
            self.tracker.add_issue_comment(issue_id=issue_id, body=body)
        except Exception as exc:
            logger.warning("Failed to post issue comment for issue #%s: %s", issue_id, exc)

    @staticmethod
    def _format_flow_status_comment(
        title: str,
        intro: str | None,
        bullets: list[str],
        *,
        outro: str | None = None,
    ) -> str:
        lines = [title.strip(), ""]
        if intro:
            lines.extend([intro.strip(), ""])
        lines.extend(f"- {item}" for item in bullets if item.strip())
        if outro:
            lines.extend(["", outro.strip()])
        lines.extend(["", "-- Flow 🌊"])
        return "\n".join(lines)

    def _cleanup_workspace(self, *, issue_id: str, state: str, workspace_path: Path) -> None:
        try:
            self.workspace_manager.remove_workspace(workspace_path=workspace_path)
        except Exception as exc:
            logger.warning("Failed to clean workspace for issue #%s: %s", issue_id, exc)
            return
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state=state,
            workspace_path="",
            branch_name="",
        )

    @staticmethod
    def _commit_and_push(workspace: Path, *, issue_id: str, branch: str) -> tuple[bool, str]:
        add = subprocess.run(
            ["git", "-C", str(workspace), "add", "-A"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if add.returncode != 0:
            return False, (add.stderr or add.stdout or "git add failed").strip()

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

        push = subprocess.run(
            ["git", "-C", str(workspace), "push", "-u", "origin", branch],
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
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
