from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from datetime import UTC, datetime, timedelta
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
from .healer_tracker import GitHubHealerTracker, HealerIssue
from .healer_verifier import HealerVerifier
from .protocols import ConnectorProtocol
from .store import SQLiteStore

logger = logging.getLogger("apple_flow.healer_loop")

_TARGETED_TEST_RE = re.compile(r"\btests/[A-Za-z0-9_./\-]*test[A-Za-z0-9_./\-]*\.py\b")
_FLOW_COMMENT_PERSONA = (
    "Laid-back tech bro vibes, light emoji use, concise status updates, "
    "and always sign off with '-- Flow 🌊'."
)


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
        )
        self.runner = HealerRunner(
            connector=connector,
            timeout_seconds=settings.healer_max_wall_clock_seconds_per_issue,
            test_gate_mode=settings.healer_test_gate_mode,
        )
        self.verifier = HealerVerifier(connector=connector)
        self.reviewer = HealerReviewer(connector=connector)
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
        self._ingest_ready_issues()
        self._reconcile_pr_outcomes()
        resumed_approved = self._resume_approved_pending_prs()
        self._ingest_pr_feedback()
        if self._circuit_breaker_open() and resumed_approved == 0:
            logger.warning("Healer circuit breaker open; skipping this cycle.")
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
                if comment_id > last_issue_comment_id and body and author != self_actor:
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
                if review_id > last_review_id and body and author != self_actor:
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
                if comment_id > last_review_comment_id and body and author != self_actor:
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
            if not self.tracker.issue_has_label(
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
        self.store.set_healer_issue_state(issue_id=issue.issue_id, state="running")
        attempt_no = self.store.increment_healer_attempt(issue.issue_id)
        prediction = predict_lock_set(issue_text=f"{issue.title}\n{issue.body}")
        lock_result = self.dispatcher.acquire_prediction_locks(issue_id=issue.issue_id, lock_keys=prediction.keys)
        if not lock_result.acquired:
            self._backoff_or_fail(
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
        )
        actual_diff: list[str] = []
        test_summary: dict[str, object] = {}
        verifier_summary: dict[str, object] = {}
        failure_class = ""
        failure_reason = ""
        final_state = "failed"
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
            )
            self._post_issue_status(
                issue_id=issue.issue_id,
                body=self._format_flow_status_comment(
                    "Yo, Flow's on it 👀",
                    "Kicking off a fresh pass now.",
                    [
                        f"Attempt: `{attempt_no}`",
                        f"Branch: `{workspace.branch}`",
                        f"Test gate mode: `{self.runner.test_gate_mode}`",
                    ],
                ),
            )
            targeted_tests = sorted(set(_TARGETED_TEST_RE.findall(issue.body or "")))
            learned_context = self.memory.build_prompt_context(
                issue_text=f"{issue.title}\n{issue.body}",
                predicted_lock_set=prediction.keys,
                last_failure_class=str(row.get("last_failure_class") or ""),
            )
            feedback_context = str(row.get("feedback_context") or "").strip()
            run_result = self.runner.run_attempt(
                issue_id=issue.issue_id,
                issue_title=issue.title,
                issue_body=issue.body,
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
            if not run_result.success:
                failure_class = run_result.failure_class
                failure_reason = run_result.failure_reason
                self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class=run_result.failure_class,
                    failure_reason=run_result.failure_reason,
                )
                final_state = "failed"
                return

            upgrade = self.dispatcher.upgrade_locks(
                issue_id=issue.issue_id,
                lock_keys=diff_paths_to_lock_keys(run_result.diff_paths),
            )
            if not upgrade.acquired:
                failure_class = "lock_upgrade_conflict"
                failure_reason = upgrade.reason
                self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class="lock_upgrade_conflict",
                    failure_reason=upgrade.reason,
                )
                final_state = "failed"
                return

            verification = self.verifier.verify(
                issue_id=issue.issue_id,
                issue_title=issue.title,
                issue_body=issue.body,
                diff_paths=run_result.diff_paths,
                test_summary=run_result.test_summary,
                proposer_output=run_result.proposer_output,
                learned_context=learned_context,
            )
            verifier_summary = {"passed": verification.passed, "summary": verification.summary}
            if not verification.passed:
                failure_class = "verifier_failed"
                failure_reason = verification.summary
                self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class="verifier_failed",
                    failure_reason=verification.summary,
                )
                final_state = "failed"
                return

            if (
                self.settings.healer_pr_actions_require_approval
                and not self.tracker.issue_has_label(
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
                final_state = "pr_pending_approval"
                return

            commit_ok, commit_reason = self._commit_and_push(workspace.path, issue_id=issue.issue_id, branch=workspace.branch)
            if not commit_ok:
                failure_class = "push_failed"
                failure_reason = commit_reason
                self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class="push_failed",
                    failure_reason=commit_reason,
                )
                final_state = "failed"
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
                self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class="pr_open_failed",
                    failure_reason="Failed to create/update pull request.",
                )
                final_state = "failed"
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
            final_state = "pr_open"
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
            self.store.finish_healer_attempt(
                attempt_id=attempt_id,
                state=final_state,
                actual_diff_set=actual_diff,
                test_summary=test_summary,
                verifier_summary=verifier_summary,
                failure_class=failure_class,
                failure_reason=failure_reason,
            )
            self.memory.maybe_record_lesson(
                issue=issue,
                attempt_id=attempt_id,
                final_state=final_state,
                predicted_lock_set=prediction.keys,
                actual_diff_set=actual_diff,
                test_summary=test_summary,
                verifier_summary=verifier_summary,
                failure_class=failure_class,
                failure_reason=failure_reason,
            )
            self.store.release_healer_locks(issue_id=issue.issue_id)
            if final_state == "failed" and failure_class:
                self._post_issue_status(
                    issue_id=issue.issue_id,
                    body=self._format_flow_status_comment(
                        "Quick heads-up: this pass hit a snag ⚠️",
                        None,
                        [
                            f"Attempt state: `{final_state}`",
                            f"Failure class: `{failure_class}`",
                            f"Reason: {failure_reason}",
                        ],
                        outro="I saved the failure details so the next pass has better context.",
                    ),
                )

    def _backoff_or_fail(
        self,
        *,
        issue_id: str,
        attempt_no: int,
        failure_class: str,
        failure_reason: str,
    ) -> None:
        if attempt_no >= self.settings.healer_retry_budget:
            self.store.set_healer_issue_state(
                issue_id=issue_id,
                state="failed",
                last_failure_class=failure_class,
                last_failure_reason=failure_reason[:500],
                clear_lease=True,
            )
            return

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

    def _circuit_breaker_open(self) -> bool:
        window = max(5, self.settings.healer_circuit_breaker_window)
        attempts = self.store.list_recent_healer_attempts(limit=window)
        if len(attempts) < window:
            return False
        failures = 0
        for attempt in attempts:
            state = str(attempt.get("state") or "").lower()
            if state not in {"pr_open", "resolved", "pr_pending_approval"}:
                failures += 1
        failure_rate = failures / float(max(1, len(attempts)))
        return failure_rate >= self.settings.healer_circuit_breaker_failure_rate

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
