from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import signal
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .config import RelaySettings
from .docker_runtime import docker_idle_shutdown_enabled, maybe_shutdown_idle_docker_runtime
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
from .healer_swarm import HealerSwarm, SwarmRecoveryOutcome, SwarmRecoveryPlan, build_connector_subagent_backend
from .healer_scan import FlowHealerScanner
from .healer_tracker import GitHubHealerTracker, HealerIssue, PullRequestDetails, PullRequestResult
from .healer_task_spec import HealerTaskSpec, compile_task_spec, lint_issue_contract
from .healer_triage import classify_failure_domain, classify_failure_family
from .healer_verifier import HealerVerifier
from .language_strategies import UnsupportedLanguageError
from .protocols import ConnectorProtocol
from .store import SQLiteStore

logger = logging.getLogger("apple_flow.healer_loop")

_TARGETED_TEST_RE = re.compile(
    r"\btests/[A-Za-z0-9_./\-]*test[A-Za-z0-9_./\-]*\.py\b"
)
_STATE_COUNTER_TOKEN_RE = re.compile(r"[^a-z0-9]+")
_FLOW_COMMENT_PERSONA = (
    "Professional, concise status updates in Markdown, "
    "and always sign off with '-- Flow Healer'."
)
_SWARM_STICKY_STATUSES = {"swarm_analyzing", "swarm_repairing"}
_INFRA_FAILURE_CLASSES = {
    "connector_unavailable",
    "connector_runtime_error",
    "github_api_error",
    "github_auth_missing",
    "github_network_error",
    "github_rate_limited",
    "infra_pause",
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
    "scope_violation",
}
_EXECUTION_CONTRACT_FAILURE_CLASSES = {
    "empty_diff",
    "malformed_diff",
    "no_patch",
    "no_workspace_change",
    "patch_apply_failed",
}
_QUARANTINE_NEUTRAL_FAILURE_CLASSES = {"interrupted", "lease_expired"}
_STUCK_PR_STATES = {"blocked", "dirty", "has_failure", "behind"}
_RETRIABLE_CI_FAILURE_BUCKETS = {"lint", "setup", "test", "typecheck"}
_AGENT_BLOCKED_LABEL = "agent:blocked"
_OUTCOME_LABEL_DONE_CODE = "healer:done-code"
_OUTCOME_LABEL_DONE_ARTIFACT = "healer:done-artifact"
_OUTCOME_LABEL_NEEDS_CLARIFICATION = "healer:needs-clarification"
_OUTCOME_LABEL_BLOCKED_ENVIRONMENT = "healer:blocked-environment"
_OUTCOME_LABEL_RETRY_EXHAUSTED = "healer:retry-exhausted"
_OUTCOME_LABELS = (
    _OUTCOME_LABEL_DONE_CODE,
    _OUTCOME_LABEL_DONE_ARTIFACT,
    _OUTCOME_LABEL_NEEDS_CLARIFICATION,
    _OUTCOME_LABEL_BLOCKED_ENVIRONMENT,
    _OUTCOME_LABEL_RETRY_EXHAUSTED,
)
_SQL_VALIDATION_COMMAND_RE = re.compile(
    r"(?:\./scripts/healer_validate\.sh\s+db\b|scripts/flow_healer_sql_validate\.py\b)",
    re.IGNORECASE,
)

_FAILURE_CLASS_STRATEGY: dict[str, dict[str, object]] = {
    "tests_failed":          {"backoff_multiplier": 0.5, "feedback_hint": "Previous attempt's tests failed. Focus on the failing test output and adjust the fix."},
    "verifier_failed":       {"backoff_multiplier": 1.5, "feedback_hint": "The verifier rejected the previous fix. Address the root cause, not symptoms."},
    "push_failed":           {"backoff_multiplier": 2.0, "feedback_hint": "Push failed on last attempt, likely transient."},
    "push_non_fast_forward": {"backoff_multiplier": 1.0, "feedback_hint": "The managed issue branch diverged remotely. Refresh the branch state and retry from the latest managed base."},
    "pr_open_failed":        {"backoff_multiplier": 2.0, "feedback_hint": "Could not open PR last time."},
    "github_auth_missing":   {"backoff_multiplier": 2.0, "feedback_hint": "GitHub token was missing or invalid while opening the PR."},
    "github_network_error":  {"backoff_multiplier": 1.5, "feedback_hint": "GitHub network call failed while opening the PR."},
    "github_api_error":      {"backoff_multiplier": 1.5, "feedback_hint": "GitHub API rejected the PR open request."},
    "lock_upgrade_conflict": {"backoff_multiplier": 1.0, "feedback_hint": "Previous fix expanded beyond predicted scope. Keep changes narrow."},
    "scope_violation":       {"backoff_multiplier": 1.0, "feedback_hint": "Previous attempt edited files outside the declared output targets. Keep the patch strictly scoped."},
    "preflight_failed":      {"backoff_multiplier": 1.0, "feedback_hint": "Environment preflight failed. Wait for the runtime/tooling lane to recover before retrying."},
    "generated_artifact_contamination": {"backoff_multiplier": 1.0, "feedback_hint": "Previous attempt left generated artifacts in the worktree. Clean workspace noise before retrying."},
    "ci_failed":            {"backoff_multiplier": 0.5, "feedback_hint": "Remote CI failed on the open PR. Fix the failing checks on the existing branch and update the same PR."},
    "infra_pause":          {"backoff_multiplier": 1.0, "feedback_hint": "Infrastructure failed before validation could confirm the patch. Repair the local runtime and wait for the pause window to clear before retrying."},
    "swarm_quarantine":     {"backoff_multiplier": 1.0, "feedback_hint": "Swarm quarantined the attempt because another autonomous edit would be speculative. Clear the blocker before retrying."},
}
_FAILURE_DOMAIN_STRATEGY: dict[str, dict[str, object]] = {
    "infra": {
        "backoff_multiplier": 1.0,
        "feedback_hint": "Failure domain is infrastructure. Stabilize runtime/tooling connectivity before another mutation-heavy retry.",
    },
    "contract": {
        "backoff_multiplier": 0.75,
        "feedback_hint": "Failure domain is execution contract. Tighten diff/patch format and output contract before retrying.",
    },
    "code": {
        "backoff_multiplier": 1.0,
        "feedback_hint": "",
    },
    "unknown": {
        "backoff_multiplier": 1.0,
        "feedback_hint": "Failure domain is unclear. Capture more diagnostics before broad retries.",
    },
}


_FAILURE_USER_HINTS: dict[str, str] = {
    "no_patch": (
        "The AI agent could not produce file changes. "
        "Try adding an explicit `Required code outputs:` section to the issue body."
    ),
    "no_workspace_change": (
        "The AI agent could not produce file changes. "
        "Try adding an explicit `Required code outputs:` section to the issue body."
    ),
    "empty_diff": (
        "The AI agent could not produce file changes. "
        "Try adding an explicit `Required code outputs:` section to the issue body."
    ),
    "connector_unavailable": (
        "The AI connector is unavailable. "
        "Ensure `codex` is installed and `GITHUB_TOKEN` is set."
    ),
    "github_auth_missing": (
        "GitHub token is missing or invalid for this run. "
        "Set `GITHUB_TOKEN` via `service.env_file` or environment variables."
    ),
    "github_api_error": (
        "GitHub rejected a mutation request (for example PR creation). "
        "Check token scope, branch state, and repository permissions."
    ),
    "github_network_error": (
        "GitHub could not be reached over the network. "
        "Retry once connectivity is restored."
    ),
    "ci_failed": (
        "Remote CI failed on the open pull request. "
        "Use the failing checks to update the existing branch and PR."
    ),
    "tests_failed": (
        "The proposed fix did not pass tests. See test output above for details."
    ),
    "verifier_failed": (
        "The AI verifier rejected the fix as potentially incorrect. Manual review recommended."
    ),
    "infra_pause": (
        "Automation paused because infrastructure failed before validation reached the requested code path. Repair the local runtime and retry after the pause window."
    ),
    "swarm_quarantine": (
        "Swarm quarantined this attempt because another autonomous edit would be speculative. Clear the blocker before retrying."
    ),
    "patch_apply_failed": (
        "The generated patch could not be applied cleanly. This may resolve on retry."
    ),
    "diff_limit_exceeded": (
        "The proposed change was too large. Break this issue into smaller tasks."
    ),
}


def _failure_user_hint(failure_class: str, *, issue_body: str = "") -> str:
    normalized = str(failure_class or "").strip()
    hint = _FAILURE_USER_HINTS.get(normalized, "")
    issue_text = str(issue_body or "").lower()
    if normalized in {"no_patch", "no_workspace_change", "empty_diff"}:
        has_required_outputs = "required code outputs:" in issue_text
        has_validation = "validation:" in issue_text
        if has_required_outputs and has_validation:
            return (
                "The AI agent returned no usable file changes despite a structured issue contract. "
                "Retrying with stricter patch guidance."
            )
        if has_required_outputs:
            return (
                "The AI agent returned no usable file changes. "
                "The output targets are present, so add or tighten a `Validation:` section if the retry keeps stalling."
            )
    return hint


def _minutes_since(timestamp_str: str) -> float:
    """Return minutes elapsed since an ISO-8601 / SQLite CURRENT_TIMESTAMP string."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return (datetime.now(tz=UTC) - dt).total_seconds() / 60.0
    except (ValueError, TypeError):
        return 0.0


def _seconds_until_utc_timestamp(timestamp_str: str) -> int:
    text = str(timestamp_str or "").strip()
    if not text:
        return 0
    try:
        target = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if target.tzinfo is None:
            target = target.replace(tzinfo=UTC)
        remaining = int((target - datetime.now(tz=UTC)).total_seconds())
        return max(0, remaining)
    except (ValueError, TypeError):
        return 0


def _state_counter_token(value: str, *, fallback: str = "unknown") -> str:
    normalized = _STATE_COUNTER_TOKEN_RE.sub("_", str(value or "").strip().lower()).strip("_")
    if normalized:
        return normalized
    return _STATE_COUNTER_TOKEN_RE.sub("_", str(fallback or "unknown").strip().lower()).strip("_") or "unknown"


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
        connectors_by_backend: dict[str, ConnectorProtocol] | None = None,
        connector_routing_mode: str = "single_backend",
        code_connector_backend: str = "exec",
        non_code_connector_backend: str = "app_server",
    ) -> None:
        self.settings = settings
        self.store = store
        self.connector = connector
        self.connector_routing_mode = str(connector_routing_mode or "single_backend")
        self.code_connector_backend = str(code_connector_backend or "exec")
        self.non_code_connector_backend = str(non_code_connector_backend or "app_server")
        self.connectors_by_backend: dict[str, ConnectorProtocol] = dict(connectors_by_backend or {})
        if not self.connectors_by_backend:
            default_backend = _default_backend_for_connector(connector)
            self.connectors_by_backend[default_backend] = connector
        elif all(existing is not connector for existing in self.connectors_by_backend.values()):
            default_backend = _default_backend_for_connector(connector)
            self.connectors_by_backend.setdefault(default_backend, connector)
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
        self.runners_by_backend: dict[str, HealerRunner] = {}
        self.verifiers_by_backend: dict[str, HealerVerifier] = {}
        self.reviewers_by_backend: dict[str, HealerReviewer] = {}
        self.swarms_by_backend: dict[str, HealerSwarm] = {}
        self.preflight_by_backend: dict[str, HealerPreflight] = {}
        for backend, backend_connector in self.connectors_by_backend.items():
            runner = HealerRunner(
                connector=backend_connector,
                timeout_seconds=settings.healer_max_wall_clock_seconds_per_issue,
                test_gate_mode=settings.healer_test_gate_mode,
                local_gate_policy=settings.healer_local_gate_policy,
                completion_artifact_mode=settings.healer_completion_artifact_mode,
                language=settings.healer_language,
                docker_image=settings.healer_docker_image,
                test_command=settings.healer_test_command,
                install_command=settings.healer_install_command,
                default_runtime_profile=str(getattr(settings, "healer_app_default_runtime_profile", "") or ""),
                app_runtime_profiles=getattr(settings, "healer_app_runtime_profiles", {}),
                auto_clean_generated_artifacts=settings.healer_auto_clean_generated_artifacts,
            )
            self.runners_by_backend[backend] = runner
            self.verifiers_by_backend[backend] = HealerVerifier(connector=backend_connector, timeout_seconds=300)
            self.reviewers_by_backend[backend] = HealerReviewer(connector=backend_connector)
            self.swarms_by_backend[backend] = HealerSwarm(
                build_connector_subagent_backend(backend_connector),
                max_parallel_agents=max(1, int(getattr(settings, "healer_swarm_max_parallel_agents", 4))),
                max_repair_cycles_per_attempt=max(
                    1,
                    int(getattr(settings, "healer_swarm_max_repair_cycles_per_attempt", 1)),
                ),
                analysis_timeout_seconds=max(
                    30,
                    int(getattr(settings, "healer_swarm_analysis_timeout_seconds", 240)),
                ),
                recovery_timeout_seconds=max(
                    60,
                    int(getattr(settings, "healer_swarm_recovery_timeout_seconds", 420)),
                ),
            )
            self.preflight_by_backend[backend] = HealerPreflight(
                store=store,
                runner=runner,
                repo_path=self.repo_path,
            )
        primary_backend = self._primary_backend()
        self.runner = self.runners_by_backend[primary_backend]
        self.verifier = self.verifiers_by_backend[primary_backend]
        self.reviewer = self.reviewers_by_backend[primary_backend]
        raw_scan_labels = getattr(settings, "healer_scan_default_labels", ["kind:scan"])
        if isinstance(raw_scan_labels, list):
            scan_default_labels = [str(label).strip() for label in raw_scan_labels if str(label).strip()]
        else:
            single_label = str(raw_scan_labels or "").strip()
            scan_default_labels = [single_label] if single_label else ["kind:scan"]
        self.scanner = FlowHealerScanner(
            repo_path=self.repo_path,
            store=store,
            tracker=self.tracker,
            severity_threshold=str(getattr(settings, "healer_scan_severity_threshold", "medium")),
            max_issues_per_run=int(getattr(settings, "healer_scan_max_issues_per_run", 5)),
            default_labels=scan_default_labels,
            enable_issue_creation=bool(getattr(settings, "healer_scan_enable_issue_creation", False)),
        )
        self._last_scan_started_at = 0.0
        self.reconciler = HealerReconciler(
            store=store,
            workspace_manager=self.workspace_manager,
            current_worker_id=self.worker_id,
            swarm_orphan_subagent_ttl_seconds=max(
                60,
                int(getattr(settings, "healer_swarm_orphan_subagent_ttl_seconds", 900)),
            ),
        )
        self.memory = HealerMemoryService(
            store=store,
            enabled=settings.healer_learning_enabled,
        )
        self.preflight = self.preflight_by_backend[primary_backend]
        self._last_housekeeping_at = 0.0
        self._last_blocked_label_repair_at = 0.0
        self._sticky_runtime_status = ""
        self._sticky_runtime_issue_id = ""

    def _primary_backend(self) -> str:
        if self.connector_routing_mode == "exec_for_code":
            return self.code_connector_backend
        for backend, existing in self.connectors_by_backend.items():
            if existing is self.connector:
                return backend
        if self.connectors_by_backend:
            return next(iter(self.connectors_by_backend))
        return _default_backend_for_connector(self.connector)

    def _select_backend_for_task(self, task_spec: HealerTaskSpec) -> str:
        if self.connector_routing_mode != "exec_for_code":
            return self._primary_backend()
        normalized_task_kind = str(task_spec.task_kind or "").strip().lower()
        if normalized_task_kind in {"docs", "research", "artifact", "artifact_only"}:
            return self.non_code_connector_backend
        return self.code_connector_backend

    def _pipeline_for_task(
        self,
        task_spec: HealerTaskSpec,
    ) -> tuple[str, ConnectorProtocol, HealerRunner, HealerVerifier, HealerReviewer, HealerSwarm, HealerPreflight]:
        backend = self._select_backend_for_task(task_spec)
        connector = self.connectors_by_backend.get(backend, self.connector)
        runner = self.runners_by_backend.get(backend, self.runner)
        verifier = self.verifiers_by_backend.get(backend, self.verifier)
        reviewer = self.reviewers_by_backend.get(backend, self.reviewer)
        swarm = self.swarms_by_backend.get(backend)
        preflight = self.preflight_by_backend.get(backend, self.preflight)
        if swarm is None:
            swarm = HealerSwarm(
                build_connector_subagent_backend(connector),
                max_parallel_agents=max(1, int(getattr(self.settings, "healer_swarm_max_parallel_agents", 4))),
                max_repair_cycles_per_attempt=max(
                    1,
                    int(getattr(self.settings, "healer_swarm_max_repair_cycles_per_attempt", 1)),
                ),
                analysis_timeout_seconds=max(
                    30,
                    int(getattr(self.settings, "healer_swarm_analysis_timeout_seconds", 240)),
                ),
                recovery_timeout_seconds=max(
                    60,
                    int(getattr(self.settings, "healer_swarm_recovery_timeout_seconds", 420)),
                ),
            )
            self.swarms_by_backend[backend] = swarm
        return backend, connector, runner, verifier, reviewer, swarm, preflight

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
                self.store.update_runtime_status(
                    status="error",
                    last_error=str(exc),
                    touch_heartbeat=True,
                    touch_tick_finished=True,
                )
                logger.exception("Autonomous healer tick failed: %s", exc)
            await self._sleep_until_next_tick(is_shutdown=is_shutdown)

    async def _sleep_until_next_tick(self, *, is_shutdown: Callable[[], bool]) -> None:
        remaining = max(5.0, float(self.settings.healer_poll_interval_seconds))
        pulse_interval = max(15.0, float(getattr(self.settings, "healer_pulse_interval_seconds", 60.0)))
        while remaining > 0 and not is_shutdown():
            delay = min(remaining, pulse_interval)
            await asyncio.sleep(delay)
            remaining -= delay
            if remaining > 0 and not is_shutdown():
                await asyncio.to_thread(self._record_worker_heartbeat, status="idle")

    def _tick_once(self) -> None:
        self.store.update_runtime_status(
            status="ticking",
            last_error="",
            touch_heartbeat=True,
            touch_tick_started=True,
        )
        self._record_worker_heartbeat(status="ticking")
        reconcile_summary = self._maybe_run_housekeeping()
        if reconcile_summary is not None:
            self._record_reconcile_summary(reconcile_summary)
        self._maybe_recycle_helpers()
        if self.store.get_state("healer_paused") == "true":
            logger.info("Autonomous healer paused via system command; housekeeping complete, skipping cycle.")
            self.store.update_runtime_status(status="paused", last_error="", touch_tick_finished=True)
            return
        if not bool(getattr(self.tracker, "enabled", False)):
            failure_class = "github_auth_missing"
            failure_reason = "GitHub tracker is disabled (missing token or repo slug); skipping cycle."
            self.store.set_states({"healer_tracker_available": "false"})
            self._record_tracker_error(failure_class=failure_class, failure_reason=failure_reason)
            logger.warning("Autonomous healer tracker unavailable; skipping cycle. %s", failure_reason)
            self.store.update_runtime_status(status="tracker_unavailable", last_error=failure_reason, touch_tick_finished=True)
            return
        self.store.set_states({"healer_tracker_available": "true"})
        self._maybe_run_scan()
        self._ingest_ready_issues()
        self.preflight.refresh_all(force=False)
        active_pr_rows = self._list_active_pr_rows(include_blocked=True)
        open_pr_rows = [
            row for row in active_pr_rows if str(row.get("state") or "").strip().lower() == "pr_open"
        ]
        details_cache: dict[int, PullRequestDetails | None] = {}
        viewer_login = self.tracker.viewer_login().lower()
        self._reconcile_pr_outcomes(active_prs=active_pr_rows, details_cache=details_cache)
        active_pr_rows = self._list_active_pr_rows(include_blocked=True)
        open_pr_rows = [
            row for row in active_pr_rows if str(row.get("state") or "").strip().lower() == "pr_open"
        ]
        self._requeue_ci_failed_prs(active_prs=open_pr_rows)
        active_pr_rows = self._list_active_pr_rows(include_blocked=True)
        open_pr_rows = [
            row for row in active_pr_rows if str(row.get("state") or "").strip().lower() == "pr_open"
        ]
        self._auto_approve_open_prs(active_prs=open_pr_rows, details_cache=details_cache, viewer_login=viewer_login)
        merged = self._auto_merge_open_prs(active_prs=open_pr_rows, details_cache=details_cache)
        if merged:
            details_cache = {}
            self._reconcile_pr_outcomes(details_cache=details_cache, force_refresh=True)
            active_pr_rows = self._list_active_pr_rows(include_blocked=True)
            open_pr_rows = [
                row for row in active_pr_rows if str(row.get("state") or "").strip().lower() == "pr_open"
            ]
        resumed_approved = self._resume_approved_pending_prs()
        self._ingest_pr_feedback(active_prs=open_pr_rows, details_cache=details_cache, viewer_login=viewer_login)
        self._maybe_reconcile_blocked_issue_labels()
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
            self.store.update_runtime_status(status="cooldown", last_error="", touch_tick_finished=True)
            return
        if self._infra_pause_active():
            pause_until = self.store.get_state("healer_infra_pause_until") or ""
            pause_reason = self.store.get_state("healer_infra_pause_reason") or ""
            logger.warning(
                "Infra safety pause active; skipping claim cycle until %s (%s).",
                pause_until,
                pause_reason,
            )
            self.store.update_runtime_status(status="infra_pause", last_error=str(pause_reason or ""), touch_tick_finished=True)
            return
        connector_health = self._connector_health_snapshot()
        self._record_connector_health(connector_health)
        if not bool(connector_health.get("available")):
            logger.warning(
                "Healer connector unavailable; skipping claim cycle. reason=%s command=%s",
                str(connector_health.get("availability_reason") or ""),
                str(connector_health.get("configured_command") or ""),
            )
            self.store.update_runtime_status(
                status="connector_unavailable",
                last_error=str(connector_health.get("availability_reason") or ""),
                touch_tick_finished=True,
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
            self._reconcile_pr_outcomes(force_refresh=True)
            processed += 1
        self.store.update_runtime_status(status="idle", last_error="", touch_tick_finished=True)
        self._maybe_shutdown_idle_docker_runtime()

    def _maybe_run_housekeeping(self) -> dict[str, int] | None:
        interval = max(30.0, float(getattr(self.settings, "healer_housekeeping_interval_seconds", 300.0)))
        now = time.monotonic()
        last_housekeeping_at = float(getattr(self, "_last_housekeeping_at", 0.0))
        if last_housekeeping_at and (now - last_housekeeping_at) < interval:
            return None
        self._last_housekeeping_at = now
        return self.reconciler.reconcile()

    def _record_worker_heartbeat(
        self,
        *,
        status: str = "idle",
        issue_id: str = "",
        attempt_id: str = "",
        force_emit: bool = False,
    ) -> None:
        requested_status = str(status or "idle").strip() or "idle"
        sticky_status = str(getattr(self, "_sticky_runtime_status", "") or "").strip()
        sticky_issue_id = str(getattr(self, "_sticky_runtime_issue_id", "") or "").strip()
        if requested_status == "processing" and issue_id and issue_id == sticky_issue_id and sticky_status in _SWARM_STICKY_STATUSES:
            status = sticky_status
        else:
            status = requested_status
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        self.store.set_states(
            {
                "healer_active_worker_id": self.worker_id,
                "healer_active_worker_heartbeat_at": now,
            }
        )
        self.store.update_runtime_status(status=status, last_error="", touch_heartbeat=True)
        pulse_interval_minutes = max(0.25, float(getattr(self.settings, "healer_pulse_interval_seconds", 60.0)) / 60.0)
        last_pulse_at = str(self.store.get_state("healer_last_pulse_at") or "").strip()
        if not force_emit and last_pulse_at and _minutes_since(last_pulse_at) < pulse_interval_minutes:
            return
        message = f"Worker pulse: {status}."
        if issue_id:
            message += f" Active issue #{issue_id}."
        self.store.create_healer_event(
            event_type="worker_pulse",
            level="info",
            message=message,
            issue_id=issue_id,
            attempt_id=attempt_id,
            payload={
                "repo": self.settings.repo_name,
                "worker_id": self.worker_id,
                "status": status,
                "heartbeat_at": now,
            },
        )
        self.store.set_states({"healer_last_pulse_at": now})
        logger.info(
            "Worker pulse emitted (repo=%s status=%s issue=%s)",
            self.settings.repo_name,
            status,
            issue_id or "-",
        )

    def _set_sticky_runtime_status(self, *, issue_id: str, status: str) -> None:
        normalized_issue = str(issue_id or "").strip()
        normalized_status = str(status or "").strip()
        if normalized_issue and normalized_status in _SWARM_STICKY_STATUSES:
            self._sticky_runtime_issue_id = normalized_issue
            self._sticky_runtime_status = normalized_status

    def _clear_sticky_runtime_status(self, *, issue_id: str = "") -> None:
        normalized_issue = str(issue_id or "").strip()
        sticky_issue_id = str(getattr(self, "_sticky_runtime_issue_id", "") or "").strip()
        if normalized_issue and sticky_issue_id and normalized_issue != sticky_issue_id:
            return
        self._sticky_runtime_issue_id = ""
        self._sticky_runtime_status = ""

    def _record_reconcile_summary(self, summary: dict[str, int]) -> None:
        payload = {"healer_last_reconcile_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")}
        for key, value in summary.items():
            payload[f"healer_reconcile_{key}"] = str(max(0, int(value)))
        self.store.set_states(payload)

    def _maybe_shutdown_idle_docker_runtime(self) -> None:
        if not docker_idle_shutdown_enabled():
            return
        try:
            if maybe_shutdown_idle_docker_runtime():
                logger.info("Stopped idle Docker runtime after healer inactivity window elapsed.")
        except Exception as exc:
            logger.warning("Failed to stop idle Docker runtime: %s", exc)

    def _maybe_recycle_helpers(self) -> bool:
        requested_at = str(self.store.get_state("healer_helper_recycle_requested_at") or "").strip()
        if not requested_at:
            return False
        idle_only = str(self.store.get_state("healer_helper_recycle_idle_only") or "").strip().lower() == "true"
        active_rows = self.store.list_healer_issues(
            states=["claimed", "running", "verify_pending"],
            limit=max(1, int(self.settings.healer_max_concurrent_issues)),
        )
        if idle_only and active_rows:
            active_issue_ids = ", ".join(str(row.get("issue_id") or "") for row in active_rows if row.get("issue_id"))
            reason = (
                f"Deferred helper recycle requested at {requested_at}; "
                f"active issue processing is still in progress ({active_issue_ids or 'busy'})."
            )
            self.store.set_states(
                {
                    "healer_helper_recycle_status": "deferred_busy",
                    "healer_helper_recycle_reason": reason[:500],
                }
            )
            logger.info(reason)
            return False

        recycled_backends: list[str] = []
        closed: set[int] = set()
        for backend, connector in self.connectors_by_backend.items():
            if id(connector) in closed:
                continue
            try:
                connector.shutdown()
                recycled_backends.append(backend)
            except Exception as exc:
                logger.warning("Failed to recycle %s helper backend for repo %s: %s", backend, self.settings.repo_name, exc)
            closed.add(id(connector))
        summary = ", ".join(sorted(set(recycled_backends))) or "none"
        self.store.set_states(
            {
                "healer_helper_recycle_requested_at": "",
                "healer_helper_recycle_idle_only": "",
                "healer_helper_recycle_status": "completed",
                "healer_helper_recycle_reason": (
                    f"Recycled helper backends: {summary}. They will restart lazily on next use."
                ),
                "healer_helper_recycle_completed_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        logger.info(
            "Recycled helper backends for repo %s (idle_only=%s, requested_at=%s, backends=%s)",
            self.settings.repo_name,
            idle_only,
            requested_at,
            summary,
        )
        return True

    def _ingest_pr_feedback(
        self,
        active_prs: list[dict[str, object]] | None = None,
        *,
        details_cache: dict[int, PullRequestDetails | None] | None = None,
        viewer_login: str | None = None,
    ) -> None:
        active_prs = active_prs or self._list_active_pr_rows(include_blocked=False)
        self_actor = (viewer_login if viewer_login is not None else self.tracker.viewer_login()).lower()
        details_cache = details_cache if details_cache is not None else {}
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

    def _swarm_enabled_for_failure(self, failure_class: str) -> bool:
        if not bool(getattr(self.settings, "healer_swarm_enabled", False)):
            return False
        if str(getattr(self.settings, "healer_swarm_mode", "failure_repair") or "failure_repair").strip().lower() != "failure_repair":
            return False
        patterns = getattr(self.settings, "healer_swarm_trigger_failure_classes", None) or [
            "tests_failed",
            "verifier_failed",
            "no_workspace_change*",
            "patch_apply_failed",
            "malformed_diff",
            "scope_violation",
            "generated_artifact_contamination",
        ]
        normalized = str(failure_class or "").strip()
        for pattern in patterns:
            token = str(pattern or "").strip()
            if not token:
                continue
            if token.endswith("*") and normalized.startswith(token[:-1]):
                return True
            if normalized == token:
                return True
        return False

    def _codex_native_multi_agent_max_subagents(self) -> int:
        return max(1, int(getattr(self.settings, "healer_codex_native_multi_agent_max_subagents", 3)))

    def _codex_native_multi_agent_profile_for_task(
        self,
        *,
        selected_backend: str,
        task_spec: HealerTaskSpec,
        recovery: bool,
        count_skips: bool = False,
    ) -> str:
        if not bool(getattr(self.settings, "healer_codex_native_multi_agent_enabled", False)):
            return ""
        if str(selected_backend or "").strip().lower() != "exec":
            if count_skips:
                self._increment_state_counter("healer_codex_native_multi_agent_skipped_backend")
            return ""
        normalized_task_kind = str(task_spec.task_kind or "").strip().lower()
        if normalized_task_kind not in {"fix", "build", "edit"} or task_spec.validation_profile != "code_change":
            if count_skips:
                self._increment_state_counter("healer_codex_native_multi_agent_skipped_task_kind")
            return ""
        return "recovery" if recovery else "initial"

    def _native_codex_recovery_feedback_context(
        self,
        *,
        feedback_context: str,
        failure_class: str,
        failure_reason: str,
        proposer_output: str,
    ) -> str:
        parts = [feedback_context.strip()] if feedback_context.strip() else []
        parts.append(
            "[native_codex_recovery]\n"
            f"Failure class: {failure_class}\n"
            f"Failure reason: {failure_reason}\n"
            "Use native multi-agent delegation to re-check root cause before producing the final patch."
        )
        trimmed_output = str(proposer_output or "").strip()
        if trimmed_output:
            parts.append(f"Previous proposer output (truncated):\n{trimmed_output[:4000]}")
        return "\n\n".join(part for part in parts if part).strip()

    def _record_swarm_metrics(self, *, backend: str, outcome: SwarmRecoveryOutcome) -> None:
        self._increment_state_counter("healer_swarm_runs")
        self._increment_state_counter(f"healer_swarm_runs_backend_{backend}")
        self._increment_state_counter(f"healer_swarm_strategy_{outcome.strategy}")
        if outcome.recovered:
            self._increment_state_counter("healer_swarm_recovered")
            return
        self._increment_state_counter("healer_swarm_unrecovered")

    def _record_codex_native_multi_agent_attempt(self) -> None:
        self._increment_state_counter("healer_codex_native_multi_agent_attempts")

    def _record_codex_native_multi_agent_recovery_attempt(self, *, success: bool) -> None:
        self._increment_state_counter("healer_codex_native_multi_agent_recovery_attempts")
        if success:
            self._increment_state_counter("healer_codex_native_multi_agent_recovery_success")

    def _emit_swarm_event(
        self,
        *,
        event_type: str,
        message: str,
        issue_id: str,
        attempt_id: str,
        payload: dict[str, Any],
        level: str = "info",
    ) -> None:
        self.store.create_healer_event(
            event_type=event_type,
            level=level,
            message=message,
            issue_id=issue_id,
            attempt_id=attempt_id,
            payload=payload,
        )
        logger.info(
            "Swarm event emitted (repo=%s event=%s issue=%s attempt=%s)",
            self.settings.repo_name,
            event_type,
            issue_id or "-",
            attempt_id or "-",
        )

    def _post_swarm_started_comment(
        self,
        *,
        issue_id: str,
        attempt_no: int,
        failure_class: str,
        failure_reason: str,
    ) -> None:
        self._post_issue_status(
            issue_id=issue_id,
            body=self._format_flow_status_comment(
                "Swarm recovery started",
                f"Attempt {attempt_no} hit `{failure_class}` and is switching to recovery subagents.",
                [
                    f"Failure class: `{failure_class}`",
                    f"Reason: `{self._clean_comment_text(failure_reason, max_chars=220)}`",
                ],
            ),
        )

    def _post_swarm_finished_comment(
        self,
        *,
        issue_id: str,
        attempt_no: int,
        outcome: SwarmRecoveryOutcome,
    ) -> None:
        intro = (
            f"Attempt {attempt_no} was recovered by the swarm and is returning to the main fix flow."
            if outcome.recovered
            else f"Attempt {attempt_no} was not recovered by the swarm."
        )
        bullets = [
            f"Recovered: `{'yes' if outcome.recovered else 'no'}`",
            f"Strategy: `{outcome.strategy}`",
            f"Summary: `{self._clean_comment_text(outcome.summary, max_chars=220)}`",
        ]
        if outcome.failure_reason and not outcome.recovered:
            bullets.append(f"Failure: `{self._clean_comment_text(outcome.failure_reason, max_chars=220)}`")
        self._post_issue_status(
            issue_id=issue_id,
            body=self._format_flow_status_comment(
                "Swarm recovery finished",
                intro,
                bullets,
            ),
        )

    def _handle_swarm_telemetry(
        self,
        *,
        issue: HealerIssue,
        attempt_id: str,
        attempt_no: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        normalized_payload = dict(payload or {})
        normalized_payload.setdefault("attempt_no", attempt_no)
        normalized_payload.setdefault("worker_id", self.worker_id)
        level = "info"
        if event_type == "swarm_started":
            self._set_sticky_runtime_status(issue_id=issue.issue_id, status="swarm_analyzing")
            self._record_worker_heartbeat(
                status="swarm_analyzing",
                issue_id=issue.issue_id,
                attempt_id=attempt_id,
                force_emit=True,
            )
            self._post_swarm_started_comment(
                issue_id=issue.issue_id,
                attempt_no=attempt_no,
                failure_class=str(normalized_payload.get("failure_class") or ""),
                failure_reason=str(normalized_payload.get("failure_reason") or ""),
            )
            message = (
                "Swarm recovery started"
                f" for failure {str(normalized_payload.get('failure_class') or 'unknown')}."
            )
        elif event_type == "swarm_role_completed":
            role = str(normalized_payload.get("role") or "unknown")
            stage = str(normalized_payload.get("stage") or "analysis")
            success = bool(normalized_payload.get("success", False))
            level = "info" if success else "warning"
            message = f"Swarm {stage} role {role} completed ({'ok' if success else 'warning'})."
        elif event_type == "swarm_plan_ready":
            strategy = str(normalized_payload.get("strategy") or "repair")
            if strategy == "repair":
                self._set_sticky_runtime_status(issue_id=issue.issue_id, status="swarm_repairing")
                self._record_worker_heartbeat(
                    status="swarm_repairing",
                    issue_id=issue.issue_id,
                    attempt_id=attempt_id,
                    force_emit=True,
                )
            message = f"Swarm recovery plan ready ({strategy})."
        elif event_type == "swarm_finished":
            recovered = bool(normalized_payload.get("recovered", False))
            level = "info" if recovered else "warning"
            summary = self._clean_comment_text(normalized_payload.get("summary") or "", max_chars=180)
            message = (
                f"Swarm recovery finished ({'recovered' if recovered else 'unrecovered'})."
                + (f" {summary}" if summary else "")
            )
            self._post_swarm_finished_comment(
                issue_id=issue.issue_id,
                attempt_no=attempt_no,
                outcome=SwarmRecoveryOutcome(
                    recovered=recovered,
                    strategy=str(normalized_payload.get("strategy") or "repair"),
                    summary=str(normalized_payload.get("summary") or ""),
                    analyzer_results=(),
                    plan=SwarmRecoveryPlan(
                        strategy=str(normalized_payload.get("strategy") or "repair"),
                        summary=str(normalized_payload.get("summary") or ""),
                        root_cause="",
                        edit_scope=(),
                        targeted_tests=(),
                        validation_focus=(),
                    ),
                    failure_class=str(normalized_payload.get("failure_class") or ""),
                    failure_reason=str(normalized_payload.get("failure_reason") or ""),
                ),
            )
            self._clear_sticky_runtime_status(issue_id=issue.issue_id)
            self._record_worker_heartbeat(
                status="processing",
                issue_id=issue.issue_id,
                attempt_id=attempt_id,
                force_emit=True,
            )
        elif event_type == "swarm_role_timeout":
            role = str(normalized_payload.get("role") or "unknown")
            stage = str(normalized_payload.get("stage") or "analysis")
            level = "warning"
            message = f"Swarm {stage} role {role} timed out."
        elif event_type == "swarm_recovery_timeout":
            stage = str(normalized_payload.get("stage") or "analysis")
            level = "warning"
            message = f"Swarm recovery timed out during {stage}."
        else:
            message = f"Swarm event: {event_type}"
        self._emit_swarm_event(
            event_type=event_type,
            level=level,
            message=message,
            issue_id=issue.issue_id,
            attempt_id=attempt_id,
            payload=normalized_payload,
        )

    def _maybe_recover_with_native_codex(
        self,
        *,
        selected_backend: str,
        selected_runner: HealerRunner,
        issue: HealerIssue,
        task_spec: HealerTaskSpec,
        learned_context: str,
        feedback_context: str,
        failure_class: str,
        failure_reason: str,
        workspace: Path,
        targeted_tests: list[str],
        proposer_output: str = "",
    ) -> HealerRunResult | None:
        profile = self._codex_native_multi_agent_profile_for_task(
            selected_backend=selected_backend,
            task_spec=task_spec,
            recovery=True,
            count_skips=True,
        )
        if not profile:
            return None
        failure_domain = classify_failure_domain(
            failure_class=failure_class,
            failure_reason=failure_reason,
        )
        if failure_domain != "code":
            return None
        result = selected_runner.run_attempt(
            issue_id=issue.issue_id,
            issue_title=issue.title,
            issue_body=issue.body,
            task_spec=task_spec,
            learned_context=learned_context,
            feedback_context=self._native_codex_recovery_feedback_context(
                feedback_context=feedback_context,
                failure_class=failure_class,
                failure_reason=failure_reason,
                proposer_output=proposer_output,
            ),
            workspace=workspace,
            max_diff_files=self.settings.healer_max_diff_files,
            max_diff_lines=self.settings.healer_max_diff_lines,
            max_failed_tests_allowed=self.settings.healer_max_failed_tests_allowed,
            targeted_tests=targeted_tests,
            native_multi_agent_profile=profile,
            native_multi_agent_max_subagents=self._codex_native_multi_agent_max_subagents(),
        )
        self._record_codex_native_multi_agent_recovery_attempt(success=result.success)
        return result

    def _maybe_recover_with_swarm(
        self,
        *,
        selected_backend: str,
        selected_swarm: HealerSwarm,
        selected_runner: HealerRunner,
        issue: HealerIssue,
        attempt_id: str,
        attempt_no: int,
        task_spec: HealerTaskSpec,
        learned_context: str,
        feedback_context: str,
        failure_class: str,
        failure_reason: str,
        proposer_output: str,
        test_summary: dict[str, Any],
        verifier_summary: dict[str, Any],
        workspace_status: dict[str, Any],
        workspace: Path,
        targeted_tests: list[str],
    ) -> SwarmRecoveryOutcome | None:
        if not self._swarm_enabled_for_failure(failure_class):
            return None
        failure_domain = classify_failure_domain(
            failure_class=failure_class,
            failure_reason=failure_reason,
        )
        if failure_domain != "code":
            self._increment_state_counter("healer_swarm_skipped_domain")
            self._increment_state_counter(f"healer_swarm_skipped_domain_{failure_domain}")
            self._emit_swarm_event(
                event_type="swarm_skipped_domain",
                level="info",
                message=f"Swarm skipped for {failure_domain} failure domain.",
                issue_id=issue.issue_id,
                attempt_id=attempt_id,
                payload={
                    "failure_class": failure_class,
                    "failure_reason": failure_reason,
                    "failure_domain": failure_domain,
                },
            )
            return None
        telemetry_emitted = False

        def _telemetry_callback(event_type: str, payload: dict[str, Any]) -> None:
            nonlocal telemetry_emitted
            telemetry_emitted = True
            self._handle_swarm_telemetry(
                issue=issue,
                attempt_id=attempt_id,
                attempt_no=attempt_no,
                event_type=event_type,
                payload=payload,
            )

        try:
            outcome = selected_swarm.recover(
                issue_id=issue.issue_id,
                issue_title=issue.title,
                issue_body=issue.body,
                task_spec=task_spec,
                learned_context=learned_context,
                feedback_context=feedback_context,
                failure_class=failure_class,
                failure_reason=failure_reason,
                proposer_output=proposer_output,
                test_summary=test_summary,
                verifier_summary=verifier_summary,
                workspace_status=workspace_status,
                workspace=workspace,
                runner=selected_runner,
                max_diff_files=self.settings.healer_max_diff_files,
                max_diff_lines=self.settings.healer_max_diff_lines,
                max_failed_tests_allowed=self.settings.healer_max_failed_tests_allowed,
                targeted_tests=targeted_tests,
                telemetry_callback=_telemetry_callback,
            )
        except Exception as exc:
            if telemetry_emitted:
                self._handle_swarm_telemetry(
                    issue=issue,
                    attempt_id=attempt_id,
                    attempt_no=attempt_no,
                    event_type="swarm_finished",
                    payload={
                        "recovered": False,
                        "strategy": "repair",
                        "summary": "Swarm recovery aborted with an internal error.",
                        "failure_class": "swarm_runtime_error",
                        "failure_reason": str(exc),
                    },
                )
            raise
        self._record_swarm_metrics(backend=selected_backend, outcome=outcome)
        return outcome

    def _swarm_failure_override(
        self,
        *,
        base_failure_class: str,
        base_failure_reason: str,
        swarm_outcome: SwarmRecoveryOutcome | None,
    ) -> tuple[str, str]:
        if swarm_outcome is None or swarm_outcome.recovered:
            return base_failure_class, base_failure_reason
        reason = (
            str(swarm_outcome.failure_reason or "").strip()
            or str(swarm_outcome.summary or "").strip()
            or str(base_failure_reason or "").strip()
        )
        strategy = str(swarm_outcome.strategy or "").strip().lower()
        if strategy == "infra_pause":
            if self._swarm_outcome_looks_infra(
                summary=str(swarm_outcome.summary or ""),
                reason=reason,
                root_cause=str(swarm_outcome.plan.root_cause or ""),
            ):
                return "infra_pause", reason
            return "swarm_quarantine", reason
        if strategy == "quarantine":
            if self._swarm_outcome_looks_infra(
                summary=str(swarm_outcome.summary or ""),
                reason=reason,
                root_cause=str(swarm_outcome.plan.root_cause or ""),
            ):
                return "infra_pause", reason
            return "swarm_quarantine", reason
        return base_failure_class, reason

    @staticmethod
    def _swarm_outcome_looks_infra(*, summary: str, reason: str, root_cause: str) -> bool:
        haystack = " ".join(
            part.strip().lower()
            for part in (summary, reason, root_cause)
            if part and part.strip()
        )
        if not haystack:
            return False
        # Keep global infra pauses for genuine runtime outages only.
        # SQL/schema/migration failures inside a healthy local stack should stay quarantined per issue.
        non_infra_tokens = (
            "assertion",
            "constraint",
            "migration",
            "policy",
            "schema",
            "sql",
            "table",
            "column",
        )
        if any(token in haystack for token in non_infra_tokens):
            return False
        strong_infra_tokens = (
            "cannot connect to the docker daemon",
            "connector_unavailable",
            "connector_runtime_error",
            "docker daemon",
            "github network",
            "network timeout",
            "permission denied",
            "service unavailable",
        )
        if any(token in haystack for token in strong_infra_tokens):
            return True
        infra_tokens = (
            "container",
            "docker",
            "environment",
            "infra",
            "network",
            "runtime",
            "stack unavailable",
        )
        return any(token in haystack for token in infra_tokens)

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

    def _reconcile_pr_outcomes(
        self,
        active_prs: list[dict[str, object]] | None = None,
        *,
        details_cache: dict[int, PullRequestDetails | None] | None = None,
        force_refresh: bool = False,
    ) -> int:
        active_prs = active_prs or self._list_active_pr_rows(include_blocked=True)
        details_cache = details_cache if details_cache is not None else {}
        ci_status_cache: dict[int, dict[str, Any]] = {}
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
            head_sha = ""
            if pr_number > 0:
                pr_details = self._get_pr_details_cached(
                    pr_number=pr_number,
                    cache=details_cache,
                    force_refresh=force_refresh,
                )
                if pr_details is None:
                    continue
                pr_state = pr_details.state
                mergeable_state = pr_details.mergeable_state
                head_ref = pr_details.head_ref
                head_sha = pr_details.head_sha
                pr_state, mergeable_state, refreshed = self._recheck_conflict_state(
                    pr_number=pr_number,
                    current_state=pr_state,
                    current_mergeable_state=mergeable_state,
                )
                if refreshed is not None:
                    details_cache[pr_number] = refreshed
                    head_ref = refreshed.head_ref
                    head_sha = refreshed.head_sha
            else:
                try:
                    discovered_pr = self.tracker.find_pr_for_issue(issue_id=issue_id)
                except Exception as exc:
                    logger.warning("Failed to discover PR for issue #%s: %s", issue_id, exc)
                    continue
                if discovered_pr is None:
                    continue
                pr_number = discovered_pr.number
                pr_state = discovered_pr.state.strip().lower()
                head_ref = ""

            if pr_number > 0 and pr_state != "merged":
                ci_status_summary = self._get_pr_ci_status_summary_cached(
                    pr_number=pr_number,
                    head_sha=head_sha,
                    cache=ci_status_cache,
                    force_refresh=force_refresh,
                )
                self.store.update_issue_pr_ci_status(issue_id=issue_id, ci_status_summary=ci_status_summary)

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
                        ci_status_summary={},
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
                        ci_status_summary=ci_status_cache.get(pr_number, {}),
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
                    ci_status_summary={},
                )
                continue

            self.store.set_healer_issue_state(
                issue_id=issue_id,
                state="resolved",
                pr_number=pr_number,
                pr_state="merged",
                ci_status_summary={},
                clear_lease=True,
            )
            self._sync_blocked_issue_label(issue_id=issue_id, state="resolved")
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
        force_refresh: bool = False,
    ) -> PullRequestDetails | None:
        if force_refresh or pr_number not in cache:
            cache[pr_number] = self.tracker.get_pr_details(pr_number=pr_number)
        return cache[pr_number]

    def _get_pr_ci_status_summary_cached(
        self,
        *,
        pr_number: int,
        head_sha: str,
        cache: dict[int, dict[str, Any]],
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        if force_refresh or pr_number not in cache:
            summary = self.tracker.get_pr_ci_status_summary(pr_number=pr_number, head_sha=head_sha)
            cache[pr_number] = dict(summary) if isinstance(summary, dict) else {}
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
        self._sync_blocked_issue_label(issue_id=issue_id, state="blocked")
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

    @staticmethod
    def _workspace_head_sha(workspace: Path) -> str:
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(workspace),
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception:
            return ""
        if proc.returncode != 0:
            return ""
        return proc.stdout.strip()

    def _open_or_reconcile_pr(
        self,
        *,
        issue_id: str,
        branch: str,
        title: str,
        body: str,
        base: str,
        workspace: Path,
    ) -> PullRequestResult | None:
        head_sha = self._workspace_head_sha(workspace)
        mutation_key = self._mutation_key(
            action=f"open_pr:{branch}:{head_sha}",
            issue_id=issue_id,
            body=body,
        )
        mutation = self.store.get_healer_mutation(mutation_key)
        if mutation is not None and str(mutation.get("status") or "").strip().lower() in {"pending", "success"}:
            discovered = self._discover_open_pr_for_issue(issue_id=issue_id)
            if discovered is not None:
                self.store.complete_healer_mutation(mutation_key=mutation_key, success=True)
                return discovered
            if str(mutation.get("status") or "").strip().lower() == "success":
                self.store.complete_healer_mutation(mutation_key=mutation_key, success=False)

        claim = self.store.claim_healer_mutation(
            mutation_key=mutation_key,
            lease_owner=self.worker_id,
            lease_seconds=max(300, int(getattr(self.dispatcher, "lease_seconds", 300))),
        )
        if claim in {"already_success", "inflight"}:
            discovered = self._discover_open_pr_for_issue(issue_id=issue_id)
            if discovered is not None:
                self.store.complete_healer_mutation(mutation_key=mutation_key, success=True)
                return discovered
            if claim == "already_success":
                self.store.complete_healer_mutation(mutation_key=mutation_key, success=False)
            else:
                logger.info(
                    "Issue #%s PR mutation is already in flight and no PR is visible yet; deferring retry.",
                    issue_id,
                )
                return None
            claim = self.store.claim_healer_mutation(
                mutation_key=mutation_key,
                lease_owner=self.worker_id,
                lease_seconds=max(300, int(getattr(self.dispatcher, "lease_seconds", 300))),
            )
        if claim != "claimed":
            return None

        pr = None
        try:
            pr = self.tracker.open_or_update_pr(
                issue_id=issue_id,
                branch=branch,
                title=title,
                body=body,
                base=base,
            )
            if pr is None or int(getattr(pr, "number", 0) or 0) <= 0:
                discovered = self._discover_open_pr_for_issue(issue_id=issue_id)
                if discovered is not None:
                    pr = discovered
        finally:
            self.store.complete_healer_mutation(
                mutation_key=mutation_key,
                success=pr is not None and int(getattr(pr, "number", 0) or 0) > 0,
            )
        return pr

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
        hardened_execution_root = _sanitize_execution_root(
            execution_root=resolved_execution.execution_root,
            workspace=Path(workspace_path),
        )
        targeted_tests = _collect_targeted_tests(
            issue_body=issue_body,
            output_targets=list(task_spec.output_targets),
            workspace=Path(workspace_path),
            language=resolved_execution.language_effective,
            execution_root=hardened_execution_root,
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

    def _close_and_requeue_stuck_pr(self, *, issue_id: str, pr_number: int, mergeable_state: str, head_ref: str = "") -> bool:
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
        closed_ok = self._run_idempotent_mutation(
            mutation_key=close_pr_key,
            action=lambda: self.tracker.close_pr(pr_number=pr_number, comment=close_body),
        )
        if not closed_ok:
            logger.warning(
                "Failed to close stuck PR #%d for issue #%s; skipping requeue.",
                pr_number,
                issue_id,
            )
            return False
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
        return True

    def _auto_approve_open_prs(
        self,
        active_prs: list[dict[str, object]] | None = None,
        *,
        details_cache: dict[int, PullRequestDetails | None] | None = None,
        viewer_login: str | None = None,
    ) -> int:
        if not getattr(self.settings, "healer_pr_auto_approve_clean", True):
            return 0
        reviewer_login = (viewer_login if viewer_login is not None else self.tracker.viewer_login()).strip().lower()
        active_prs = active_prs or self.store.list_healer_issues(states=["pr_open"], limit=100)
        details_cache = details_cache if details_cache is not None else {}
        approved = 0
        for row in active_prs:
            pr_number = int(row.get("pr_number") or 0)
            if pr_number <= 0:
                continue
            details = self._get_pr_details_cached(pr_number=pr_number, cache=details_cache)
            approved += int(self._maybe_auto_approve_pr(pr_number=pr_number, viewer_login=reviewer_login, details=details))
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
        # GitHub computes mergeable_state asynchronously. When a PR is freshly opened it
        # often returns "unknown". Poll briefly to let GitHub catch up before giving up.
        if details.mergeable_state == "unknown":
            for _attempt in range(4):
                time.sleep(3)
                refreshed = self.tracker.get_pr_details(pr_number=pr_number)
                if refreshed is None:
                    break
                details = refreshed
                if details.mergeable_state != "unknown":
                    break
            else:
                logger.info(
                    "PR #%d mergeable_state still unknown after polling; reconciler will retry.", pr_number
                )
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

    def _auto_merge_open_prs(
        self,
        active_prs: list[dict[str, object]] | None = None,
        *,
        details_cache: dict[int, PullRequestDetails | None] | None = None,
    ) -> int:
        if not getattr(self.settings, "healer_pr_auto_merge_clean", True):
            return 0
        active_prs = active_prs or self.store.list_healer_issues(states=["pr_open"], limit=100)
        details_cache = details_cache if details_cache is not None else {}
        merged = 0
        for row in active_prs:
            pr_number = int(row.get("pr_number") or 0)
            if pr_number <= 0:
                continue
            details = self._get_pr_details_cached(pr_number=pr_number, cache=details_cache)
            merged += int(
                self._maybe_auto_merge_pr(
                    pr_number=pr_number,
                    details=details,
                    issue_id=str(row.get("issue_id") or ""),
                    ci_status_summary=row.get("ci_status_summary"),
                )
            )
        return merged

    def _maybe_auto_merge_pr(
        self,
        *,
        pr_number: int,
        details: PullRequestDetails | None = None,
        issue_id: str = "",
        test_summary: dict[str, Any] | None = None,
        ci_status_summary: dict[str, Any] | None = None,
    ) -> bool:
        if not getattr(self.settings, "healer_pr_auto_merge_clean", True):
            return False
        details = details if details is not None else self.tracker.get_pr_details(pr_number=pr_number)
        if details is None or details.state != "open":
            return False
        if details.mergeable_state not in {"clean", "has_hooks", "unstable"}:
            return False
        resolved_ci_status_summary = dict(ci_status_summary or {})
        if self._ci_overall_state(resolved_ci_status_summary) != "success":
            resolved_ci_status_summary = self._resolve_pr_ci_status_summary(
                issue_id=issue_id,
                pr_number=pr_number,
                head_sha=details.head_sha,
            )
        gate_state = self._merge_gate_state_for_issue(
            issue_id=issue_id,
            test_summary=test_summary,
            ci_status_summary=resolved_ci_status_summary,
        )
        if gate_state != "promotion_ready":
            logger.info(
                "Skipping auto-merge for PR #%d because promotion gate is %s.",
                pr_number,
                gate_state,
            )
            return False
        try:
            return self.tracker.merge_pr(
                pr_number=pr_number,
                merge_method=str(getattr(self.settings, "healer_pr_merge_method", "squash") or "squash"),
            )
        except Exception as exc:
            logger.warning("Failed to auto-merge PR #%d: %s", pr_number, exc)
            return False

    def _resolve_pr_ci_status_summary(
        self,
        *,
        issue_id: str,
        pr_number: int,
        head_sha: str = "",
    ) -> dict[str, Any]:
        normalized_issue_id = str(issue_id or "").strip()
        if pr_number <= 0:
            return {}
        summary = self.tracker.get_pr_ci_status_summary(pr_number=pr_number, head_sha=head_sha)
        normalized_summary = dict(summary) if isinstance(summary, dict) else {}
        if normalized_issue_id and normalized_summary:
            self.store.update_issue_pr_ci_status(
                issue_id=normalized_issue_id,
                ci_status_summary=normalized_summary,
            )
        return normalized_summary

    def _merge_gate_state_for_issue(
        self,
        *,
        issue_id: str,
        test_summary: dict[str, Any] | None = None,
        ci_status_summary: dict[str, Any] | None = None,
    ) -> str:
        if self._judgment_reason_code_for_issue(issue_id=issue_id, test_summary=test_summary):
            return "judgment_required"
        local_gate_state = self._local_promotion_gate_state_for_issue(
            issue_id=issue_id,
            test_summary=test_summary,
        )
        if local_gate_state != "promotion_ready":
            return local_gate_state
        ci_state = self._ci_overall_state(ci_status_summary)
        if ci_state == "success":
            return "promotion_ready"
        if ci_state == "pending":
            return "ci_pending"
        if ci_state == "failure":
            return "ci_failed"
        return "ci_unknown"

    def _local_promotion_gate_state_for_issue(
        self,
        *,
        issue_id: str,
        test_summary: dict[str, Any] | None = None,
    ) -> str:
        resolved_test_summary = dict(test_summary or {})
        if not resolved_test_summary and str(issue_id or "").strip():
            attempts = self.store.list_healer_attempts(issue_id=str(issue_id), limit=1)
            if attempts:
                latest_summary = attempts[0].get("test_summary")
                if isinstance(latest_summary, dict):
                    resolved_test_summary = dict(latest_summary)
        if not resolved_test_summary:
            return "local_validation_pending"
        if str(resolved_test_summary.get("promotion_state") or "").strip().lower() != "promotion_ready":
            phase_states = resolved_test_summary.get("phase_states")
            if not (isinstance(phase_states, dict) and phase_states.get("promotion_ready")):
                return "local_validation_pending"
        if self._browser_artifact_proof_required(resolved_test_summary) and not self._browser_artifact_proof_ready(
            resolved_test_summary
        ):
            return "artifacts_missing"
        return "promotion_ready"

    def _browser_artifact_proof_required(self, test_summary: dict[str, Any] | None) -> bool:
        if not isinstance(test_summary, dict):
            return False
        if bool(test_summary.get("browser_evidence_required")):
            return True
        artifact_bundle = test_summary.get("artifact_bundle")
        if isinstance(artifact_bundle, dict) and (
            isinstance(artifact_bundle.get("failure_artifacts"), dict)
            or isinstance(artifact_bundle.get("resolution_artifacts"), dict)
        ):
            return True
        artifact_links = self._normalized_artifact_links(test_summary.get("artifact_links"))
        if not artifact_links:
            return False
        labels = {
            str(link.get("label") or "").strip().lower()
            for link in artifact_links
            if str(link.get("label") or "").strip()
        }
        return any(label.startswith("failure_") or label.startswith("resolution_") for label in labels)

    def _browser_artifact_proof_ready(self, test_summary: dict[str, Any] | None) -> bool:
        if not isinstance(test_summary, dict):
            return False
        if bool(test_summary.get("artifact_proof_ready")):
            return True
        artifact_links = self._normalized_artifact_links(test_summary.get("artifact_links"))
        labels = {
            str(link.get("label") or "").strip().lower()
            for link in artifact_links
            if str(link.get("label") or "").strip()
        }
        if {"failure_screenshot", "resolution_screenshot"}.issubset(labels):
            return True
        artifact_bundle = test_summary.get("artifact_bundle")
        if not isinstance(artifact_bundle, dict):
            return False
        failure_artifacts = artifact_bundle.get("failure_artifacts")
        resolution_artifacts = artifact_bundle.get("resolution_artifacts")
        if not isinstance(failure_artifacts, dict) or not isinstance(resolution_artifacts, dict):
            return False
        return bool(
            str(failure_artifacts.get("screenshot_path") or "").strip()
            and str(resolution_artifacts.get("screenshot_path") or "").strip()
        )

    def _judgment_reason_code_for_issue(
        self,
        *,
        issue_id: str,
        test_summary: dict[str, Any] | None = None,
    ) -> str:
        if isinstance(test_summary, dict):
            value = str(test_summary.get("judgment_reason_code") or "").strip()
            if value:
                return value
        if str(issue_id or "").strip():
            attempts = self.store.list_healer_attempts(issue_id=str(issue_id), limit=1)
            if attempts:
                value = str(attempts[0].get("judgment_reason_code") or "").strip()
                if value:
                    return value
        return ""

    def _with_promotion_transitions(
        self,
        *,
        test_summary: dict[str, Any] | None,
        issue_state: str,
        pr_number: int,
        ci_status_summary: dict[str, Any] | None = None,
        judgment_reason_code: str = "",
    ) -> dict[str, Any]:
        enriched = dict(test_summary or {})
        transitions = self._normalized_promotion_transitions(enriched.get("promotion_transitions"))
        if pr_number > 0 or issue_state in {"pr_open", "pr_pending_approval", "resolved"}:
            self._append_promotion_transition(transitions, "pr_open")
        ci_state = self._ci_overall_state(ci_status_summary)
        if ci_state == "success":
            self._append_promotion_transition(transitions, "ci_green")
        local_gate_state = self._local_promotion_gate_state_for_issue(issue_id="", test_summary=enriched)
        if judgment_reason_code.strip():
            self._append_promotion_transition(transitions, "merge_blocked")
        elif local_gate_state == "promotion_ready" and (
            issue_state == "resolved" or (issue_state == "pr_open" and ci_state == "success")
        ):
            self._append_promotion_transition(transitions, "promotion_ready")
        elif local_gate_state == "artifacts_missing" or ci_state == "failure" or issue_state in {"failed", "blocked"}:
            self._append_promotion_transition(transitions, "merge_blocked")
        if transitions:
            enriched["promotion_transitions"] = transitions
        return enriched

    @staticmethod
    def _normalized_promotion_transitions(raw_value: Any) -> list[str]:
        if not isinstance(raw_value, list):
            return []
        normalized: list[str] = []
        for item in raw_value:
            label = str(item or "").strip().lower()
            if not label or label in normalized:
                continue
            normalized.append(label)
        return normalized

    @staticmethod
    def _append_promotion_transition(transitions: list[str], label: str) -> None:
        normalized = str(label or "").strip().lower()
        if normalized and normalized not in transitions:
            transitions.append(normalized)

    @staticmethod
    def _ci_overall_state(ci_status_summary: dict[str, Any] | None) -> str:
        if not isinstance(ci_status_summary, dict):
            return ""
        return str(ci_status_summary.get("overall_state") or "").strip().lower()

    def _requeue_ci_failed_prs(self, active_prs: list[dict[str, object]] | None = None) -> int:
        active_prs = active_prs or self.store.list_healer_issues(states=["pr_open"], limit=100)
        requeued = 0
        for row in active_prs:
            issue_id = str(row.get("issue_id") or "").strip()
            pr_number = int(row.get("pr_number") or 0)
            ci_status_summary = dict(row.get("ci_status_summary") or {})
            if not issue_id or pr_number <= 0:
                continue
            if self._ci_overall_state(ci_status_summary) != "failure":
                continue
            signal = self._ci_failure_signal(ci_status_summary)
            if signal and self.store.get_state(self._ci_handled_signal_key(issue_id)) == signal:
                continue
            retriable_buckets = self._retriable_ci_failure_buckets(ci_status_summary)
            if not retriable_buckets:
                if signal:
                    self.store.set_state(self._ci_handled_signal_key(issue_id), signal)
                continue
            feedback_context = self._compose_ci_failure_feedback_context(
                existing_feedback=str(row.get("feedback_context") or "").strip(),
                ci_status_summary=ci_status_summary,
                pr_number=pr_number,
            )
            failure_reason = self._ci_failure_reason(
                ci_status_summary=ci_status_summary,
                pr_number=pr_number,
            )
            attempt_no = max(1, int(row.get("attempt_count") or 0))
            if attempt_no >= int(getattr(self.settings, "healer_retry_budget", 1)):
                self.store.set_healer_issue_state(
                    issue_id=issue_id,
                    state="pr_open",
                    last_failure_class="ci_retry_exhausted",
                    last_failure_reason=failure_reason[:500],
                    clear_lease=True,
                )
                if signal:
                    self.store.set_state(self._ci_handled_signal_key(issue_id), signal)
                self._sync_outcome_issue_label(issue_id=issue_id, label=_OUTCOME_LABEL_RETRY_EXHAUSTED)
                self._post_issue_status(
                    issue_id=issue_id,
                    body=self._format_flow_status_comment(
                        "Remote CI retry budget exhausted",
                        "The open pull request still has deterministic CI failures, but Flow Healer will stop retrying automatically for this CI signal.",
                        [
                            f"PR: `#{pr_number}`",
                            f"Failure buckets: `{', '.join(retriable_buckets)}`",
                            f"Reason: {self._clean_comment_text(failure_reason, max_chars=260)}",
                            f"Retry budget: `{self.settings.healer_retry_budget}`",
                        ],
                        outro="Review the failing checks or add new guidance before another autonomous retry.",
                    ),
                )
                self._record_retry_playbook_selection(
                    issue_id=issue_id,
                    failure_class="ci_failed",
                    failure_domain="code",
                    strategy="remote_ci_retry_budget_exhausted",
                    backoff_seconds=0,
                    feedback_hint=feedback_context,
                )
                continue
            self.store.set_healer_issue_state(
                issue_id=issue_id,
                state="queued",
                backoff_until="",
                last_failure_class="ci_failed",
                last_failure_reason=failure_reason[:500],
                feedback_context=feedback_context[:500],
                clear_lease=True,
            )
            if signal:
                self.store.set_state(self._ci_handled_signal_key(issue_id), signal)
            self._sync_blocked_issue_label(issue_id=issue_id, state="queued")
            self._sync_outcome_issue_label(issue_id=issue_id, label="")
            self._post_issue_status(
                issue_id=issue_id,
                body=self._format_flow_status_comment(
                    "Remote CI failed; requeueing the same PR",
                    "Flow Healer detected deterministic CI failures on the open pull request and is queueing another repair pass on the same branch.",
                    [
                        f"PR: `#{pr_number}`",
                        f"Failure buckets: `{', '.join(retriable_buckets)}`",
                        f"Reason: {self._clean_comment_text(failure_reason, max_chars=260)}",
                    ],
                    outro="The next attempt will reuse the existing PR context instead of opening a duplicate pull request.",
                ),
            )
            self._record_retry_playbook_selection(
                issue_id=issue_id,
                failure_class="ci_failed",
                failure_domain="code",
                strategy="remote_ci_requeue",
                backoff_seconds=0,
                feedback_hint=feedback_context,
            )
            requeued += 1
        return requeued

    @staticmethod
    def _ci_handled_signal_key(issue_id: str) -> str:
        return f"healer_ci_handled_signal:{str(issue_id or '').strip()}"

    @staticmethod
    def _ci_failure_signal(ci_status_summary: dict[str, Any] | None) -> str:
        if not isinstance(ci_status_summary, dict):
            return ""
        entries = [
            {
                "source": str(entry.get("source") or "").strip(),
                "name": str(entry.get("name") or "").strip(),
                "state": str(entry.get("state") or "").strip(),
                "bucket": str(entry.get("bucket") or "").strip(),
                "failure_kind": str(entry.get("failure_kind") or "").strip(),
                "updated_at": str(entry.get("updated_at") or "").strip(),
            }
            for entry in (ci_status_summary.get("failing_entries") or [])
            if isinstance(entry, dict)
        ]
        material = json.dumps(
            {
                "head_sha": str(ci_status_summary.get("head_sha") or "").strip(),
                "updated_at": str(ci_status_summary.get("updated_at") or "").strip(),
                "failing_entries": entries,
            },
            sort_keys=True,
        )
        if not material:
            return ""
        return hashlib.sha1(material.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _retriable_ci_failure_buckets(ci_status_summary: dict[str, Any] | None) -> list[str]:
        if not isinstance(ci_status_summary, dict):
            return []
        failing_entries = [
            dict(entry)
            for entry in (ci_status_summary.get("failing_entries") or [])
            if isinstance(entry, dict)
        ]
        if failing_entries:
            deterministic_buckets = {
                str(entry.get("bucket") or "").strip()
                for entry in failing_entries
                if str(entry.get("bucket") or "").strip()
                and str(entry.get("failure_kind") or "").strip().lower() != "transient_infra"
            }
            if deterministic_buckets:
                return sorted(bucket for bucket in deterministic_buckets if bucket in _RETRIABLE_CI_FAILURE_BUCKETS)
            if any(str(entry.get("failure_kind") or "").strip().lower() == "transient_infra" for entry in failing_entries):
                return []
        buckets = [
            str(bucket).strip()
            for bucket in (ci_status_summary.get("failure_buckets") or [])
            if str(bucket).strip()
        ]
        return sorted(bucket for bucket in buckets if bucket in _RETRIABLE_CI_FAILURE_BUCKETS)

    def _ci_failure_reason(self, *, ci_status_summary: dict[str, Any], pr_number: int) -> str:
        buckets = self._retriable_ci_failure_buckets(ci_status_summary)
        entries = self._ci_failure_entries_preview(ci_status_summary=ci_status_summary)
        if buckets and entries:
            return (
                f"Remote CI failed for PR #{pr_number} in {', '.join(buckets)} checks: "
                f"{'; '.join(entries)}."
            )
        if buckets:
            return f"Remote CI failed for PR #{pr_number} in {', '.join(buckets)} checks."
        if entries:
            return f"Remote CI failed for PR #{pr_number}: {'; '.join(entries)}."
        return f"Remote CI failed for PR #{pr_number}."

    def _compose_ci_failure_feedback_context(
        self,
        *,
        existing_feedback: str,
        ci_status_summary: dict[str, Any],
        pr_number: int,
    ) -> str:
        buckets = self._retriable_ci_failure_buckets(ci_status_summary)
        entries = self._ci_failure_entries_preview(ci_status_summary=ci_status_summary)
        pending_contexts = [
            str(context).strip()
            for context in (ci_status_summary.get("pending_contexts") or [])
            if str(context).strip()
        ]
        parts = [existing_feedback] if existing_feedback else []
        ci_lines = [
            "[ci_failure_feedback]",
            f"Open PR: #{pr_number}",
            f"Head SHA: {str(ci_status_summary.get('head_sha') or '').strip()}",
            f"Failure buckets: {', '.join(buckets) if buckets else 'unknown'}",
        ]
        if entries:
            ci_lines.append("Failing checks:")
            ci_lines.extend(f"- {entry}" for entry in entries)
        if pending_contexts:
            ci_lines.append(f"Still pending: {', '.join(pending_contexts)}")
        ci_lines.append(
            "Fix the failing remote CI checks on the existing managed branch and update the same pull request."
        )
        parts.append("\n".join(ci_lines))
        return "\n\n".join(part for part in parts if part).strip()

    @staticmethod
    def _ci_failure_entries_preview(
        *,
        ci_status_summary: dict[str, Any],
        limit: int = 5,
    ) -> list[str]:
        preview: list[str] = []
        for entry in ci_status_summary.get("failing_entries") or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            bucket = str(entry.get("bucket") or "").strip()
            source = str(entry.get("source") or "").strip()
            if not name:
                continue
            label = name
            if bucket:
                label = f"{label} [{bucket}]"
            if source:
                label = f"{label} via {source}"
            preview.append(label)
            if len(preview) >= max(1, int(limit)):
                break
        return preview

    @staticmethod
    def _normalize_repo_path(value: str) -> str:
        return _normalize_repo_relative_path(value)

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
            limit=max(50, self.settings.healer_max_concurrent_issues * 20),
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
            existing_state = str((existing_issue or {}).get("state") or "").strip().lower()
            issue_contract_changed = bool(
                existing_issue is not None
                and (
                    str(existing_issue.get("title") or "") != issue.title
                    or str(existing_issue.get("body") or "") != issue.body
                    or list(existing_issue.get("labels") or []) != issue.labels
                )
            )
            should_discover_pr = (
                existing_issue is None
                or int((existing_issue or {}).get("pr_number") or 0) > 0
                or existing_state in {"pr_open", "pr_pending_approval", "blocked", "resolved"}
                or issue_contract_changed
            )
            discovered_pr = (
                self._discover_open_pr_for_issue(issue_id=issue.issue_id)
                if should_discover_pr
                else None
            )
            if existing_issue is not None:
                existing_pr_state = str(existing_issue.get("pr_state") or "").strip().lower()
                preserve_ci_requeue = (
                    existing_state == "queued"
                    and int(existing_issue.get("pr_number") or 0) > 0
                    and str(existing_issue.get("last_failure_class") or "").strip().lower() == "ci_failed"
                )
                if discovered_pr is not None:
                    if preserve_ci_requeue:
                        continue
                    self._restore_open_pr_state(
                        issue_id=issue.issue_id,
                        pr_number=discovered_pr.number,
                        pr_state=discovered_pr.state,
                    )
                    continue
                if existing_state == "needs_clarification":
                    # Issue body was updated; re-check confidence on next cycle
                    clarification_key = f"healer_clarification_posted:{issue.issue_id}"
                    new_spec = compile_task_spec(issue_title=issue.title, issue_body=issue.body)
                    if new_spec.parse_confidence >= 0.3:
                        self.store.set_state(clarification_key, "")
                        self.store.set_healer_issue_state(
                            issue_id=issue.issue_id,
                            state="queued",
                            clear_lease=True,
                        )
                    continue
                should_requeue_blocked = existing_state == "blocked" and issue_contract_changed
                if existing_state == "archived" or should_requeue_blocked or (
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
            self._sync_blocked_issue_label(issue_id=issue_id, state="queued")
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
        self._clear_sticky_runtime_status(issue_id=issue.issue_id)
        if not self._claim_is_actionable(issue):
            return
        logger.info("Claimed issue #%s (%s)", issue.issue_id, issue.title[:120])
        self._record_worker_heartbeat(status="processing", issue_id=issue.issue_id)
        task_spec = compile_task_spec(issue_title=issue.title, issue_body=issue.body)
        clarification_reasons = self._clarification_reasons_for_task_spec(task_spec=task_spec)
        if clarification_reasons:
            clarification_key = f"healer_clarification_posted:{issue.issue_id}"
            already_posted = self.store.get_state(clarification_key) == "true"
            if not already_posted:
                logger.info(
                    "Issue #%s requires clarification (%s); posting needs-clarification comment.",
                    issue.issue_id,
                    ", ".join(clarification_reasons),
                )
                self._post_issue_status(
                    issue_id=issue.issue_id,
                    body=self._build_needs_clarification_comment(
                        clarification_reasons,
                        task_spec=task_spec,
                    ),
                )
                self.store.set_state(clarification_key, "true")
            self.store.set_healer_issue_state(
                issue_id=issue.issue_id,
                state="needs_clarification",
                clear_lease=True,
            )
            self._sync_outcome_issue_label(issue_id=issue.issue_id, label=_OUTCOME_LABEL_NEEDS_CLARIFICATION)
            return
        prediction = predict_lock_set(issue_text=f"{issue.title}\n{issue.body}")
        scope_key = self._issue_scope_key(task_spec=task_spec, prediction=prediction)
        dedupe_key = self._issue_dedupe_key(task_spec=task_spec, scope_key=scope_key)
        self.store.set_healer_issue_state(
            issue_id=issue.issue_id,
            state="claimed",
            scope_key=scope_key,
            dedupe_key=dedupe_key,
        )
        self._sync_outcome_issue_label(issue_id=issue.issue_id, label="")
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
        ci_status_summary: dict[str, object] = {}
        verifier_summary: dict[str, object] = {}
        swarm_summary: dict[str, object] = {}
        failure_class = ""
        failure_reason = ""
        proposer_output_excerpt = ""
        issue_state = "claimed"
        attempt_state = "failed"
        pr_number = 0
        workspace = None
        run_result: Any = None

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

        try:
            selected_backend, selected_connector, selected_runner, selected_verifier, selected_reviewer, selected_swarm, selected_preflight = (
                self._pipeline_for_task(task_spec)
            )
            if not bool(getattr(self.tracker, "enabled", False)):
                failure_class = "github_auth_missing"
                failure_reason = "GitHub tracker is disabled (missing token or repo slug); cannot process claimed issue."
                self._record_tracker_error(failure_class=failure_class, failure_reason=failure_reason)
                issue_state = self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=_attempt_label(),
                    failure_class=failure_class,
                    failure_reason=failure_reason,
                )
                return
            try:
                resolved_execution = selected_runner.resolve_execution(workspace=self.repo_path, task_spec=task_spec)
            except UnsupportedLanguageError as exc:
                failure_class = "unsupported_language"
                failure_reason = str(exc)
                issue_state = "archived"
                attempt_state = "archived"
                self._archive_unsupported_language_issue(
                    issue_id=issue.issue_id,
                    reason=failure_reason,
                )
                return
            detected_language = resolved_execution.language_effective or resolved_execution.language_detected or ""
            preflight_root_candidate = _sanitize_execution_root(
                execution_root=(
                    resolved_execution.execution_root
                    or execution_root_for_language(detected_language)
                ),
                workspace=self.repo_path,
            )
            preflight_execution_root = (
                preflight_root_candidate
                or execution_root_for_language(detected_language)
            )
            should_run_preflight = bool(preflight_execution_root) and (
                self.repo_path / preflight_execution_root
            ).is_dir()
            if detected_language and should_run_preflight:
                report = selected_preflight.ensure_language_ready(
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
                resolved_execution = selected_runner.resolve_execution(workspace=workspace.path, task_spec=task_spec)
            except UnsupportedLanguageError as exc:
                failure_class = "unsupported_language"
                failure_reason = str(exc)
                issue_state = "archived"
                attempt_state = "archived"
                self._archive_unsupported_language_issue(
                    issue_id=issue.issue_id,
                    reason=failure_reason,
                )
                return
            detected_language = resolved_execution.language_effective or resolved_execution.language_detected or ""
            hardened_execution_root = _sanitize_execution_root(
                execution_root=resolved_execution.execution_root,
                workspace=workspace.path,
            )
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
                        f"Execution mode: `{_execution_mode_for_task(connector=selected_connector, task_spec=task_spec)}`",
                        f"Targets: `{self._clean_comment_text(', '.join(task_spec.output_targets) if task_spec.output_targets else 'inferred in code', max_chars=220)}`",
                        f"Connector backend: `{selected_backend}`",
                        f"Test gate mode: `{selected_runner.test_gate_mode}`",
                    ],
                ),
            )
            targeted_tests = _collect_targeted_tests(
                issue_body=issue.body,
                output_targets=list(task_spec.output_targets),
                workspace=workspace.path,
                language=resolved_execution.language_effective,
                execution_root=hardened_execution_root,
            )
            if _is_issue_scoped_sql_validation_task(task_spec):
                baseline_validation = selected_runner.validate_workspace(
                    workspace.path,
                    task_spec=task_spec,
                    targeted_tests=targeted_tests,
                )
                if int(baseline_validation.get("failed_tests", 0) or 0) == 0:
                    issue_state = "archived"
                    attempt_state = "archived"
                    self._archive_already_satisfied_issue(
                        issue_id=issue.issue_id,
                        reason=(
                            "The current baseline already satisfies the issue-scoped SQL assertion(s) "
                            "and full DB validation, so no code change is needed."
                        ),
                    )
                    return
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
            # Probe connector availability before burning turn timeout on a broken connector.
            connector_ok, connector_fail_reason = selected_preflight.probe_connector(selected_connector)
            if not connector_ok:
                logger.warning(
                    "Connector probe failed for issue #%s: %s", issue.issue_id, connector_fail_reason
                )
                failure_class = "connector_unavailable"
                failure_reason = connector_fail_reason or "Connector probe failed before run attempt."
                self._post_issue_status(
                    issue_id=issue.issue_id,
                    body=self._format_flow_status_comment(
                        title="Connector Unavailable",
                        subtitle=f"Attempt {attempt_no} skipped — AI connector is not reachable.",
                        bullets=[
                            f"Reason: {failure_reason}",
                            "Please verify that `codex` is installed and the `GITHUB_TOKEN` is set.",
                        ],
                    ),
                )
                return self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class=failure_class,
                    failure_reason=failure_reason,
                )
            native_multi_agent_profile = self._codex_native_multi_agent_profile_for_task(
                selected_backend=selected_backend,
                task_spec=task_spec,
                recovery=False,
                count_skips=True,
            )
            native_multi_agent_max_subagents = self._codex_native_multi_agent_max_subagents()
            if native_multi_agent_profile:
                self._record_codex_native_multi_agent_attempt()
            run_result = selected_runner.run_attempt(
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
                native_multi_agent_profile=native_multi_agent_profile,
                native_multi_agent_max_subagents=native_multi_agent_max_subagents,
            )
            if native_multi_agent_profile and run_result.success:
                self._increment_state_counter("healer_codex_native_multi_agent_success")
            actual_diff = run_result.diff_paths
            test_summary = dict(run_result.test_summary or {})
            self._record_app_server_attempt_metrics(
                connector=selected_connector,
                task_kind=task_spec.task_kind,
                had_material_diff=bool(actual_diff),
            )
            self._record_app_server_recovery_metrics(
                connector=selected_connector,
                workspace_status=run_result.workspace_status,
            )
            proposer_output_excerpt = (run_result.proposer_output or "")[:1500]
            if not run_result.success:
                swarm_outcome: SwarmRecoveryOutcome | None = None
                native_recovery_result = self._maybe_recover_with_native_codex(
                    selected_backend=selected_backend,
                    selected_runner=selected_runner,
                    issue=issue,
                    task_spec=task_spec,
                    learned_context=learned_context,
                    feedback_context=feedback_context,
                    failure_class=run_result.failure_class,
                    failure_reason=run_result.failure_reason,
                    proposer_output=run_result.proposer_output,
                    workspace=workspace.path,
                    targeted_tests=targeted_tests,
                )
                if native_recovery_result is not None:
                    run_result = native_recovery_result
                    actual_diff = run_result.diff_paths
                    test_summary = dict(run_result.test_summary or {})
                    proposer_output_excerpt = (run_result.proposer_output or "")[:1500]
                    self._record_app_server_recovery_metrics(
                        connector=selected_connector,
                        workspace_status=run_result.workspace_status,
                    )
                    if not run_result.success:
                        self._increment_state_counter("healer_codex_native_multi_agent_fallback_to_swarm")
                if not run_result.success:
                    swarm_outcome = self._maybe_recover_with_swarm(
                        selected_backend=selected_backend,
                        selected_swarm=selected_swarm,
                        selected_runner=selected_runner,
                        issue=issue,
                        attempt_id=attempt_id,
                        attempt_no=attempt_no,
                        task_spec=task_spec,
                        learned_context=learned_context,
                        feedback_context=feedback_context,
                        failure_class=run_result.failure_class,
                        failure_reason=run_result.failure_reason,
                        proposer_output=run_result.proposer_output,
                        test_summary=dict(run_result.test_summary or {}),
                        verifier_summary={},
                        workspace_status=run_result.workspace_status,
                        workspace=workspace.path,
                        targeted_tests=targeted_tests,
                    )
                if swarm_outcome is not None:
                    swarm_summary = _append_swarm_cycle(swarm_summary, swarm_outcome)
                    if swarm_outcome.recovered and swarm_outcome.run_result is not None:
                        run_result = swarm_outcome.run_result
                        actual_diff = run_result.diff_paths
                        test_summary = dict(run_result.test_summary or {})
                        proposer_output_excerpt = (run_result.proposer_output or "")[:1500]
                        self._record_app_server_recovery_metrics(
                            connector=selected_connector,
                            workspace_status=run_result.workspace_status,
                        )
                failure_class = run_result.failure_class
                failure_reason = run_result.failure_reason
                if run_result.success:
                    failure_class = ""
                    failure_reason = ""
                else:
                    if swarm_outcome is not None and not swarm_outcome.recovered:
                        failure_class, failure_reason = self._swarm_failure_override(
                            base_failure_class=failure_class,
                            base_failure_reason=failure_reason,
                            swarm_outcome=swarm_outcome,
                        )
                        if not str(run_result.test_summary or "").strip():
                            test_summary = dict(run_result.test_summary or {})
                if not run_result.success:
                    if run_result.failure_fingerprint and not str(test_summary.get("failure_fingerprint") or "").strip():
                        test_summary["failure_fingerprint"] = run_result.failure_fingerprint
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
                        failure_class=failure_class,
                        failure_reason=failure_reason,
                        issue_body=issue.body,
                        feedback_context_override=_format_swarm_retry_feedback(swarm_summary),
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

            verification = selected_verifier.verify(
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
                staged_diff_content=self._resolve_staged_diff_content(run_result=run_result, workspace=workspace.path),
                staged_diff_metadata=self._resolve_staged_diff_metadata(run_result=run_result),
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
                swarm_outcome: SwarmRecoveryOutcome | None = None
                native_recovery_result = self._maybe_recover_with_native_codex(
                    selected_backend=selected_backend,
                    selected_runner=selected_runner,
                    issue=issue,
                    task_spec=task_spec,
                    learned_context=learned_context,
                    feedback_context=feedback_context,
                    failure_class="verifier_failed",
                    failure_reason=verification.summary,
                    proposer_output=run_result.proposer_output,
                    workspace=workspace.path,
                    targeted_tests=targeted_tests,
                )
                if native_recovery_result is not None:
                    run_result = native_recovery_result
                    actual_diff = run_result.diff_paths
                    test_summary = dict(run_result.test_summary or {})
                    proposer_output_excerpt = (run_result.proposer_output or "")[:1500]
                    if not run_result.success:
                        self._increment_state_counter("healer_codex_native_multi_agent_fallback_to_swarm")
                    else:
                        if _abort_for_lost_lease():
                            return
                        verification = selected_verifier.verify(
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
                            staged_diff_content=self._resolve_staged_diff_content(run_result=run_result, workspace=workspace.path),
                            staged_diff_metadata=self._resolve_staged_diff_metadata(run_result=run_result),
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
                    swarm_outcome = self._maybe_recover_with_swarm(
                        selected_backend=selected_backend,
                        selected_swarm=selected_swarm,
                        selected_runner=selected_runner,
                        issue=issue,
                        attempt_id=attempt_id,
                        attempt_no=attempt_no,
                        task_spec=task_spec,
                        learned_context=learned_context,
                        feedback_context=feedback_context,
                        failure_class="verifier_failed",
                        failure_reason=verification.summary,
                        proposer_output=run_result.proposer_output,
                        test_summary=dict(run_result.test_summary or {}),
                        verifier_summary=verifier_summary,
                        workspace_status=run_result.workspace_status,
                        workspace=workspace.path,
                        targeted_tests=targeted_tests,
                    )
                if swarm_outcome is not None:
                    swarm_summary = _append_swarm_cycle(swarm_summary, swarm_outcome)
                    if swarm_outcome.recovered and swarm_outcome.run_result is not None:
                        run_result = swarm_outcome.run_result
                        actual_diff = run_result.diff_paths
                        test_summary = dict(run_result.test_summary or {})
                        proposer_output_excerpt = (run_result.proposer_output or "")[:1500]
                        if _abort_for_lost_lease():
                            return
                        verification = selected_verifier.verify(
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
                            staged_diff_content=self._resolve_staged_diff_content(run_result=run_result, workspace=workspace.path),
                            staged_diff_metadata=self._resolve_staged_diff_metadata(run_result=run_result),
                        )
                        verifier_summary = {
                            "passed": verification.passed,
                            "summary": verification.summary,
                            "verdict": getattr(verification, "verdict", "pass" if verification.passed else "hard_fail"),
                            "hard_failure": bool(getattr(verification, "hard_failure", not verification.passed)),
                            "parse_error": bool(getattr(verification, "parse_error", False)),
                            "policy": _verifier_policy_for_settings(self.settings),
                        }
                    else:
                        failure_class, failure_reason = self._swarm_failure_override(
                            base_failure_class=failure_class,
                            base_failure_reason=failure_reason,
                            swarm_outcome=swarm_outcome,
                        )
                if _should_block_on_verification(self.settings, verification):
                    issue_state = self._backoff_or_fail(
                        issue_id=issue.issue_id,
                        attempt_no=attempt_no,
                        failure_class=failure_class,
                        failure_reason=failure_reason,
                        feedback_context_override=_compose_retry_feedback_context(
                            feedback_hint=_format_verifier_retry_feedback(
                                verdict=str(getattr(verification, "verdict", "")),
                                hard_failure=bool(getattr(verification, "hard_failure", False)),
                                parse_error=bool(getattr(verification, "parse_error", False)),
                                summary=verification.summary,
                            ),
                            override=_format_swarm_retry_feedback(swarm_summary),
                        ),
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
                self._sync_outcome_issue_label(issue_id=issue.issue_id, label="")
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
                            *self._format_evidence_bullets(run_result.test_summary),
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

            test_summary = self._publish_pr_artifacts(
                issue_id=issue.issue_id,
                attempt_id=attempt_id,
                base_branch=self.settings.healer_default_branch,
                test_summary=test_summary,
            )
            pr_title = f"healer: fix issue #{issue.issue_id} - {issue.title[:80]}"
            pr_body = self._format_pr_description(
                issue_id=issue.issue_id,
                verifier_summary=verification.summary,
                test_summary=test_summary,
            )
            pr = self._open_or_reconcile_pr(
                issue_id=issue.issue_id,
                branch=workspace.branch,
                title=pr_title,
                body=pr_body,
                base=self.settings.healer_default_branch,
                workspace=workspace.path,
            )
            pr_number = int(getattr(pr, "number", 0) or 0) if pr is not None else 0
            if pr is None or pr_number <= 0:
                tracker_error_class, tracker_error_reason = self._tracker_last_error()
                failure_class = self._classify_tracker_failure(tracker_error_class)
                failure_reason = (
                    tracker_error_reason.strip()
                    or "Failed to create/update pull request."
                )
                self._record_tracker_error(failure_class=failure_class, failure_reason=failure_reason)
                logger.info("Issue #%s attempt %s could not open PR", issue.issue_id, attempt_no)
                issue_state = self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class=failure_class,
                    failure_reason=failure_reason,
                )
                return

            self.store.set_healer_issue_state(
                issue_id=issue.issue_id,
                state="pr_open",
                pr_number=pr.number,
                pr_state=pr.state,
                clear_lease=True,
            )
            outcome_label = (
                _OUTCOME_LABEL_DONE_ARTIFACT
                if task_spec.validation_profile == "artifact_only"
                else _OUTCOME_LABEL_DONE_CODE
            )
            self._sync_outcome_issue_label(issue_id=issue.issue_id, label=outcome_label)
            self._post_issue_status(
                issue_id=issue.issue_id,
                body=self._format_flow_status_comment(
                    "Pull request opened or updated",
                    "I opened or updated the pull request for this issue.",
                    [
                        f"PR: [#{pr.number}]({pr.html_url})",
                        f"Execution mode: `{_execution_mode_for_task(connector=selected_connector, task_spec=task_spec)}`",
                        f"Connector backend: `{selected_backend}`",
                        f"Verifier mode: `{_verifier_mode_label(self.settings, verification)}`",
                        f"Verifier verdict: `{getattr(verification, 'verdict', 'pass' if verification.passed else 'hard_fail')}`",
                        *self._format_test_summary_bullets(test_summary),
                        *self._format_evidence_bullets(test_summary),
                    ],
                ),
            )
            issue_state = "pr_open"
            attempt_state = "pr_open"
            self._maybe_auto_approve_pr(pr_number=pr.number)
            ci_status_summary = dict(
                self._resolve_pr_ci_status_summary(
                    issue_id=issue.issue_id,
                    pr_number=pr.number,
                )
            )
            self._maybe_auto_merge_pr(
                pr_number=pr.number,
                issue_id=issue.issue_id,
                test_summary=test_summary,
                ci_status_summary=ci_status_summary,
            )
            logger.info("Issue #%s opened/updated PR #%s", issue.issue_id, pr.number)
            if self.settings.healer_enable_review:
                try:
                    review = selected_reviewer.review(
                        issue_id=issue.issue_id,
                        issue_title=issue.title,
                        issue_body=issue.body,
                        diff_paths=run_result.diff_paths,
                        test_summary=test_summary,
                        proposer_output=run_result.proposer_output,
                        verifier_summary=verification.summary,
                        learned_context=learned_context,
                    )
                    self.tracker.add_pr_comment(pr_number=pr.number, body=review.review_body)
                except Exception as exc:
                    logger.warning("Failed to generate or post code review for PR #%d: %s", pr.number, exc)
        finally:
            self._clear_sticky_runtime_status(issue_id=issue.issue_id)
            lease_stop.set()
            lease_thread.join(timeout=1.0)
            if attempt_id:
                judgment_reason_code = self._resolve_attempt_judgment_reason_code(
                    test_summary=test_summary,
                    workspace_status=getattr(run_result, "workspace_status", None),
                )
                test_summary = self._with_promotion_transitions(
                    test_summary=test_summary,
                    issue_state=attempt_state,
                    pr_number=pr_number,
                    ci_status_summary=ci_status_summary,
                    judgment_reason_code=judgment_reason_code,
                )
                self.store.finish_healer_attempt(
                    attempt_id=attempt_id,
                    state=attempt_state,
                    actual_diff_set=actual_diff,
                    test_summary=test_summary,
                    verifier_summary=verifier_summary,
                    swarm_summary=swarm_summary,
                    runtime_summary=self._resolve_attempt_runtime_summary(
                        test_summary=test_summary,
                        workspace_status=getattr(run_result, "workspace_status", None),
                    ),
                    artifact_bundle=self._resolve_attempt_artifact_bundle(
                        test_summary=test_summary,
                        workspace_status=getattr(run_result, "workspace_status", None),
                    ),
                    artifact_links=self._resolve_attempt_artifact_links(
                        test_summary=test_summary,
                        workspace_status=getattr(run_result, "workspace_status", None),
                    ),
                    ci_status_summary=ci_status_summary,
                    judgment_reason_code=judgment_reason_code,
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
                            *self._format_evidence_bullets(test_summary),
                        ],
                        outro="Failure details were saved so the next pass can reuse the context.",
                        ),
                )

    def _archive_unsupported_language_issue(self, *, issue_id: str, reason: str) -> None:
        reason_text = str(reason or "").strip() or "Unsupported language for this automation lane."
        self._post_issue_status(
            issue_id=issue_id,
            body=self._format_flow_status_comment(
                "Unsupported language for this lane",
                "This Flow Healer lane currently focuses on Python and Node.js.",
                [
                    "Status: `archived`",
                    "Lane focus: `python`, `node`",
                    f"Reason: {self._clean_comment_text(reason_text, max_chars=260)}",
                    "Action: migrate this issue to the matching language lane/queue.",
                ],
                outro=(
                    "After migration, re-run the issue in the language-specific lane so it can be processed "
                    "with the right toolchain."
                ),
            ),
        )
        close_issue_key = self._mutation_key(action="close_issue_unsupported_language", issue_id=issue_id)
        close_ok = self._run_idempotent_mutation(
            mutation_key=close_issue_key,
            action=lambda: self.tracker.close_issue(issue_id=issue_id),
        )
        if not close_ok:
            logger.warning("Unsupported-language issue #%s could not be closed on GitHub.", issue_id)
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="archived",
            pr_state="closed",
            last_failure_class="unsupported_language",
            last_failure_reason=reason_text[:500],
            clear_lease=True,
        )

    def _archive_already_satisfied_issue(self, *, issue_id: str, reason: str) -> None:
        reason_text = str(reason or "").strip() or "The issue requirement is already satisfied on the current baseline."
        self._post_issue_status(
            issue_id=issue_id,
            body=self._format_flow_status_comment(
                "Issue already satisfied on current baseline",
                "The issue-scoped validation passed before any edits were needed.",
                [
                    "Status: `archived`",
                    f"Reason: {self._clean_comment_text(reason_text, max_chars=260)}",
                    "Action: queue a fresh issue only if there is a concrete failing regression to reproduce.",
                ],
                outro=(
                    "This prevents unnecessary churn on issues whose declared validation contract already passes "
                    "without a code change."
                ),
            ),
        )
        close_issue_key = self._mutation_key(action="close_issue_already_satisfied", issue_id=issue_id)
        close_ok = self._run_idempotent_mutation(
            mutation_key=close_issue_key,
            action=lambda: self.tracker.close_issue(issue_id=issue_id),
        )
        if not close_ok:
            logger.warning("Already-satisfied issue #%s could not be closed on GitHub.", issue_id)
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="archived",
            pr_state="closed",
            last_failure_class="already_satisfied",
            last_failure_reason=reason_text[:500],
            clear_lease=True,
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
            local_issue = self.store.get_healer_issue(issue.issue_id) or {}
            local_state = str(local_issue.get("state") or "").strip().lower()
            local_pr_number = int(local_issue.get("pr_number") or 0)
            if (
                local_state in {"queued", "claimed", "running", "verify_pending"}
                and local_pr_number > 0
                and local_pr_number == open_pr.number
            ):
                logger.info(
                    "Continuing issue #%s in state %s on existing PR #%s.",
                    issue.issue_id,
                    local_state or "unknown",
                    open_pr.number,
                )
                return True
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

    def _sync_blocked_issue_label(self, *, issue_id: str, state: str) -> None:
        if not issue_id or not bool(getattr(self.tracker, "enabled", False)):
            return
        try:
            issue = self.tracker.get_issue(issue_id=issue_id)
        except Exception as exc:
            logger.warning("Failed to load issue #%s while syncing blocked label: %s", issue_id, exc)
            return
        remote_state = str((issue or {}).get("state") or "").strip().lower()
        remote_labels = self._normalize_labels((issue or {}).get("labels"))
        should_have_label = str(state or "").strip().lower() == "blocked" and remote_state != "closed"
        has_label = _AGENT_BLOCKED_LABEL in remote_labels
        if should_have_label == has_label:
            return
        try:
            if should_have_label:
                self.tracker.add_issue_label(issue_id=issue_id, label=_AGENT_BLOCKED_LABEL)
            elif has_label:
                self.tracker.remove_issue_label(issue_id=issue_id, label=_AGENT_BLOCKED_LABEL)
        except Exception as exc:
            logger.warning("Failed to sync blocked label for issue #%s: %s", issue_id, exc)

    def _sync_outcome_issue_label(self, *, issue_id: str, label: str = "") -> None:
        if not issue_id or not bool(getattr(self.tracker, "enabled", False)):
            return
        target = self._normalize_label(label)
        if target not in _OUTCOME_LABELS:
            target = ""
        for candidate in _OUTCOME_LABELS:
            try:
                if candidate == target:
                    self.tracker.add_issue_label(issue_id=issue_id, label=candidate)
                else:
                    self.tracker.remove_issue_label(issue_id=issue_id, label=candidate)
            except Exception as exc:
                logger.warning("Failed to sync outcome label %s for issue #%s: %s", candidate, issue_id, exc)

    def _maybe_reconcile_blocked_issue_labels(self) -> None:
        interval = max(
            60.0,
            float(getattr(self.settings, "healer_blocked_label_repair_interval_seconds", 600.0)),
        )
        now = time.monotonic()
        last_repair_at = float(getattr(self, "_last_blocked_label_repair_at", 0.0))
        if last_repair_at and (now - last_repair_at) < interval:
            return
        self._last_blocked_label_repair_at = now
        self._reconcile_blocked_issue_labels()
        self._reconcile_outcome_issue_labels()

    def _reconcile_blocked_issue_labels(self) -> None:
        if not bool(getattr(self.tracker, "enabled", False)):
            return
        for row in self.store.list_healer_issues(
            states=["blocked", "resolved", "queued", "pr_open", "pr_pending_approval", "failed"],
            limit=500,
        ):
            issue_id = str(row.get("issue_id") or "").strip()
            if not issue_id:
                continue
            self._sync_blocked_issue_label(issue_id=issue_id, state=str(row.get("state") or ""))

    def _reconcile_outcome_issue_labels(self) -> None:
        if not bool(getattr(self.tracker, "enabled", False)):
            return
        for row in self.store.list_healer_issues(
            states=[
                "queued",
                "claimed",
                "running",
                "verify_pending",
                "blocked",
                "failed",
                "needs_clarification",
                "pr_open",
                "pr_pending_approval",
            ],
            limit=500,
        ):
            issue_id = str(row.get("issue_id") or "").strip()
            if not issue_id:
                continue
            desired = self._desired_outcome_label_for_issue(issue_id=issue_id, issue_row=row)
            self._sync_outcome_issue_label(issue_id=issue_id, label=desired)

    def _desired_outcome_label_for_issue(self, *, issue_id: str, issue_row: dict[str, object]) -> str:
        state = str(issue_row.get("state") or "").strip().lower()
        last_failure_class = str(issue_row.get("last_failure_class") or "").strip()
        has_backoff = bool(str(issue_row.get("backoff_until") or "").strip())
        if state == "needs_clarification":
            return _OUTCOME_LABEL_NEEDS_CLARIFICATION
        if state in {"failed", "blocked"}:
            if last_failure_class in _INFRA_FAILURE_CLASSES or last_failure_class == "infra_pause":
                return _OUTCOME_LABEL_BLOCKED_ENVIRONMENT
            return _OUTCOME_LABEL_RETRY_EXHAUSTED
        if state == "queued" and has_backoff and (
            last_failure_class in _INFRA_FAILURE_CLASSES or last_failure_class == "infra_pause"
        ):
            return _OUTCOME_LABEL_BLOCKED_ENVIRONMENT
        if state not in {"pr_open", "pr_pending_approval"}:
            return ""
        latest_attempts = self.store.list_healer_attempts(issue_id=issue_id, limit=1)
        if not latest_attempts:
            return _OUTCOME_LABEL_DONE_CODE
        latest = latest_attempts[0]
        profile = str(latest.get("validation_profile") or "").strip().lower()
        if profile == "artifact_only":
            return _OUTCOME_LABEL_DONE_ARTIFACT
        summary = latest.get("test_summary") or {}
        if isinstance(summary, dict):
            mode = str(summary.get("mode") or "").strip().lower()
            if mode == "skipped_artifact_only":
                return _OUTCOME_LABEL_DONE_ARTIFACT
        return _OUTCOME_LABEL_DONE_CODE

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
        interval = min(
            max(15.0, float(self.dispatcher.lease_seconds) / 2.0),
            max(15.0, float(getattr(self.settings, "healer_pulse_interval_seconds", 60.0))),
        )
        while not stop_event.wait(interval):
            renewed = self.store.renew_healer_issue_lease(
                issue_id=issue_id,
                worker_id=self.worker_id,
                lease_seconds=self.dispatcher.lease_seconds,
            )
            if not renewed:
                issue_record = self.store.get_healer_issue(issue_id)
                issue_state = ""
                if isinstance(issue_record, dict):
                    issue_state = str(issue_record.get("state") or "").strip().lower()
                if issue_state and issue_state not in {"claimed", "running", "verify_pending"}:
                    return
                logger.warning("Lease heartbeat stopped for issue #%s; lease could not be renewed.", issue_id)
                lease_lost.set()
                return
            self._record_worker_heartbeat(status="processing", issue_id=issue_id)

    def _backoff_or_fail(
        self,
        *,
        issue_id: str,
        attempt_no: int,
        failure_class: str,
        failure_reason: str,
        issue_body: str = "",
        feedback_context_override: str = "",
    ) -> str:
        failure_domain = classify_failure_domain(
            failure_class=failure_class,
            failure_reason=failure_reason,
        )
        self._increment_state_counter("healer_failure_domain_total")
        self._increment_state_counter(f"healer_failure_domain_{failure_domain}")
        if failure_class == "infra_pause":
            backoff_until = self._activate_infra_pause(
                failure_class=failure_class,
                failure_reason=failure_reason,
            )
            self.store.set_healer_issue_state(
                issue_id=issue_id,
                state="queued",
                backoff_until=backoff_until,
                last_failure_class=failure_class,
                last_failure_reason=failure_reason[:500],
                clear_lease=True,
            )
            self._sync_blocked_issue_label(issue_id=issue_id, state="queued")
            self._sync_outcome_issue_label(issue_id=issue_id, label=_OUTCOME_LABEL_BLOCKED_ENVIRONMENT)
            now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            self.store.set_state("healer_connector_last_error_class", failure_class)
            self.store.set_state("healer_connector_last_error_reason", failure_reason[:500])
            self.store.set_state("healer_connector_last_error_at", now_str)
            logger.warning(
                "Issue #%s paused after attempt %s until %s (%s)",
                issue_id,
                attempt_no,
                backoff_until,
                failure_class,
            )
            _hint = _failure_user_hint(failure_class, issue_body=issue_body)
            self._post_issue_status(
                issue_id=issue_id,
                body=self._format_flow_status_comment(
                    "Issue paused for infrastructure recovery",
                    "Validation failed before the code change could be trusted, so automation is waiting for the runtime lane to recover.",
                    [
                        f"Attempt: `{attempt_no}`",
                        f"Failure class: `{failure_class}`",
                        f"Reason: {self._clean_comment_text(failure_reason, max_chars=260)}",
                        f"Pause until: `{backoff_until} UTC`",
                        *([f"Hint: {_hint}"] if _hint else []),
                    ],
                ),
            )
            self._record_retry_playbook_selection(
                issue_id=issue_id,
                failure_class=failure_class,
                failure_domain=failure_domain,
                strategy="infra_pause",
                backoff_seconds=_seconds_until_utc_timestamp(backoff_until),
                feedback_hint=_hint,
            )
            return "queued"

        is_infra = failure_class in _INFRA_FAILURE_CLASSES or failure_domain == "infra"
        counts_against_trust = _counts_against_issue_trust(failure_class=failure_class, failure_reason=failure_reason)
        is_always_requeue = (
            is_infra
            or (failure_class in _ALWAYS_REQUEUE_FAILURE_CLASSES)
            or _is_no_workspace_change_failure_class(failure_class)
            or not counts_against_trust
        )

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
            self._sync_blocked_issue_label(issue_id=issue_id, state="queued")
            self._sync_outcome_issue_label(
                issue_id=issue_id,
                label=_OUTCOME_LABEL_BLOCKED_ENVIRONMENT if is_infra else "",
            )
            if is_infra:
                self._note_infra_failure(failure_class=failure_class, failure_reason=failure_reason)
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
            _hint = _failure_user_hint(failure_class, issue_body=issue_body)
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
                        *([f"Hint: {_hint}"] if _hint else []),
                    ],
                ),
            )
            strategy = "always_requeue_trust_exempt"
            if is_infra:
                strategy = "always_requeue_infra"
            elif failure_class in {"lock_conflict", "lock_upgrade_conflict"}:
                strategy = "always_requeue_lock_conflict"
            elif failure_class in _ALWAYS_REQUEUE_FAILURE_CLASSES or _is_no_workspace_change_failure_class(failure_class):
                strategy = "always_requeue_failure_class"
            self._record_retry_playbook_selection(
                issue_id=issue_id,
                failure_class=failure_class,
                failure_domain=failure_domain,
                strategy=strategy,
                backoff_seconds=delay,
                feedback_hint=_hint,
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
            self._sync_blocked_issue_label(issue_id=issue_id, state="failed")
            self._sync_outcome_issue_label(issue_id=issue_id, label=_OUTCOME_LABEL_RETRY_EXHAUSTED)
            logger.info(
                "Issue #%s reached retry budget and is now failed (%s): %s",
                issue_id,
                failure_class,
                failure_reason,
            )
            self._record_retry_playbook_selection(
                issue_id=issue_id,
                failure_class=failure_class,
                failure_domain=failure_domain,
                strategy="retry_exhausted",
                backoff_seconds=0,
                feedback_hint="Retry budget exhausted; manual intervention required.",
            )
            return "failed"

        delay = min(
            self.settings.healer_backoff_max_seconds,
            self.settings.healer_backoff_initial_seconds * (2 ** max(0, attempt_no - 1)),
        )
        strategy = dict(_FAILURE_DOMAIN_STRATEGY.get(failure_domain, {}))
        strategy.update(_FAILURE_CLASS_STRATEGY.get(failure_class, {}))
        multiplier = float(strategy.get("backoff_multiplier", 1.0))
        delay = max(15, int(delay * multiplier))
        feedback_hint = str(strategy.get("feedback_hint", "")).strip()
        retry_feedback_context = _compose_retry_feedback_context(
            feedback_hint=feedback_hint,
            override=feedback_context_override,
        )
        backoff_until = (datetime.now(UTC) + timedelta(seconds=delay)).strftime("%Y-%m-%d %H:%M:%S")
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="queued",
            backoff_until=backoff_until,
            last_failure_class=failure_class,
            last_failure_reason=failure_reason[:500],
            feedback_context=retry_feedback_context if retry_feedback_context else None,
            clear_lease=True,
        )
        self._sync_blocked_issue_label(issue_id=issue_id, state="queued")
        self._sync_outcome_issue_label(issue_id=issue_id, label="")
        logger.info(
                "Issue #%s requeued after attempt %s with backoff until %s (%s)",
                issue_id,
                attempt_no,
                backoff_until,
                failure_class,
            )
        _hint = _failure_user_hint(failure_class, issue_body=issue_body)
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
                    *([f"Hint: {_hint}"] if _hint else []),
                ],
            ),
        )
        self._record_retry_playbook_selection(
            issue_id=issue_id,
            failure_class=failure_class,
            failure_domain=failure_domain,
            strategy="adaptive_failure_strategy",
            backoff_seconds=delay,
            feedback_hint=retry_feedback_context or _hint,
        )
        return "queued"

    def _connector_health_snapshot(self, connector: ConnectorProtocol | None = None) -> dict[str, str | bool]:
        target = connector or self.connector
        try:
            target.ensure_started()
        except Exception as exc:
            return {
                "available": False,
                "configured_command": "",
                "resolved_command": "",
                "availability_reason": f"connector ensure_started failed: {exc}",
                "last_health_error": str(exc),
            }
        if hasattr(target, "health_snapshot"):
            try:
                health = target.health_snapshot()  # type: ignore[attr-defined]
                return {
                    "available": bool(health.get("available")),
                    "configured_command": str(health.get("configured_command") or ""),
                    "resolved_command": str(health.get("resolved_command") or ""),
                    "availability_reason": str(health.get("availability_reason") or ""),
                    "last_health_error": str(health.get("last_health_error") or ""),
                    "fallback_backend": str(health.get("fallback_backend") or ""),
                    "fallback_available": bool(health.get("fallback_available")),
                    "fallback_attempts": str(health.get("fallback_attempts") or ""),
                    "fallback_successes": str(health.get("fallback_successes") or ""),
                    "last_fallback_reason": str(health.get("last_fallback_reason") or ""),
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

    def _connector_health_by_backend(self) -> dict[str, dict[str, str | bool]]:
        return {
            backend: self._connector_health_snapshot(connector=backend_connector)
            for backend, backend_connector in self.connectors_by_backend.items()
        }

    def _record_connector_health(self, health: dict[str, str | bool]) -> None:
        available = "true" if bool(health.get("available")) else "false"
        self.store.set_states(
            {
                "healer_connector_available": available,
                "healer_connector_configured_command": str(health.get("configured_command") or ""),
                "healer_connector_resolved_command": str(health.get("resolved_command") or ""),
                "healer_connector_availability_reason": str(health.get("availability_reason") or ""),
                "healer_connector_last_checked_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
                "healer_connector_fallback_backend": str(health.get("fallback_backend") or ""),
                "healer_connector_fallback_available": "true" if bool(health.get("fallback_available")) else "false",
                "healer_connector_fallback_attempts": str(health.get("fallback_attempts") or ""),
                "healer_connector_fallback_successes": str(health.get("fallback_successes") or ""),
                "healer_connector_last_fallback_reason": str(health.get("last_fallback_reason") or ""),
            }
        )

    def _increment_state_counter(self, key: str, *, amount: int = 1) -> None:
        raw = str(self.store.get_state(key) or "").strip()
        try:
            current = int(raw)
        except ValueError:
            current = 0
        self.store.set_state(key, str(max(0, current + int(amount))))

    def _record_retry_playbook_selection(
        self,
        *,
        issue_id: str,
        failure_class: str,
        failure_domain: str,
        strategy: str,
        backoff_seconds: int,
        feedback_hint: str,
    ) -> None:
        class_token = _state_counter_token(failure_class)
        domain_token = _state_counter_token(failure_domain)
        strategy_token = _state_counter_token(strategy)
        self._increment_state_counter("healer_retry_playbook_total")
        self._increment_state_counter(f"healer_retry_playbook_class_{class_token}")
        self._increment_state_counter(f"healer_retry_playbook_domain_{domain_token}")
        self._increment_state_counter(f"healer_retry_playbook_strategy_{strategy_token}")
        self.store.set_states(
            {
                "healer_retry_playbook_last_issue_id": str(issue_id or ""),
                "healer_retry_playbook_last_failure_class": str(failure_class or ""),
                "healer_retry_playbook_last_failure_domain": str(failure_domain or ""),
                "healer_retry_playbook_last_strategy": str(strategy or ""),
                "healer_retry_playbook_last_backoff_seconds": str(max(0, int(backoff_seconds))),
                "healer_retry_playbook_last_feedback_hint": str(feedback_hint or "")[:500],
                "healer_retry_playbook_last_selected_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    def _record_app_server_attempt_metrics(
        self,
        *,
        connector: ConnectorProtocol,
        task_kind: str,
        had_material_diff: bool,
    ) -> None:
        if connector.__class__.__name__ != "CodexAppServerConnector":
            return
        normalized_task_kind = str(task_kind or "").strip().lower() or "unknown"
        self._increment_state_counter("app_server_attempts")
        self._increment_state_counter(f"app_server_attempts_task_kind_{normalized_task_kind}")
        if had_material_diff:
            self._increment_state_counter("app_server_attempts_with_material_diff")
            return
        self._increment_state_counter("app_server_attempts_with_zero_diff")
        self._increment_state_counter(f"app_server_attempts_with_zero_diff_task_kind_{normalized_task_kind}")

    def _record_app_server_recovery_metrics(
        self,
        *,
        connector: ConnectorProtocol,
        workspace_status: dict[str, object] | None,
    ) -> None:
        if connector.__class__.__name__ != "CodexAppServerConnector":
            return
        status = workspace_status or {}
        if bool(status.get("app_server_forced_serialized_recovery_attempted")):
            self._increment_state_counter("app_server_forced_serialized_recovery_attempts")
        if bool(status.get("app_server_forced_serialized_recovery_succeeded")):
            self._increment_state_counter("app_server_forced_serialized_recovery_success")
        if bool(status.get("app_server_exec_failover_attempted")):
            self._increment_state_counter("app_server_exec_failover_attempts")
        if bool(status.get("app_server_exec_failover_succeeded")):
            self._increment_state_counter("app_server_exec_failover_success")

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
        contamination = workspace_status or {}
        contamination_paths = contamination.get("contamination_paths") or contamination.get("cleaned_paths") or []
        rendered = ", ".join(str(item).strip() for item in contamination_paths if str(item).strip())
        self.store.set_states(
            {
                "healer_last_failure_fingerprint": failure_fingerprint,
                "healer_last_failure_fingerprint_issue_id": issue_id,
                "healer_last_failure_fingerprint_class": failure_class,
                "healer_last_contamination_paths": rendered,
            }
        )

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
            attempt_failure_class = str(attempt.get("failure_class") or "").strip()
            if attempt_failure_class in _QUARANTINE_NEUTRAL_FAILURE_CLASSES:
                continue
            attempt_fingerprint = self._attempt_failure_fingerprint(
                attempt=attempt,
                current_failure_fingerprint=failure_fingerprint,
            )
            if attempt_fingerprint != failure_fingerprint:
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
        self._sync_blocked_issue_label(issue_id=issue_id, state="blocked")
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

    @staticmethod
    def _attempt_failure_fingerprint(*, attempt: dict[str, Any], current_failure_fingerprint: str) -> str:
        summary = attempt.get("test_summary") or {}
        persisted = str(summary.get("failure_fingerprint") or "").strip()
        if persisted:
            return persisted
        parts = current_failure_fingerprint.split("|")
        if len(parts) != 3:
            return ""
        if parts[0] != "execution_contract":
            return ""
        attempt_failure_class = str(attempt.get("failure_class") or "").strip()
        if (
            attempt_failure_class not in _EXECUTION_CONTRACT_FAILURE_CLASSES
            and not _is_no_workspace_change_failure_class(attempt_failure_class)
        ):
            return ""
        if attempt_failure_class == "no_workspace_change" and _is_no_workspace_change_failure_class(parts[2]):
            return current_failure_fingerprint
        return f"{parts[0]}|{parts[1]}|{attempt_failure_class}"

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

    def _record_tracker_error(self, *, failure_class: str, failure_reason: str) -> None:
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        self.store.set_states(
            {
                "healer_tracker_last_error_class": str(failure_class or "")[:120],
                "healer_tracker_last_error_reason": str(failure_reason or "")[:500],
                "healer_tracker_last_error_at": now_str,
            }
        )

    @staticmethod
    def _classify_tracker_failure(error_class: str) -> str:
        normalized = str(error_class or "").strip().lower()
        if normalized in {"github_auth_missing", "github_repo_unconfigured"}:
            return "github_auth_missing"
        if normalized == "github_network_error":
            return "github_network_error"
        if normalized == "github_rate_limited":
            return "github_rate_limited"
        if normalized == "github_api_error":
            return "github_api_error"
        return "pr_open_failed"

    def _note_infra_failure(self, *, failure_class: str, failure_reason: str) -> None:
        if failure_class not in _INFRA_FAILURE_CLASSES:
            return
        streak = self._coerce_int(self.store.get_state("healer_infra_failure_streak"), default=0) + 1
        self.store.set_states({"healer_infra_failure_streak": str(streak)})
        threshold = max(1, int(getattr(self.settings, "healer_infra_dlq_threshold", 8)))
        if streak < threshold:
            return
        cooldown_seconds = max(60, int(getattr(self.settings, "healer_infra_dlq_cooldown_seconds", 3600)))
        pause_until = datetime.now(UTC) + timedelta(seconds=cooldown_seconds)
        pause_until_str = pause_until.strftime("%Y-%m-%d %H:%M:%S")
        self.store.set_states(
            {
                "healer_infra_pause_until": pause_until_str,
                "healer_infra_pause_reason": f"{failure_class}: {failure_reason[:300]}",
            }
        )
        logger.warning(
            "Infra failure streak reached %d/%d. Pausing claims until %s.",
            streak,
            threshold,
            pause_until_str,
        )

    def _activate_infra_pause(self, *, failure_class: str, failure_reason: str) -> str:
        cooldown_seconds = max(300, int(getattr(self.settings, "healer_infra_dlq_cooldown_seconds", 3600)))
        pause_until = datetime.now(UTC) + timedelta(seconds=cooldown_seconds)
        pause_until_str = pause_until.strftime("%Y-%m-%d %H:%M:%S")
        self.store.set_states(
            {
                "healer_infra_failure_streak": str(
                    max(1, self._coerce_int(self.store.get_state("healer_infra_failure_streak"), default=0) + 1)
                ),
                "healer_infra_pause_until": pause_until_str,
                "healer_infra_pause_reason": f"{failure_class}: {failure_reason[:300]}",
            }
        )
        logger.warning(
            "Infra pause activated until %s (%s).",
            pause_until_str,
            failure_class,
        )
        return pause_until_str

    def _reset_infra_failure_streak(self) -> None:
        self.store.set_states(
            {
                "healer_infra_failure_streak": "0",
                "healer_infra_pause_until": "",
                "healer_infra_pause_reason": "",
            }
        )

    def _infra_pause_active(self) -> bool:
        raw = str(self.store.get_state("healer_infra_pause_until") or "").strip()
        if not raw:
            return False
        reason = str(self.store.get_state("healer_infra_pause_reason") or "").strip()
        if self._infra_pause_reason_is_resolved(reason):
            self._reset_infra_failure_streak()
            return False
        try:
            pause_until = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            return False
        return datetime.now(UTC) < pause_until

    def _infra_pause_reason_is_resolved(self, reason: str) -> bool:
        normalized = str(reason or "").strip().lower()
        if not normalized:
            return True
        if "requires `pnpm`" in normalized:
            return shutil.which("pnpm") is not None
        if "requires `yarn`" in normalized:
            return shutil.which("yarn") is not None
        if "requires `bun`" in normalized:
            return shutil.which("bun") is not None
        if "missing issue worktree" in normalized or "workspace orchestration" in normalized:
            running_rows = self.store.list_healer_issues(states=["running", "claimed", "verify_pending"], limit=5)
            return len(running_rows) == 0
        if "lease lost during processing" in normalized:
            return True
        return False

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

    def _issue_contract_mode(self) -> str:
        raw = str(getattr(self.settings, "healer_issue_contract_mode", "lenient") or "lenient")
        normalized = raw.strip().lower()
        return normalized if normalized in {"strict", "lenient"} else "lenient"

    def _parse_confidence_threshold(self) -> float:
        raw = getattr(self.settings, "healer_parse_confidence_threshold", 0.3)
        try:
            threshold = float(raw)
        except (TypeError, ValueError):
            threshold = 0.3
        return max(0.0, min(1.0, threshold))

    def _clarification_reasons_for_task_spec(self, *, task_spec: HealerTaskSpec) -> list[str]:
        lint = lint_issue_contract(
            issue_title="",
            issue_body="",
            task_spec=task_spec,
            contract_mode=self._issue_contract_mode(),
            parse_confidence_threshold=self._parse_confidence_threshold(),
        )
        return list(lint.reason_codes)

    @staticmethod
    def _build_needs_clarification_comment(
        reasons: list[str] | None = None,
        task_spec: HealerTaskSpec | None = None,
    ) -> str:
        reason_lines: list[str] = []
        normalized_reasons = [str(item or "").strip() for item in (reasons or []) if str(item or "").strip()]
        reason_map = {
            "low_confidence": "Parser confidence is below the configured threshold for autonomous edits.",
            "missing_required_outputs": "Strict issue-contract mode requires `Required code outputs:`.",
            "missing_validation": "Strict issue-contract mode requires a `Validation:` command.",
            "ambiguous_execution_root": "The issue maps to multiple execution roots, so the runtime scope is ambiguous.",
        }
        for reason in normalized_reasons:
            rendered = reason_map.get(reason, reason.replace("_", " "))
            reason_lines.append(f"- {rendered}")
        reason_block = ""
        if reason_lines:
            reason_block = "Detected issue-contract gaps:\n" + "\n".join(reason_lines) + "\n\n"
        suggested_root = ""
        output_targets: tuple[str, ...] = ()
        validation_placeholder = "Validation: pytest tests/test_auth.py -v"
        if task_spec is not None:
            output_targets = tuple(str(path or "").strip() for path in task_spec.output_targets if str(path or "").strip())
            lint = lint_issue_contract(
                issue_title="",
                issue_body="",
                task_spec=task_spec,
                contract_mode="strict",
                parse_confidence_threshold=0.0,
            )
            suggested_root = lint.suggested_execution_root
            if task_spec.validation_commands:
                validation_placeholder = f"Validation: {task_spec.validation_commands[0]}"
            elif suggested_root:
                validation_placeholder = f"Validation: cd {suggested_root} && <run-your-checks>"
        suggested_contract_lines = [
            "Suggested issue-contract skeleton:",
            "```",
            "Required code outputs:",
        ]
        if output_targets:
            suggested_contract_lines.extend(f"- {path}" for path in output_targets)
        else:
            suggested_contract_lines.extend(["- src/auth/login.py", "- tests/test_auth.py"])
        if suggested_root:
            suggested_contract_lines.extend(["", "Execution root:", f"- {suggested_root}"])
        suggested_contract_lines.extend(["", validation_placeholder, "```"])
        suggested_contract = "\n".join(suggested_contract_lines)
        return (
            "## Flow Healer — Needs Clarification\n\n"
            "This issue doesn't have enough structured information for me to reliably generate a fix.\n"
            f"{reason_block}"
            "Please update the issue body with a tighter execution contract so the next run can stay scoped and verifiable.\n\n"
            f"{suggested_contract}\n\n"
            "If you need to fill it in manually, include these sections:\n\n"
            "**Required code outputs** (the files I should edit):\n"
            "```\n"
            "Required code outputs:\n"
            "- src/auth/login.py\n"
            "- tests/test_auth.py\n"
            "```\n\n"
            "**Execution root** (the directory commands should run from when multiple roots are possible):\n"
            "```\n"
            "Execution root:\n"
            "- e2e-smoke/node\n"
            "```\n\n"
            "**Validation command** (how to verify the fix):\n"
            "```\n"
            "Validation: pytest tests/test_auth.py -v\n"
            "```\n\n"
            "-- Flow Healer"
        )

    @staticmethod
    def _format_flow_status_comment(
        title: str,
        intro: str | None,
        bullets: list[str],
        *,
        outro: str | None = None,
    ) -> str:
        heading = AutonomousHealerLoop._status_heading(title)
        signoff = AutonomousHealerLoop._status_signoff(title)
        lines = [f"### {heading}", ""]
        if intro:
            lines.extend([intro.strip(), ""])
        lines.extend(f"- {item}" for item in bullets if item.strip())
        if outro:
            lines.extend(["", outro.strip()])
        lines.extend(["", signoff])
        return "\n".join(lines)

    @staticmethod
    def _status_heading(title: str) -> str:
        normalized = (title or "").strip()
        heading_map = {
            "Started automated fix attempt": "🛠️ Flow Healer is on it",
            "Patch is ready for approval": "✨ Patch is ready for a human thumbs-up",
            "Pull request opened or updated": "🚀 Fresh PR energy",
            "Attempt failed": "😵‍💫 Hit a snag this round",
            "Issue requeued automatically": "🔁 Automatic retry queued up",
            "Issue requeued for another attempt": "🎯 Taking another swing",
            "Repeated failure pattern detected; issue paused": "🧯 Same snag, smart pause",
        }
        flair = heading_map.get(normalized)
        if flair:
            return f"{flair} · {normalized}"
        return f"🤖 {normalized}" if normalized else "🤖 Flow Healer update"

    @staticmethod
    def _status_signoff(title: str) -> str:
        normalized = (title or "").strip()
        if normalized == "Pull request opened or updated":
            return "-- Flow Healer 🤖✨"
        if normalized in {"Issue requeued automatically", "Issue requeued for another attempt"}:
            return "-- Flow Healer, warming up another pass 🔁"
        if normalized == "Attempt failed":
            return "-- Flow Healer, regrouping for the next round 🧰"
        if normalized == "Repeated failure pattern detected; issue paused":
            return "-- Flow Healer, pausing here so we don't thrash 🧯"
        return "-- Flow Healer 🤖"

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
    def _format_evidence_bullets(cls, summary: dict[str, object] | None) -> list[str]:
        if not summary:
            return []
        bundle = summary.get("artifact_bundle")
        bundle_dict = dict(bundle) if isinstance(bundle, dict) else {}
        links = cls._normalized_artifact_links(summary.get("artifact_links"))
        if not bundle_dict and not links:
            return []
        bullets: list[str] = []
        bundle_status = cls._clean_comment_text(bundle_dict.get("status") or "", max_chars=40)
        if bundle_status:
            bullets.append(f"Evidence bundle: `{bundle_status}`")
        artifact_root = cls._clean_comment_text(bundle_dict.get("artifact_root") or "", max_chars=180)
        if artifact_root:
            bullets.append(f"Evidence root: `{artifact_root}`")
        published_branch = cls._clean_comment_text(bundle_dict.get("github_artifact_branch") or "", max_chars=80)
        if published_branch:
            bullets.append(f"Published branch: `{published_branch}`")
        if isinstance(bundle_dict.get("journey_transcript"), list):
            bullets.append(f"Journey transcripts: `{len(bundle_dict.get('journey_transcript') or [])}` phase(s)")
        preferred_labels = (
            "failure_screenshot",
            "resolution_screenshot",
            "failure_video",
            "resolution_video",
            "failure_console_log",
            "resolution_console_log",
            "failure_network_log",
            "resolution_network_log",
            "journey_transcript",
        )
        for label in preferred_labels:
            target = next((item for item in links if item["label"] == label), None)
            if target is None:
                continue
            target_markdown = cls._artifact_link_reference(target)
            bullets.append(f"{label.replace('_', ' ').title()}: {target_markdown}")
        return bullets

    @classmethod
    def _normalized_artifact_links(cls, raw_links: object) -> list[dict[str, str]]:
        if not isinstance(raw_links, list):
            return []
        normalized: list[dict[str, str]] = []
        for item in raw_links:
            if not isinstance(item, dict):
                continue
            label = cls._clean_comment_text(item.get("label") or "", max_chars=80)
            path = cls._clean_comment_text(item.get("path") or "", max_chars=240)
            href = cls._clean_comment_text(item.get("href") or "", max_chars=400)
            raw_href = cls._clean_comment_text(item.get("raw_href") or "", max_chars=400)
            download_href = cls._clean_comment_text(item.get("download_href") or "", max_chars=400)
            published_path = cls._clean_comment_text(item.get("published_path") or "", max_chars=240)
            target = path or href
            if not label or not target:
                continue
            normalized.append(
                {
                    "label": label,
                    "target": target,
                    "path": path,
                    "href": href,
                    "raw_href": raw_href,
                    "download_href": download_href,
                    "published_path": published_path,
                }
            )
        return normalized

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
            f"Flow Healer rolled in with an automated proposal for issue #{issue_id}.",
            "",
            "A quick heads-up before you review: this branch was assembled by the agent, then checked against the current validation gates.",
            "",
            "### Verification",
            f"- Verifier: `{verifier_line}`",
            "",
            "### Test Summary",
        ]
        lines.extend(f"- {item}" for item in cls._format_test_summary_bullets(test_summary))
        evidence_lines = cls._format_pr_evidence_lines(test_summary)
        if evidence_lines:
            lines.extend(["", "### Evidence"])
            lines.extend(evidence_lines)
        lines.extend(["", "_Built with a little hustle by Flow Healer 🤖✨_"])
        return "\n".join(lines) + "\n"

    def _publish_pr_artifacts(
        self,
        *,
        issue_id: str,
        attempt_id: str,
        base_branch: str,
        test_summary: dict[str, object] | None,
    ) -> dict[str, object]:
        summary = dict(test_summary or {})
        if not bool(getattr(self.settings, "healer_github_artifact_publish_enabled", True)):
            return summary
        publish_fn = getattr(self.tracker, "publish_artifact_files", None)
        if not callable(publish_fn):
            return summary
        artifact_links = self._normalized_artifact_links(summary.get("artifact_links"))
        artifact_bundle = summary.get("artifact_bundle")
        bundle_dict = dict(artifact_bundle) if isinstance(artifact_bundle, dict) else {}
        publish_paths: list[Path] = []
        by_name: dict[str, dict[str, str]] = {}
        for link in artifact_links:
            local_path = Path(str(link.get("path") or "")).expanduser()
            if not local_path.is_file():
                continue
            publish_paths.append(local_path)
            by_name[local_path.name] = link
        transcript_path = self._write_journey_transcript_artifact(bundle_dict)
        if transcript_path is not None:
            publish_paths.append(transcript_path)
        if not publish_paths:
            return summary
        artifact_branch = str(
            getattr(self.settings, "healer_github_artifact_branch", "flow-healer-artifacts") or "flow-healer-artifacts"
        ).strip() or "flow-healer-artifacts"
        published_artifacts = publish_fn(
            issue_id=issue_id,
            files=publish_paths,
            branch=artifact_branch,
            source_branch=str(base_branch or "main").strip() or "main",
            run_key=str(attempt_id or "latest").strip() or "latest",
        )
        if not isinstance(published_artifacts, list) or not published_artifacts:
            return summary
        enriched_links = [dict(item) for item in artifact_links]
        published_root = ""
        for published in published_artifacts:
            name = str(getattr(published, "name", "") or "").strip()
            html_url = str(getattr(published, "html_url", "") or "").strip()
            markdown_url = str(getattr(published, "markdown_url", "") or "").strip()
            download_url = str(getattr(published, "download_url", "") or "").strip()
            remote_path = str(getattr(published, "remote_path", "") or "").strip()
            published_branch = str(getattr(published, "branch", "") or "").strip()
            if remote_path and not published_root:
                published_root = str(Path(remote_path).parent).replace("\\", "/")
            existing = by_name.get(name)
            if existing is not None:
                target = next((item for item in enriched_links if item.get("label") == existing.get("label")), None)
                if target is None:
                    target = dict(existing)
                    enriched_links.append(target)
                target["href"] = html_url
                target["raw_href"] = markdown_url
                target["download_href"] = download_url
                target["published_path"] = remote_path
                target["published_branch"] = published_branch
                continue
            if name == "journey-transcript.json":
                enriched_links.append(
                    {
                        "label": "journey_transcript",
                        "path": str(transcript_path) if transcript_path is not None else "",
                        "href": html_url,
                        "raw_href": markdown_url,
                        "download_href": download_url,
                        "published_path": remote_path,
                        "published_branch": published_branch,
                    }
                )
        if bundle_dict:
            bundle_dict["github_artifact_branch"] = artifact_branch
            if published_root:
                bundle_dict["github_artifact_root"] = published_root
            summary["artifact_bundle"] = bundle_dict
        summary["artifact_links"] = enriched_links
        return summary

    @classmethod
    def _write_journey_transcript_artifact(cls, bundle: dict[str, object]) -> Path | None:
        transcript = bundle.get("journey_transcript")
        if not isinstance(transcript, list) or not transcript:
            return None
        artifact_root = str(bundle.get("artifact_root") or "").strip()
        if not artifact_root:
            return None
        root_path = Path(artifact_root).expanduser()
        if not root_path.exists():
            return None
        transcript_path = root_path / "journey-transcript.json"
        transcript_path.write_text(json.dumps(transcript, indent=2) + "\n", encoding="utf-8")
        return transcript_path

    @classmethod
    def _format_pr_evidence_lines(cls, summary: dict[str, object] | None) -> list[str]:
        if not summary:
            return []
        links = cls._normalized_artifact_links(summary.get("artifact_links"))
        if not links and not isinstance(summary.get("artifact_bundle"), dict):
            return []
        lines: list[str] = []
        failure_screenshot = cls._artifact_link_by_label(links, "failure_screenshot")
        resolution_screenshot = cls._artifact_link_by_label(links, "resolution_screenshot")
        if failure_screenshot and resolution_screenshot:
            lines.extend(
                [
                    "| Before | After |",
                    "| --- | --- |",
                    (
                        f"| {cls._artifact_inline_image_markdown(failure_screenshot, alt='Failure screenshot')} "
                        f"| {cls._artifact_inline_image_markdown(resolution_screenshot, alt='Resolution screenshot')} |"
                    ),
                    "",
                ]
            )
        elif failure_screenshot or resolution_screenshot:
            screenshot = failure_screenshot or resolution_screenshot
            title = "Before" if failure_screenshot else "After"
            lines.extend([f"**{title}**", cls._artifact_inline_image_markdown(screenshot, alt=f"{title} screenshot"), ""])
        published_branch = str(
            (summary.get("artifact_bundle") or {}).get("github_artifact_branch")
            if isinstance(summary.get("artifact_bundle"), dict)
            else ""
        ).strip()
        evidence_bullets = []
        for item in cls._format_evidence_bullets(summary):
            normalized = item.lower()
            if normalized.startswith("failure screenshot:") or normalized.startswith("resolution screenshot:"):
                continue
            if normalized.startswith("failure video:") or normalized.startswith("resolution video:"):
                continue
            if published_branch and normalized.startswith("evidence root:"):
                continue
            evidence_bullets.append(item)
        lines.extend(f"- {item}" for item in evidence_bullets)
        operational_links = cls._format_operational_artifact_links(links)
        if operational_links:
            lines.extend(["", f"Operational links: {operational_links}"])
        transcript_lines = cls._format_transcript_details(summary)
        if transcript_lines:
            lines.extend(["", *transcript_lines])
        return lines

    @classmethod
    def _format_operational_artifact_links(cls, links: list[dict[str, str]]) -> str:
        labels = (
            "failure_console_log",
            "failure_network_log",
            "resolution_console_log",
            "resolution_network_log",
            "journey_transcript",
        )
        chunks: list[str] = []
        for label in labels:
            link = cls._artifact_link_by_label(links, label)
            if link is None:
                continue
            chunks.append(cls._artifact_link_markdown(link, title=label.replace("_", " ")))
        return ", ".join(chunks)

    @classmethod
    def _format_transcript_details(cls, summary: dict[str, object]) -> list[str]:
        bundle = summary.get("artifact_bundle")
        bundle_dict = dict(bundle) if isinstance(bundle, dict) else {}
        transcript = bundle_dict.get("journey_transcript")
        if not isinstance(transcript, list) or not transcript:
            return []
        lines = ["<details>", "<summary>Journey transcript</summary>", ""]
        for phase_payload in transcript:
            if not isinstance(phase_payload, dict):
                continue
            phase = cls._clean_comment_text(phase_payload.get("phase") or "journey", max_chars=40) or "journey"
            lines.append(f"**{phase.title()}**")
            entries = phase_payload.get("transcript")
            if not isinstance(entries, list) or not entries:
                lines.append("1. No recorded steps")
                lines.append("")
                continue
            for index, entry in enumerate(entries[:8], start=1):
                if not isinstance(entry, dict):
                    continue
                step = cls._clean_comment_text(entry.get("step") or "step", max_chars=160) or "step"
                status = cls._clean_comment_text(entry.get("status") or "unknown", max_chars=40) or "unknown"
                error = cls._clean_comment_text(entry.get("error") or "", max_chars=160)
                suffix = f" - {status}"
                if error:
                    suffix += f" ({error})"
                lines.append(f"{index}. `{step}`{suffix}")
            if len(entries) > 8:
                lines.append(f"9. ... +{len(entries) - 8} more step(s)")
            lines.append("")
        lines.append("</details>")
        return lines

    @staticmethod
    def _artifact_link_by_label(links: list[dict[str, str]], label: str) -> dict[str, str] | None:
        return next((item for item in links if item.get("label") == label), None)

    @classmethod
    def _artifact_inline_image_markdown(cls, link: dict[str, str], *, alt: str) -> str:
        raw_href = str(link.get("raw_href") or link.get("href") or "").strip()
        href = str(link.get("href") or raw_href).strip()
        alt_text = cls._clean_comment_text(alt, max_chars=80) or "Evidence image"
        if not raw_href:
            return cls._artifact_link_reference(link)
        image_markdown = f"![{alt_text}]({raw_href})"
        if href and href != raw_href:
            return f"[{image_markdown}]({href})"
        return image_markdown

    @classmethod
    def _artifact_link_markdown(cls, link: dict[str, str], *, title: str) -> str:
        href = str(link.get("href") or link.get("raw_href") or "").strip()
        label = cls._clean_comment_text(title, max_chars=80) or "artifact"
        if href:
            return f"[{label}]({href})"
        return cls._artifact_link_reference(link)

    @classmethod
    def _artifact_link_reference(cls, link: dict[str, str]) -> str:
        href = str(link.get("href") or "").strip()
        if href:
            return f"[view evidence]({href})"
        target = cls._clean_comment_text(link.get("target") or "", max_chars=180)
        return f"`{target}`"

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
    def _resolve_staged_diff_content(*, run_result: Any, workspace: Path) -> str:
        content = str(getattr(run_result, "staged_diff_content", "") or "").strip()
        if content:
            return content
        try:
            diff = subprocess.run(
                ["git", "-C", str(workspace), "diff", "--cached"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except Exception:
            return ""
        if diff.returncode != 0:
            return ""
        return (diff.stdout or "").strip()

    @staticmethod
    def _resolve_staged_diff_metadata(*, run_result: Any) -> dict[str, object]:
        raw = getattr(run_result, "staged_diff_metadata", None)
        if isinstance(raw, dict):
            return dict(raw)
        metadata: dict[str, object] = {}
        diff_files = getattr(run_result, "diff_files", None)
        diff_lines = getattr(run_result, "diff_lines", None)
        if diff_files is not None:
            try:
                metadata["diff_files"] = int(diff_files)
            except (TypeError, ValueError):
                pass
        if diff_lines is not None:
            try:
                metadata["diff_lines"] = int(diff_lines)
            except (TypeError, ValueError):
                pass
        workspace_status = getattr(run_result, "workspace_status", None)
        if isinstance(workspace_status, dict):
            staged_paths = workspace_status.get("staged_paths")
            if isinstance(staged_paths, list):
                metadata["staged_paths"] = [str(path) for path in staged_paths if str(path).strip()]
            execution_root = str(workspace_status.get("execution_root") or "").strip()
            if execution_root:
                metadata["execution_root"] = execution_root
        return metadata

    @staticmethod
    def _resolve_attempt_runtime_summary(
        *,
        test_summary: dict[str, object] | None,
        workspace_status: dict[str, object] | None,
    ) -> dict[str, object]:
        if isinstance(test_summary, dict):
            runtime_summary = test_summary.get("runtime_summary")
            if isinstance(runtime_summary, dict):
                return dict(runtime_summary)
        if isinstance(workspace_status, dict):
            runtime_summary = workspace_status.get("runtime_summary")
            if isinstance(runtime_summary, dict):
                return dict(runtime_summary)
            app_runtime = workspace_status.get("app_runtime")
            if isinstance(app_runtime, dict):
                return {"app_harness": dict(app_runtime)}
        return {}

    @staticmethod
    def _resolve_attempt_artifact_bundle(
        *,
        test_summary: dict[str, object] | None,
        workspace_status: dict[str, object] | None,
    ) -> dict[str, object]:
        if isinstance(test_summary, dict):
            artifact_bundle = test_summary.get("artifact_bundle")
            if isinstance(artifact_bundle, dict):
                return dict(artifact_bundle)
        if isinstance(workspace_status, dict):
            artifact_bundle = workspace_status.get("artifact_bundle")
            if isinstance(artifact_bundle, dict):
                return dict(artifact_bundle)
        return {}

    @staticmethod
    def _resolve_attempt_artifact_links(
        *,
        test_summary: dict[str, object] | None,
        workspace_status: dict[str, object] | None,
    ) -> list[dict[str, object]]:
        if isinstance(test_summary, dict):
            artifact_links = test_summary.get("artifact_links")
            if isinstance(artifact_links, list):
                return [dict(item) for item in artifact_links if isinstance(item, dict)]
        if isinstance(workspace_status, dict):
            artifact_links = workspace_status.get("artifact_links")
            if isinstance(artifact_links, list):
                return [dict(item) for item in artifact_links if isinstance(item, dict)]
        return []

    @staticmethod
    def _resolve_attempt_judgment_reason_code(
        *,
        test_summary: dict[str, object] | None,
        workspace_status: dict[str, object] | None,
    ) -> str:
        if isinstance(test_summary, dict):
            value = str(test_summary.get("judgment_reason_code") or "").strip()
            if value:
                return value[:120]
        if isinstance(workspace_status, dict):
            value = str(workspace_status.get("judgment_reason_code") or "").strip()
            if value:
                return value[:120]
        return ""

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


def _normalize_repo_relative_path(value: str) -> str:
    text = (value or "").strip().replace("\\", "/")
    if not text:
        return ""
    if text.startswith("/"):
        return ""
    while text.startswith("./"):
        text = text[2:]
    parts = []
    for part in text.split("/"):
        chunk = part.strip()
        if not chunk or chunk == ".":
            continue
        if chunk == "..":
            return ""
        if ":" in chunk:
            return ""
        parts.append(chunk)
    return "/".join(parts).strip("/").lower()


def _sanitize_execution_root(*, execution_root: str, workspace: Path) -> str:
    normalized = _normalize_repo_relative_path(execution_root)
    if not normalized:
        return ""
    candidate = (workspace / normalized).resolve()
    workspace_root = workspace.resolve()
    if candidate == workspace_root:
        return ""
    try:
        candidate.relative_to(workspace_root)
    except ValueError:
        return ""
    return normalized


def _compose_retry_feedback_context(*, feedback_hint: str, override: str) -> str:
    parts = []
    hint = str(feedback_hint or "").strip()
    if hint:
        parts.append(hint)
    extra = str(override or "").strip()
    if extra:
        parts.append(extra)
    return "\n".join(parts)[:500]


def _append_swarm_cycle(summary: dict[str, object], outcome: SwarmRecoveryOutcome) -> dict[str, object]:
    cycles = []
    existing = summary.get("cycles") if isinstance(summary, dict) else None
    if isinstance(existing, list):
        cycles.extend(existing)
    cycles.append(outcome.as_summary())
    return {"cycles": cycles}


def _format_swarm_retry_feedback(summary: dict[str, object]) -> str:
    cycles = summary.get("cycles") if isinstance(summary, dict) else None
    if not isinstance(cycles, list) or not cycles:
        return ""
    latest = cycles[-1] if isinstance(cycles[-1], dict) else {}
    strategy = str(latest.get("strategy") or "").strip()
    summary_text = re.sub(r"\s+", " ", str(latest.get("summary") or "").strip())[:220]
    roles = latest.get("roles")
    role_names: list[str] = []
    if isinstance(roles, list):
        role_names = [
            str(item.get("role") or "").strip()
            for item in roles
            if isinstance(item, dict) and str(item.get("role") or "").strip()
        ]
    lines = [
        "[swarm_feedback]",
        f"strategy={strategy or 'unknown'}",
        f"summary={summary_text}",
        f"roles={','.join(role_names)}" if role_names else "roles=",
        "[/swarm_feedback]",
    ]
    return "\n".join(lines)[:420]


def _format_verifier_retry_feedback(
    *,
    verdict: str,
    hard_failure: bool,
    parse_error: bool,
    summary: str,
) -> str:
    summary_text = re.sub(r"\s+", " ", str(summary or "").strip())[:260]
    verdict_text = str(verdict or "hard_fail").strip().lower() or "hard_fail"
    lines = [
        "[verifier_feedback]",
        f"verdict={verdict_text}",
        f"hard_failure={'true' if hard_failure else 'false'}",
        f"parse_error={'true' if parse_error else 'false'}",
        f"summary={summary_text}",
        "[/verifier_feedback]",
    ]
    return "\n".join(lines)[:420]


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


def _is_no_workspace_change_failure_class(failure_class: str) -> bool:
    normalized = str(failure_class or "").strip()
    return normalized == "no_workspace_change" or normalized.startswith("no_workspace_change:")


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


def _is_issue_scoped_sql_validation_task(task_spec: HealerTaskSpec | None) -> bool:
    if task_spec is None:
        return False
    assertion_targets = [
        str(path or "").strip().replace("\\", "/").lstrip("./")
        for path in task_spec.output_targets
        if str(path or "").strip().lower().endswith(".sql")
        and "/assertions/" in str(path or "").strip().replace("\\", "/")
    ]
    if not assertion_targets:
        return False
    return any(_SQL_VALIDATION_COMMAND_RE.search(str(command or "")) for command in task_spec.validation_commands)


def _collect_targeted_tests(
    *,
    issue_body: str,
    output_targets: list[str] | tuple[str, ...],
    workspace: Path,
    language: str,
    execution_root: str = "",
) -> list[str]:
    execution_root = _normalize_repo_relative_path(execution_root)
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
    execution_root = _normalize_repo_relative_path(execution_root)
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
    execution_root = _normalize_repo_relative_path(execution_root)
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
    execution_root = _normalize_repo_relative_path(execution_root)
    cleaned = str(target or "").strip().lstrip("./")
    if execution_root and cleaned.startswith(f"{execution_root}/"):
        return cleaned[len(execution_root) + 1 :]
    return cleaned


def _default_backend_for_connector(connector: ConnectorProtocol) -> str:
    class_name = connector.__class__.__name__
    if class_name == "CodexAppServerConnector":
        return "app_server"
    if class_name == "ClaudeCliConnector":
        return "claude_cli"
    if class_name == "ClineConnector":
        return "cline"
    if class_name == "KiloCliConnector":
        return "kilo_cli"
    return "exec"
