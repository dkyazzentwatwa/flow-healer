from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from .claude_cli_connector import ClaudeCliConnector
from .cline_connector import ClineConnector
from .codex_app_server_connector import CodexAppServerConnector
from .codex_cli_connector import CodexCliConnector
from .config import AppConfig, RelaySettings
from .fallback_connector import FailoverConnector
from .healer_loop import AutonomousHealerLoop
from .healer_preflight import (
    list_cached_preflight_reports,
    preflight_readiness_assessment,
    summarize_preflight_readiness,
)
from .healer_reconciler import HealerReconciler
from .healer_scan import FlowHealerScanner
from .healer_tracker import GitHubHealerTracker
from .healer_triage import classify_issue_route
from .kilo_cli_connector import KiloCliConnector
from .local_healer_tracker import LocalHealerTracker
from .protocols import ConnectorProtocol
from .skill_contracts import audit_skill_contracts
from .store import SQLiteStore


@dataclass(slots=True)
class RepoRuntime:
    settings: RelaySettings
    store: SQLiteStore
    loop: AutonomousHealerLoop
    tracker: GitHubHealerTracker | LocalHealerTracker
    connector: object
    connectors_by_backend: dict[str, ConnectorProtocol]


@dataclass(slots=True)
class StatusSnapshot:
    rows: list[dict[str, object]]
    generated_at: float


class FlowHealerService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._status_cache: dict[str, StatusSnapshot] = {}
        self._status_cache_lock = Lock()

    def build_runtime(self, repo: RelaySettings) -> RepoRuntime:
        store = SQLiteStore(
            self.config.repo_db_path(repo.repo_name),
            busy_timeout_ms=repo.healer_sqlite_busy_timeout_ms,
        )
        store.bootstrap()
        if self.config.service.tracker_backend == "local_fs":
            tracker = LocalHealerTracker(
                repo_path=Path(repo.healer_repo_path),
                state_root=self.config.state_root_path() / "repos" / repo.repo_name / "local_tracker",
            )
        else:
            tracker = GitHubHealerTracker(
                repo_path=Path(repo.healer_repo_path),
                token=os.getenv(self.config.service.github_token_env, "").strip(),
                api_base_url=self.config.service.github_api_base_url,
                mutation_min_interval_ms=repo.healer_github_mutation_min_interval_ms,
                retry_respect_retry_after=repo.healer_retry_respect_retry_after,
                retry_jitter_mode=repo.healer_retry_jitter_mode,
                retry_max_backoff_seconds=repo.healer_retry_max_backoff_seconds,
                poll_use_conditional_requests=repo.healer_poll_use_conditional_requests,
                poll_etag_ttl_seconds=repo.healer_poll_etag_ttl_seconds,
            )
        connector_cache: dict[str, ConnectorProtocol] = {}

        def _build_connector(backend: str) -> ConnectorProtocol:
            cached = connector_cache.get(backend)
            if cached is not None:
                return cached
            if backend == "app_server":
                connector = CodexAppServerConnector(
                    workspace=repo.healer_repo_path,
                    codex_command=self.config.service.connector_command,
                    timeout=self.config.service.connector_timeout_seconds,
                    model=self.config.service.connector_model,
                    reasoning_effort=self.config.service.connector_reasoning_effort,
                )
            elif backend == "claude_cli":
                connector = ClaudeCliConnector(
                    workspace=repo.healer_repo_path,
                    claude_command=self.config.service.claude_cli_command,
                    timeout=self.config.service.connector_timeout_seconds,
                    model=self.config.service.claude_cli_model,
                    dangerously_skip_permissions=self.config.service.claude_cli_dangerously_skip_permissions,
                )
            elif backend == "cline":
                connector = ClineConnector(
                    workspace=repo.healer_repo_path,
                    cline_command=self.config.service.cline_command,
                    timeout=self.config.service.connector_timeout_seconds,
                    model=self.config.service.cline_model,
                    use_json=self.config.service.cline_use_json,
                    act_mode=self.config.service.cline_act_mode,
                )
            elif backend == "kilo_cli":
                connector = KiloCliConnector(
                    workspace=repo.healer_repo_path,
                    kilo_cli_command=self.config.service.kilo_cli_command,
                    timeout=self.config.service.connector_timeout_seconds,
                    model=self.config.service.kilo_cli_model,
                )
            else:
                connector = CodexCliConnector(
                    workspace=repo.healer_repo_path,
                    codex_command=self.config.service.connector_command,
                    timeout=self.config.service.connector_timeout_seconds,
                    model=self.config.service.connector_model,
                    reasoning_effort=self.config.service.connector_reasoning_effort,
                )
            connector_cache[backend] = connector
            return connector

        routing_mode = self.config.service.connector_routing_mode
        if routing_mode == "exec_for_code":
            code_backend = self.config.service.code_connector_backend
            non_code_backend = self.config.service.non_code_connector_backend
            connectors_by_backend: dict[str, ConnectorProtocol] = {}
            for backend in {code_backend, non_code_backend}:
                connectors_by_backend[backend] = _build_connector(backend)
            fallback_exec_connector = connectors_by_backend.get("exec") or _build_connector("exec")
            for backend, backend_connector in list(connectors_by_backend.items()):
                if backend in {"exec", "app_server"}:
                    continue
                connectors_by_backend[backend] = FailoverConnector(
                    primary_backend=backend,
                    primary=backend_connector,
                    fallback_backend="exec",
                    fallback=fallback_exec_connector,
                )
            connector = connectors_by_backend[code_backend]
        else:
            code_backend = self.config.service.connector_backend
            non_code_backend = self.config.service.connector_backend
            connector = _build_connector(self.config.service.connector_backend)
            if self.config.service.connector_backend not in {"exec", "app_server"}:
                connector = FailoverConnector(
                    primary_backend=self.config.service.connector_backend,
                    primary=connector,
                    fallback_backend="exec",
                    fallback=_build_connector("exec"),
                )
            connectors_by_backend = {self.config.service.connector_backend: connector}

        loop = AutonomousHealerLoop(
            settings=repo,
            store=store,
            connector=connector,
            tracker=tracker,
            connectors_by_backend=connectors_by_backend,
            connector_routing_mode=routing_mode,
            code_connector_backend=code_backend,
            non_code_connector_backend=non_code_backend,
        )
        if repo.healer_repo_slug and not loop.tracker.repo_slug:
            loop.tracker.repo_slug = repo.healer_repo_slug
        return RepoRuntime(
            settings=repo,
            store=store,
            loop=loop,
            tracker=loop.tracker,
            connector=connector,
            connectors_by_backend=connectors_by_backend,
        )

    def start(self, repo_name: str | None = None, *, once: bool = False) -> None:
        repos = self.config.select_repos(repo_name)
        if once:
            for repo in repos:
                runtime = self.build_runtime(repo)
                try:
                    runtime.loop._tick_once()
                finally:
                    self._close_runtime(runtime)
                self._invalidate_status_cache(repo.repo_name)
            return

        async def _run() -> None:
            runtimes = [self.build_runtime(repo) for repo in repos]
            stop = False
            try:
                await asyncio.gather(*(runtime.loop.run_forever(lambda: stop) for runtime in runtimes))
            finally:
                stop = True
                for runtime in runtimes:
                    self._close_runtime(runtime)
                self._invalidate_status_cache(repo_name)

        asyncio.run(_run())

    def status_rows(
        self,
        repo_name: str | None = None,
        *,
        force_refresh: bool = False,
        probe_connector: bool = False,
    ) -> list[dict[str, object]]:
        cache_key = (repo_name or "").strip() or "*"
        ttl_seconds = self._status_cache_ttl_seconds(repo_name)
        token_present = bool(os.getenv(self.config.service.github_token_env, "").strip())
        if not force_refresh and ttl_seconds > 0:
            with self._status_cache_lock:
                cached = self._status_cache.get(cache_key)
                if cached is not None and (time.monotonic() - cached.generated_at) <= ttl_seconds:
                    return [dict(row) for row in cached.rows]
        rows: list[dict[str, object]] = []
        for repo in self.config.select_repos(repo_name):
            runtime = self.build_runtime(repo)
            try:
                repo_path = Path(repo.healer_repo_path).expanduser().resolve()
                connector_health = self._connector_health_payload(runtime, probe_connector=probe_connector)
                connector_health_by_backend = self._connector_health_payload_by_backend(
                    runtime,
                    probe_connector=probe_connector,
                )
                if probe_connector:
                    runtime.loop._record_connector_health(connector_health)
                issues = runtime.store.list_healer_issues(limit=500)
                issues_by_id = {str(issue.get("issue_id") or ""): issue for issue in issues}
                breaker = runtime.loop._circuit_breaker_status()
                counts: dict[str, int] = {}
                for issue in issues:
                    state = str(issue.get("state") or "unknown")
                    counts[state] = counts.get(state, 0) + 1
                recent_attempts = runtime.store.list_recent_healer_attempts(limit=5)
                annotated_attempts: list[dict[str, object]] = []
                for attempt in recent_attempts:
                    attempt_row = dict(attempt)
                    issue = issues_by_id.get(str(attempt.get("issue_id") or ""))
                    route = classify_issue_route(issue, attempt)
                    test_summary = attempt.get("test_summary") or {}
                    if isinstance(test_summary, dict):
                        attempt_row["validation_lane"] = str(test_summary.get("validation_lane") or "")
                        attempt_row["promotion_state"] = str(test_summary.get("promotion_state") or "")
                        attempt_row["phase_states"] = dict(test_summary.get("phase_states") or {})
                    attempt_row["diagnosis"] = route.diagnosis
                    attempt_row["failure_family"] = route.failure_family
                    attempt_row["recommended_skill"] = route.recommended_skill
                    attempt_row["default_action"] = route.default_action
                    attempt_row["graph_position"] = route.graph_position
                    attempt_row["previous_skill"] = route.previous_skill
                    attempt_row["next_skill"] = route.next_skill
                    attempt_row["skill_relative_path"] = route.skill_relative_path
                    attempt_row["default_command_preview"] = route.default_command_preview
                    attempt_row["key_output_fields"] = list(route.key_output_fields)
                    attempt_row["stop_conditions"] = list(route.stop_conditions)
                    attempt_row["stop_recommended"] = route.stop_recommended
                    attempt_row["stop_reason"] = route.stop_reason
                    attempt_row["connector_debug_focus"] = route.connector_debug_focus
                    attempt_row["connector_debug_checks"] = list(route.connector_debug_checks)
                    annotated_attempts.append(attempt_row)
                preflight_reports = list_cached_preflight_reports(
                    store=runtime.store,
                    gate_mode=repo.healer_test_gate_mode,
                )
                git_ok = _check_command(["git", "-C", str(repo_path), "rev-parse", "--is-inside-work-tree"])
                branch_ok = _check_command(["git", "-C", str(repo_path), "rev-parse", "--verify", repo.healer_default_branch])
                preflight_summary = summarize_preflight_readiness(preflight_reports)
                preflight_report_rows = []
                for report in preflight_reports:
                    readiness = preflight_readiness_assessment(report)
                    preflight_report_rows.append(
                        {
                            "language": report.language,
                            "execution_root": report.execution_root,
                            "status": report.status,
                            "failure_class": report.failure_class,
                            "summary": report.summary,
                            "checked_at": report.checked_at,
                            "readiness_score": readiness["score"],
                            "readiness_class": readiness["class"],
                            "blocking": readiness["blocking"],
                            "recommendation": readiness["recommendation"],
                            "blockers": list(readiness["blockers"]),
                        }
                    )
                failure_domain_metrics = _failure_domain_metrics(runtime.store)
                retry_playbook_metrics = _retry_playbook_metrics(runtime.store)
                reliability_canary = _reliability_canary_metrics(runtime.store)
                policy = _build_policy_payload(
                    store=runtime.store,
                    paused=runtime.store.get_state("healer_paused") == "true",
                    circuit_breaker_open=breaker.open,
                    trust_state="",
                    trust_recommended_operator_action="",
                    failure_domain_metrics=failure_domain_metrics,
                    retry_playbook_metrics=retry_playbook_metrics,
                    reliability_canary=reliability_canary,
                )
                trust = _build_trust_payload(
                    store=runtime.store,
                    paused=runtime.store.get_state("healer_paused") == "true",
                    circuit_breaker_open=breaker.open,
                    circuit_breaker_cooldown_remaining_seconds=breaker.cooldown_remaining_seconds,
                    preflight_summary=preflight_summary,
                    state_counts=counts,
                    connector_available=bool(connector_health.get("available")),
                    tracker_available=runtime.store.get_state("healer_tracker_available") != "false",
                    dominant_failure_domain=_dominant_failure_domain(
                        retry_playbook_metrics=retry_playbook_metrics,
                        failure_domain_metrics=failure_domain_metrics,
                    ),
                    repo_path_exists=repo_path.exists(),
                    git_repo_ok=git_ok,
                    default_branch_ok=branch_ok,
                    github_token_present=token_present,
                    policy=policy,
                )
                policy = _build_policy_payload(
                    store=runtime.store,
                    paused=runtime.store.get_state("healer_paused") == "true",
                    circuit_breaker_open=breaker.open,
                    trust_state=str(trust.get("state") or ""),
                    trust_recommended_operator_action=str(trust.get("recommended_operator_action") or ""),
                    failure_domain_metrics=failure_domain_metrics,
                    retry_playbook_metrics=retry_playbook_metrics,
                    reliability_canary=reliability_canary,
                )
                trust["policy_outcome"] = str(policy.get("outcome") or "")
                trust["policy_recommendation"] = str(policy.get("recommendation") or "")
                rows.append(
                    {
                        "repo": repo.repo_name,
                        "path": repo.healer_repo_path,
                        "paused": runtime.store.get_state("healer_paused") == "true",
                        "issues_total": len(issues),
                        "state_counts": counts,
                        "circuit_breaker": {
                            "open": breaker.open,
                            "attempts_considered": breaker.attempts_considered,
                            "failures": breaker.failures,
                            "failure_rate": breaker.failure_rate,
                            "threshold": breaker.threshold,
                            "cooldown_remaining_seconds": breaker.cooldown_remaining_seconds,
                            "last_failure_at": breaker.last_failure_at,
                        },
                        "connector": {
                            "backend": self.config.service.connector_backend,
                            "routing_mode": runtime.loop.connector_routing_mode,
                            "code_backend": runtime.loop.code_connector_backend,
                            "non_code_backend": runtime.loop.non_code_connector_backend,
                            "available": connector_health.get("available"),
                            "configured_command": connector_health.get("configured_command"),
                            "resolved_command": connector_health.get("resolved_command"),
                            "availability_reason": connector_health.get("availability_reason"),
                            "last_health_error": connector_health.get("last_health_error"),
                            "last_runtime_error_kind": connector_health.get("last_runtime_error_kind"),
                            "last_runtime_stdout_tail": connector_health.get("last_runtime_stdout_tail"),
                            "last_runtime_stderr_tail": connector_health.get("last_runtime_stderr_tail"),
                            "fallback_backend": connector_health.get("fallback_backend"),
                            "fallback_available": connector_health.get("fallback_available"),
                            "fallback_attempts": connector_health.get("fallback_attempts"),
                            "fallback_successes": connector_health.get("fallback_successes"),
                            "last_fallback_reason": connector_health.get("last_fallback_reason"),
                            "last_checked_at": runtime.store.get_state("healer_connector_last_checked_at") or "",
                            "last_error_class": runtime.store.get_state("healer_connector_last_error_class") or "",
                            "last_error_reason": runtime.store.get_state("healer_connector_last_error_reason") or "",
                            "last_error_at": runtime.store.get_state("healer_connector_last_error_at") or "",
                            "last_failure_fingerprint": runtime.store.get_state("healer_last_failure_fingerprint") or "",
                            "last_failure_fingerprint_issue_id": runtime.store.get_state("healer_last_failure_fingerprint_issue_id") or "",
                            "last_failure_fingerprint_class": runtime.store.get_state("healer_last_failure_fingerprint_class") or "",
                            "last_contamination_paths": runtime.store.get_state("healer_last_contamination_paths") or "",
                            "backends": connector_health_by_backend,
                        },
                        "tracker": {
                            "available": runtime.store.get_state("healer_tracker_available") != "false",
                            "last_error_class": runtime.store.get_state("healer_tracker_last_error_class") or "",
                            "last_error_reason": runtime.store.get_state("healer_tracker_last_error_reason") or "",
                            "last_error_at": runtime.store.get_state("healer_tracker_last_error_at") or "",
                            "request_metrics": (
                                runtime.tracker.request_metrics_snapshot()
                                if hasattr(runtime.tracker, "request_metrics_snapshot")
                                else {"counts": {}}
                            ),
                        },
                        "worker": _worker_runtime_state(runtime.store),
                        "resource_audit": HealerReconciler(
                            store=runtime.store,
                            workspace_manager=runtime.loop.workspace_manager,
                        ).resource_audit(),
                        "preflight": {
                            "gate_mode": repo.healer_test_gate_mode,
                            "summary": preflight_summary,
                            "reports": preflight_report_rows,
                        },
                        "trust": trust,
                        "policy": policy,
                        "issue_explanations": _build_issue_explanations(issues=issues, trust=trust),
                        "app_server_metrics": _app_server_metrics(runtime.store),
                        "codex_native_multi_agent_metrics": _codex_native_multi_agent_metrics(runtime.store),
                        "swarm_metrics": _swarm_metrics(runtime.store),
                        "failure_domain_metrics": failure_domain_metrics,
                        "retry_playbook_metrics": retry_playbook_metrics,
                        "reliability_canary": reliability_canary,
                        "reliability_daily_rollups": _reliability_daily_rollups(runtime.store),
                        "reliability_trends": _reliability_trend_metrics(runtime.store),
                        "issue_outcomes": _issue_outcome_metrics(issues),
                        "recent_attempts": annotated_attempts,
                    }
                )
            finally:
                self._close_runtime(runtime)
        with self._status_cache_lock:
            self._status_cache[cache_key] = StatusSnapshot(
                rows=[dict(row) for row in rows],
                generated_at=time.monotonic(),
            )
        return rows

    def set_paused(self, paused: bool, repo_name: str | None = None) -> None:
        for repo in self.config.select_repos(repo_name):
            runtime = self.build_runtime(repo)
            try:
                runtime.store.set_state("healer_paused", "true" if paused else "false")
            finally:
                self._close_runtime(runtime)
        self._invalidate_status_cache(repo_name)

    def run_scan(self, repo_name: str | None = None, *, dry_run: bool) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for repo in self.config.select_repos(repo_name):
            runtime = self.build_runtime(repo)
            try:
                scanner = FlowHealerScanner(
                    repo_path=Path(repo.healer_repo_path),
                    store=runtime.store,
                    tracker=runtime.tracker,
                    severity_threshold=repo.healer_scan_severity_threshold,
                    max_issues_per_run=repo.healer_scan_max_issues_per_run,
                    default_labels=repo.healer_scan_default_labels,
                    enable_issue_creation=repo.healer_scan_enable_issue_creation,
                )
                results.append({"repo": repo.repo_name, "summary": scanner.run_scan(dry_run=dry_run)})
            finally:
                self._close_runtime(runtime)
        self._invalidate_status_cache(repo_name)
        return results

    def request_helper_recycle(self, repo_name: str | None = None, *, idle_only: bool) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for repo in self.config.select_repos(repo_name):
            runtime = self.build_runtime(repo)
            try:
                active_rows = runtime.store.list_healer_issues(
                    states=["claimed", "running", "verify_pending"],
                    limit=max(1, int(repo.healer_max_concurrent_issues)),
                )
                runtime.store.set_state("healer_helper_recycle_requested_at", _utc_now_string())
                runtime.store.set_state("healer_helper_recycle_idle_only", "true" if idle_only else "false")
                runtime.store.set_state("healer_helper_recycle_status", "requested")
                runtime.store.set_state(
                    "healer_helper_recycle_reason",
                    "Queued via CLI maintenance command.",
                )
                rows.append(
                    {
                        "repo": repo.repo_name,
                        "requested": True,
                        "idle_only": idle_only,
                        "active_issue_count": len(active_rows),
                        "status": "requested",
                        "note": (
                            "The live daemon will recycle helper processes on its next tick when idle."
                            if idle_only
                            else "The live daemon will recycle helper processes on its next tick."
                        ),
                    }
                )
            finally:
                self._close_runtime(runtime)
        self._invalidate_status_cache(repo_name)
        return rows

    def cached_status_rows(
        self,
        repo_name: str | None = None,
        *,
        force_refresh: bool = False,
        probe_connector: bool = False,
    ) -> list[dict[str, object]]:
        return self.status_rows(
            repo_name,
            force_refresh=force_refresh,
            probe_connector=probe_connector,
        )

    def _invalidate_status_cache(self, repo_name: str | None = None) -> None:
        with self._status_cache_lock:
            if repo_name is None:
                self._status_cache.clear()
                return
            wanted = repo_name.strip()
            self._status_cache.pop(wanted, None)
            self._status_cache.pop("*", None)

    def _status_cache_ttl_seconds(self, repo_name: str | None = None) -> float:
        repos = self.config.select_repos(repo_name)
        if not repos:
            return 0.0
        return float(max(0, min(int(repo.healer_status_cache_ttl_seconds) for repo in repos)))

    def _connector_health_payload(
        self,
        runtime: RepoRuntime,
        *,
        probe_connector: bool,
        connector: ConnectorProtocol | None = None,
        backend_name: str = "",
    ) -> dict[str, str | bool]:
        if probe_connector:
            return runtime.loop._connector_health_snapshot(connector=connector)
        store = runtime.store
        available_raw = str(store.get_state("healer_connector_available") or "").strip().lower()
        available = True if not available_raw else available_raw == "true"
        configured_command = str(store.get_state("healer_connector_configured_command") or "").strip()
        resolved_command = str(store.get_state("healer_connector_resolved_command") or "").strip()
        availability_reason = str(store.get_state("healer_connector_availability_reason") or "").strip()
        payload = {
            "available": available,
            "configured_command": configured_command,
            "resolved_command": resolved_command,
            "availability_reason": availability_reason,
            "last_health_error": str(store.get_state("healer_connector_last_error_reason") or "").strip(),
            "fallback_backend": str(store.get_state("healer_connector_fallback_backend") or "").strip(),
            "fallback_available": str(store.get_state("healer_connector_fallback_available") or "").strip().lower()
            == "true",
            "fallback_attempts": str(store.get_state("healer_connector_fallback_attempts") or "").strip(),
            "fallback_successes": str(store.get_state("healer_connector_fallback_successes") or "").strip(),
            "last_fallback_reason": str(store.get_state("healer_connector_last_fallback_reason") or "").strip(),
        }
        if backend_name and not configured_command:
            payload["configured_command"] = str(runtime.connectors_by_backend.get(backend_name).__class__.__name__)
        return payload

    def _connector_health_payload_by_backend(
        self,
        runtime: RepoRuntime,
        *,
        probe_connector: bool,
    ) -> dict[str, dict[str, str | bool]]:
        if probe_connector:
            return runtime.loop._connector_health_by_backend()
        return {
            backend: self._connector_health_payload(
                runtime,
                probe_connector=False,
                connector=backend_connector,
                backend_name=backend,
            )
            for backend, backend_connector in runtime.connectors_by_backend.items()
        }

    def doctor_rows(self, repo_name: str | None = None, *, preflight: bool = False) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        token_name = self.config.service.github_token_env
        token_present = bool(os.getenv(token_name, "").strip())
        docker_present = shutil.which("docker") is not None
        launchd_path = _launch_agent_path("local.flow-healer")
        launchd_path_connector = _resolve_command_in_path(self.config.service.connector_command, launchd_path)
        skill_contracts = audit_skill_contracts()
        for repo in self.config.select_repos(repo_name):
            repo_path = Path(repo.healer_repo_path).expanduser().resolve()
            runtime = self.build_runtime(repo)
            try:
                reports = (
                    runtime.loop.preflight.refresh_all(force=True)
                    if preflight
                    else list_cached_preflight_reports(store=runtime.store, gate_mode=repo.healer_test_gate_mode)
                )
                connector_health = runtime.loop._connector_health_snapshot()
                connector_health_by_backend = runtime.loop._connector_health_by_backend()
                runtime.loop._record_connector_health(connector_health)
                breaker = runtime.loop._circuit_breaker_status()
                issues = runtime.store.list_healer_issues(limit=500)
                counts: dict[str, int] = {}
                for issue in issues:
                    state = str(issue.get("state") or "unknown")
                    counts[state] = counts.get(state, 0) + 1
                preflight_summary = summarize_preflight_readiness(reports)
                failure_domain_metrics = _failure_domain_metrics(runtime.store)
                retry_playbook_metrics = _retry_playbook_metrics(runtime.store)
                reliability_canary = _reliability_canary_metrics(runtime.store)
                policy = _build_policy_payload(
                    store=runtime.store,
                    paused=runtime.store.get_state("healer_paused") == "true",
                    circuit_breaker_open=breaker.open,
                    trust_state="",
                    trust_recommended_operator_action="",
                    failure_domain_metrics=failure_domain_metrics,
                    retry_playbook_metrics=retry_playbook_metrics,
                    reliability_canary=reliability_canary,
                )
                git_ok = _check_command(["git", "-C", str(repo_path), "rev-parse", "--is-inside-work-tree"])
                branch_ok = _check_command(["git", "-C", str(repo_path), "rev-parse", "--verify", repo.healer_default_branch])
                trust = _build_trust_payload(
                    store=runtime.store,
                    paused=runtime.store.get_state("healer_paused") == "true",
                    circuit_breaker_open=breaker.open,
                    circuit_breaker_cooldown_remaining_seconds=breaker.cooldown_remaining_seconds,
                    preflight_summary=preflight_summary,
                    state_counts=counts,
                    connector_available=bool(connector_health.get("available")),
                    tracker_available=runtime.store.get_state("healer_tracker_available") != "false",
                    dominant_failure_domain=_dominant_failure_domain(
                        retry_playbook_metrics=retry_playbook_metrics,
                        failure_domain_metrics=failure_domain_metrics,
                    ),
                    repo_path_exists=repo_path.exists(),
                    git_repo_ok=git_ok,
                    default_branch_ok=branch_ok,
                    github_token_present=token_present,
                    policy=policy,
                )
                policy = _build_policy_payload(
                    store=runtime.store,
                    paused=runtime.store.get_state("healer_paused") == "true",
                    circuit_breaker_open=breaker.open,
                    trust_state=str(trust.get("state") or ""),
                    trust_recommended_operator_action=str(trust.get("recommended_operator_action") or ""),
                    failure_domain_metrics=failure_domain_metrics,
                    retry_playbook_metrics=retry_playbook_metrics,
                    reliability_canary=reliability_canary,
                )
                trust["policy_outcome"] = str(policy.get("outcome") or "")
                trust["policy_recommendation"] = str(policy.get("recommendation") or "")
                rows.append(
                    {
                        "repo": repo.repo_name,
                        "repo_path": str(repo_path),
                        "path_exists": repo_path.exists(),
                        "git_repo": git_ok,
                        "default_branch_ok": branch_ok,
                        "docker": docker_present,
                        "codex": bool(connector_health.get("available")),
                        "connector_backend": self.config.service.connector_backend,
                        "connector_routing_mode": runtime.loop.connector_routing_mode,
                        "code_connector_backend": runtime.loop.code_connector_backend,
                        "non_code_connector_backend": runtime.loop.non_code_connector_backend,
                        "connector_command": self.config.service.connector_command,
                        "connector_resolved_command": connector_health.get("resolved_command"),
                        "connector_availability_reason": connector_health.get("availability_reason"),
                        "connector_last_health_error": connector_health.get("last_health_error"),
                        "connector_last_runtime_error_kind": connector_health.get("last_runtime_error_kind"),
                        "connector_last_runtime_stdout_tail": connector_health.get("last_runtime_stdout_tail"),
                        "connector_last_runtime_stderr_tail": connector_health.get("last_runtime_stderr_tail"),
                        "connector_fallback_backend": connector_health.get("fallback_backend"),
                        "connector_fallback_available": connector_health.get("fallback_available"),
                        "connector_fallback_attempts": connector_health.get("fallback_attempts"),
                        "connector_fallback_successes": connector_health.get("fallback_successes"),
                        "connector_last_fallback_reason": connector_health.get("last_fallback_reason"),
                        "connector_backends": connector_health_by_backend,
                        "last_failure_fingerprint": runtime.store.get_state("healer_last_failure_fingerprint") or "",
                        "last_failure_fingerprint_issue_id": runtime.store.get_state("healer_last_failure_fingerprint_issue_id") or "",
                        "last_failure_fingerprint_class": runtime.store.get_state("healer_last_failure_fingerprint_class") or "",
                        "last_contamination_paths": runtime.store.get_state("healer_last_contamination_paths") or "",
                        "launchd_path": launchd_path,
                        "launchd_path_has_connector": bool(launchd_path_connector),
                        "launchd_path_connector": launchd_path_connector or "",
                        "github_token_env": token_name,
                        "github_token_present": token_present,
                        "tracker_available": runtime.store.get_state("healer_tracker_available") != "false",
                        "tracker_last_error_class": runtime.store.get_state("healer_tracker_last_error_class") or "",
                        "tracker_last_error_reason": runtime.store.get_state("healer_tracker_last_error_reason") or "",
                        "tracker_last_error_at": runtime.store.get_state("healer_tracker_last_error_at") or "",
                        "worker": _worker_runtime_state(runtime.store),
                        "preflight_gate_mode": repo.healer_test_gate_mode,
                        "trust": trust,
                        "policy": policy,
                        "preflight_reports": [
                            {
                                "language": report.language,
                                "execution_root": report.execution_root,
                                "status": report.status,
                                "failure_class": report.failure_class,
                                "summary": report.summary,
                                "checked_at": report.checked_at,
                            }
                            for report in reports
                        ],
                        "skill_contracts_ok": skill_contracts["contracts_ok"],
                        "skill_contracts": skill_contracts,
                        "circuit_breaker_open": breaker.open,
                        "circuit_breaker_cooldown_remaining_seconds": breaker.cooldown_remaining_seconds,
                    }
                )
            finally:
                self._close_runtime(runtime)
        return rows

    def control_command_rows(self, repo_name: str | None = None, *, limit: int = 100) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for repo in self.config.select_repos(repo_name):
            store = SQLiteStore(self.config.repo_db_path(repo.repo_name))
            store.bootstrap()
            for entry in store.list_control_commands(limit=limit):
                row = dict(entry)
                row.setdefault("repo_name", repo.repo_name)
                rows.append(row)
            store.close()
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        if len(rows) > limit:
            rows = rows[:limit]
        return rows

    def healer_event_rows(self, repo_name: str | None = None, *, limit: int = 100) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for repo in self.config.select_repos(repo_name):
            store = SQLiteStore(self.config.repo_db_path(repo.repo_name))
            store.bootstrap()
            for entry in store.list_healer_events(limit=limit):
                row = dict(entry)
                row.setdefault("repo_name", repo.repo_name)
                rows.append(row)
            store.close()
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        if len(rows) > limit:
            rows = rows[:limit]
        return rows

    @staticmethod
    def _close_runtime(runtime: RepoRuntime) -> None:
        closed: set[int] = set()
        for connector in runtime.connectors_by_backend.values():
            if id(connector) in closed:
                continue
            try:
                connector.shutdown()  # type: ignore[call-arg]
            except Exception:
                pass
            closed.add(id(connector))
        runtime.store.close()


def _check_command(cmd: list[str]) -> bool:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=15)
    return proc.returncode == 0


def _utc_now_string() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _safe_state_int(store: SQLiteStore, key: str) -> int:
    raw = str(store.get_state(key) or "").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _app_server_metrics(store: SQLiteStore) -> dict[str, object]:
    attempts = _safe_state_int(store, "app_server_attempts")
    with_material_diff = _safe_state_int(store, "app_server_attempts_with_material_diff")
    with_zero_diff = _safe_state_int(store, "app_server_attempts_with_zero_diff")
    forced_recovery_attempts = _safe_state_int(store, "app_server_forced_serialized_recovery_attempts")
    forced_recovery_success = _safe_state_int(store, "app_server_forced_serialized_recovery_success")
    exec_failover_attempts = _safe_state_int(store, "app_server_exec_failover_attempts")
    exec_failover_success = _safe_state_int(store, "app_server_exec_failover_success")
    task_kinds = ("fix", "build", "docs", "research", "unknown")
    zero_diff_rate_by_task_kind: dict[str, float] = {}
    for task_kind in task_kinds:
        total = _safe_state_int(store, f"app_server_attempts_task_kind_{task_kind}")
        if total <= 0:
            continue
        zero = _safe_state_int(store, f"app_server_attempts_with_zero_diff_task_kind_{task_kind}")
        zero_diff_rate_by_task_kind[task_kind] = round(float(zero) / float(total), 4)
    return {
        "app_server_attempts": attempts,
        "app_server_attempts_with_material_diff": with_material_diff,
        "app_server_attempts_with_zero_diff": with_zero_diff,
        "app_server_forced_serialized_recovery_attempts": forced_recovery_attempts,
        "app_server_forced_serialized_recovery_success": forced_recovery_success,
        "app_server_exec_failover_attempts": exec_failover_attempts,
        "app_server_exec_failover_success": exec_failover_success,
        "zero_diff_rate_by_task_kind": zero_diff_rate_by_task_kind,
    }


def _swarm_metrics(store: SQLiteStore) -> dict[str, object]:
    strategies = ("repair", "retry_prompt_only", "quarantine", "infra_pause")
    strategy_counts = {
        strategy: _safe_state_int(store, f"healer_swarm_strategy_{strategy}")
        for strategy in strategies
    }
    skipped_domains = ("infra", "contract", "unknown")
    skipped_by_domain = {
        domain: _safe_state_int(store, f"healer_swarm_skipped_domain_{domain}")
        for domain in skipped_domains
    }
    return {
        "runs": _safe_state_int(store, "healer_swarm_runs"),
        "recovered": _safe_state_int(store, "healer_swarm_recovered"),
        "unrecovered": _safe_state_int(store, "healer_swarm_unrecovered"),
        "backend_exec": _safe_state_int(store, "healer_swarm_runs_backend_exec"),
        "backend_app_server": _safe_state_int(store, "healer_swarm_runs_backend_app_server"),
        "strategy_counts": strategy_counts,
        "skipped_domain": _safe_state_int(store, "healer_swarm_skipped_domain"),
        "skipped_by_domain": skipped_by_domain,
    }


def _codex_native_multi_agent_metrics(store: SQLiteStore) -> dict[str, int]:
    return {
        "attempts": _safe_state_int(store, "healer_codex_native_multi_agent_attempts"),
        "success": _safe_state_int(store, "healer_codex_native_multi_agent_success"),
        "recovery_attempts": _safe_state_int(store, "healer_codex_native_multi_agent_recovery_attempts"),
        "recovery_success": _safe_state_int(store, "healer_codex_native_multi_agent_recovery_success"),
        "fallback_to_swarm": _safe_state_int(store, "healer_codex_native_multi_agent_fallback_to_swarm"),
        "skipped_backend": _safe_state_int(store, "healer_codex_native_multi_agent_skipped_backend"),
        "skipped_task_kind": _safe_state_int(store, "healer_codex_native_multi_agent_skipped_task_kind"),
    }


def _issue_outcome_metrics(
    issues: list[dict[str, object]],
    *,
    recent_limit: int = 50,
) -> dict[str, object]:
    success_states = {"pr_open", "pr_pending_approval", "resolved"}
    failure_states = {"failed", "blocked"}
    success_count = 0
    failure_count = 0
    active_count = 0
    terminal_outcomes: list[dict[str, object]] = []
    daily_counts: dict[str, dict[str, int]] = {}

    for issue in issues:
        state = str(issue.get("state") or "").strip().lower()
        updated_at = str(issue.get("updated_at") or "").strip()
        issue_id = str(issue.get("issue_id") or "").strip()
        title = str(issue.get("title") or "").strip()
        if state in success_states:
            outcome = "success"
            success_count += 1
        elif state in failure_states:
            outcome = "failure"
            failure_count += 1
        else:
            active_count += 1
            continue

        terminal_outcomes.append(
            {
                "issue_id": issue_id,
                "title": title,
                "state": state,
                "updated_at": updated_at,
                "outcome": outcome,
            }
        )
        day = updated_at[:10] if len(updated_at) >= 10 else ""
        if day:
            bucket = daily_counts.setdefault(day, {"success": 0, "failure": 0})
            bucket[outcome] += 1

    terminal_outcomes.sort(
        key=lambda item: (str(item.get("updated_at") or ""), str(item.get("issue_id") or "")),
        reverse=True,
    )

    current_success_streak = 0
    for item in terminal_outcomes:
        if str(item.get("outcome") or "") != "success":
            break
        current_success_streak += 1

    daily_outcomes = [
        {
            "day": day,
            "success": counts["success"],
            "failure": counts["failure"],
            "total": counts["success"] + counts["failure"],
        }
        for day, counts in sorted(daily_counts.items())
    ]
    return {
        "success": success_count,
        "failure": failure_count,
        "active": active_count,
        "terminal_total": success_count + failure_count,
        "current_success_streak": current_success_streak,
        "recent_terminal_outcomes": terminal_outcomes[:max(1, int(recent_limit))],
        "daily_terminal_outcomes": daily_outcomes,
    }


def _failure_domain_metrics(store: SQLiteStore) -> dict[str, int]:
    domains = ("infra", "contract", "code", "unknown")
    return {
        "total": _safe_state_int(store, "healer_failure_domain_total"),
        **{
            domain: _safe_state_int(store, f"healer_failure_domain_{domain}")
            for domain in domains
        },
    }


def _retry_playbook_metrics(store: SQLiteStore) -> dict[str, object]:
    class_prefix = "healer_retry_playbook_class_"
    domain_prefix = "healer_retry_playbook_domain_"
    strategy_prefix = "healer_retry_playbook_strategy_"
    class_counts = _counter_state_map(store=store, prefix=class_prefix)
    domain_counts = _counter_state_map(store=store, prefix=domain_prefix)
    strategy_counts = _counter_state_map(store=store, prefix=strategy_prefix)
    total = _safe_state_int(store, "healer_retry_playbook_total")
    top_failure_classes = [
        {"failure_class": name, "count": count}
        for name, count in sorted(class_counts.items(), key=lambda item: (-item[1], item[0]))[:3]
    ]
    dominant_domain = ""
    dominant_domain_count = 0
    if domain_counts:
        dominant_domain, dominant_domain_count = max(
            domain_counts.items(),
            key=lambda item: (item[1], item[0]),
        )
    recommendation = _retry_playbook_recommendation(
        dominant_domain=dominant_domain,
        dominant_domain_count=dominant_domain_count,
        total=total,
    )
    return {
        "total": total,
        "class_counts": class_counts,
        "domain_counts": domain_counts,
        "strategy_counts": strategy_counts,
        "top_failure_classes": top_failure_classes,
        "dominant_domain": dominant_domain,
        "dominant_domain_count": dominant_domain_count,
        "dominant_domain_share": round(float(dominant_domain_count) / float(max(1, total)), 4),
        "recommendation": recommendation,
        "last_selection": {
            "issue_id": store.get_state("healer_retry_playbook_last_issue_id") or "",
            "failure_class": store.get_state("healer_retry_playbook_last_failure_class") or "",
            "failure_domain": store.get_state("healer_retry_playbook_last_failure_domain") or "",
            "strategy": store.get_state("healer_retry_playbook_last_strategy") or "",
            "backoff_seconds": _safe_state_int(store, "healer_retry_playbook_last_backoff_seconds"),
            "feedback_hint": store.get_state("healer_retry_playbook_last_feedback_hint") or "",
            "selected_at": store.get_state("healer_retry_playbook_last_selected_at") or "",
        },
    }


def _counter_state_map(*, store: SQLiteStore, prefix: str) -> dict[str, int]:
    values = store.list_states(prefix=prefix, limit=500)
    mapped: dict[str, int] = {}
    for key, raw in values.items():
        if not key.startswith(prefix):
            continue
        token = key[len(prefix):]
        if not token:
            continue
        try:
            count = max(0, int(str(raw).strip()))
        except ValueError:
            continue
        mapped[token] = count
    return mapped


def _retry_playbook_recommendation(*, dominant_domain: str, dominant_domain_count: int, total: int) -> str:
    share = float(dominant_domain_count) / float(max(1, total))
    if not dominant_domain or total <= 0:
        return "No retry playbook samples yet."
    if dominant_domain == "contract" and share >= 0.45:
        return "Contract failures dominate; tighten issue output/validation contracts and diff formatting guidance."
    if dominant_domain == "infra" and share >= 0.45:
        return "Infrastructure failures dominate; prioritize preflight and runtime/toolchain stabilization before retries."
    if dominant_domain == "code" and share >= 0.45:
        return "Code failures dominate; focus retries on failing tests and narrower code-scope edits."
    if dominant_domain == "unknown" and share >= 0.35:
        return "Unknown-domain failures are high; increase structured failure details to improve retry routing."
    return "Failure domains are mixed; continue collecting samples before tuning retry multipliers."


def _worker_runtime_state(store: SQLiteStore) -> dict[str, object]:
    runtime = store.get_runtime_status() or {}
    return {
        "active_worker_id": store.get_state("healer_active_worker_id") or "",
        "last_heartbeat_at": store.get_state("healer_active_worker_heartbeat_at") or "",
        "last_pulse_at": store.get_state("healer_last_pulse_at") or "",
        "last_reconcile_at": store.get_state("healer_last_reconcile_at") or "",
        "runtime_status": str(runtime.get("status") or ""),
        "runtime_last_error": str(runtime.get("last_error") or ""),
        "runtime_heartbeat_at": str(runtime.get("heartbeat_at") or ""),
        "last_tick_started_at": str(runtime.get("last_tick_started_at") or ""),
        "last_tick_finished_at": str(runtime.get("last_tick_finished_at") or ""),
        "recovered_stale_active_issues": _safe_state_int(store, "healer_reconcile_recovered_stale_active_issues"),
        "recovered_leases": _safe_state_int(store, "healer_reconcile_recovered_leases"),
        "interrupted_inactive_attempts": _safe_state_int(store, "healer_reconcile_interrupted_inactive_attempts"),
        "interrupted_superseded_attempts": _safe_state_int(store, "healer_reconcile_interrupted_superseded_attempts"),
    }


def _build_trust_payload(
    *,
    store: SQLiteStore,
    paused: bool,
    circuit_breaker_open: bool,
    circuit_breaker_cooldown_remaining_seconds: int,
    preflight_summary: dict[str, object],
    state_counts: dict[str, int],
    connector_available: bool,
    tracker_available: bool,
    dominant_failure_domain: str,
    repo_path_exists: bool = True,
    git_repo_ok: bool = True,
    default_branch_ok: bool = True,
    github_token_present: bool = True,
    policy: dict[str, object] | None = None,
) -> dict[str, object]:
    infra_pause = _infra_pause_snapshot(store)
    needs_clarification_count = max(0, int(state_counts.get("needs_clarification", 0)))
    failed_issue_count = max(0, int(state_counts.get("failed", 0)))
    actionable_preflight_degradation = _preflight_summary_is_actionably_degraded(preflight_summary)
    preflight_class = str(preflight_summary.get("overall_class") or "").strip().lower()
    blocking_roots = list(preflight_summary.get("blocking_execution_roots") or [])

    state = "ready"
    score = 100
    summary = "Repo is ready for autonomous issue execution."
    why_runnable = "Repo is ready for autonomous issue execution."
    why_blocked = ""
    recommended_operator_action = "continue_autonomous_healing"

    if paused:
        state = "paused"
        score = 40
        summary = "Autonomous healing is paused for this repo."
        why_runnable = ""
        why_blocked = "Autonomous healing is paused for this repo."
        recommended_operator_action = "resume_repo"
    elif circuit_breaker_open:
        state = "quarantined"
        score = 0
        summary = "Circuit breaker is open and the repo is quarantined from new healing attempts."
        why_runnable = ""
        why_blocked = (
            "Circuit breaker is open; pause new healing attempts until recent failures are understood."
        )
        recommended_operator_action = "inspect_circuit_breaker"
    elif (
        not repo_path_exists
        or not git_repo_ok
        or not default_branch_ok
        or not github_token_present
        or infra_pause["active"]
        or not connector_available
        or not tracker_available
        or preflight_class == "blocked"
    ):
        state = "needs_environment_fix"
        score = 20
        why_runnable = ""
        if not repo_path_exists:
            why_blocked = "The configured repo path does not exist, so doctor cannot verify execution readiness."
        elif not git_repo_ok:
            why_blocked = "The configured repo path is not a valid git checkout, so autonomous healing cannot run safely."
        elif not default_branch_ok:
            why_blocked = "The configured default branch is unavailable in the target repo checkout."
        elif not github_token_present:
            why_blocked = "The configured GitHub token is missing, so issue and PR operations cannot start safely."
        elif not connector_available:
            why_blocked = "The configured connector is unavailable, so autonomous healing cannot start safely."
        elif not tracker_available:
            why_blocked = "GitHub tracker access is unavailable, so issue and PR state cannot be trusted."
        elif infra_pause["active"]:
            why_blocked = str(infra_pause["reason"] or "Infrastructure pause is active for this repo.")
        elif blocking_roots:
            roots_text = ", ".join(str(root) for root in blocking_roots[:3])
            why_blocked = f"Preflight is blocked for execution roots: {roots_text}."
        else:
            why_blocked = "Preflight is blocked and the local environment needs repair."
        summary = why_blocked
        recommended_operator_action = "repair_environment"
    elif needs_clarification_count > 0:
        state = "needs_contract_fix"
        score = 45
        summary = f"{needs_clarification_count} issue(s) need clarification before safe execution."
        why_runnable = ""
        why_blocked = summary
        recommended_operator_action = "tighten_issue_contract"
    elif actionable_preflight_degradation or failed_issue_count > 0 or dominant_failure_domain:
        state = "degraded"
        score = 70
        summary = "Repo is runnable, but recent readiness or reliability signals need attention."
        why_runnable = "Healing can continue, but recent readiness or reliability signals need operator attention."
        why_blocked = ""
        recommended_operator_action = "review_reliability_signals"

    return {
        "state": state,
        "score": int(score),
        "summary": summary,
        "why_runnable": why_runnable,
        "why_blocked": why_blocked,
        "recommended_operator_action": recommended_operator_action,
        "dominant_failure_domain": dominant_failure_domain,
        "policy_outcome": str((policy or {}).get("outcome") or ""),
        "policy_recommendation": str((policy or {}).get("recommendation") or ""),
        "evidence": {
            "paused": paused,
            "circuit_breaker_open": circuit_breaker_open,
            "circuit_breaker_cooldown_remaining_seconds": int(circuit_breaker_cooldown_remaining_seconds),
            "preflight_overall_class": preflight_class,
            "preflight_blocking_execution_roots": blocking_roots,
            "repo_path_exists": repo_path_exists,
            "git_repo_ok": git_repo_ok,
            "default_branch_ok": default_branch_ok,
            "github_token_present": github_token_present,
            "connector_available": connector_available,
            "tracker_available": tracker_available,
            "infra_pause_active": bool(infra_pause["active"]),
            "infra_pause_reason": str(infra_pause["reason"]),
            "needs_clarification_count": needs_clarification_count,
            "failed_issue_count": failed_issue_count,
            "dominant_failure_domain": dominant_failure_domain,
        },
    }


def _build_policy_payload(
    *,
    store: SQLiteStore,
    paused: bool,
    circuit_breaker_open: bool,
    trust_state: str,
    trust_recommended_operator_action: str,
    failure_domain_metrics: dict[str, int],
    retry_playbook_metrics: dict[str, object],
    reliability_canary: dict[str, object],
) -> dict[str, object]:
    infra_pause = _infra_pause_snapshot(store)
    dominant_domain = str(retry_playbook_metrics.get("dominant_domain") or "").strip().lower()
    domain_total = max(
        int(failure_domain_metrics.get("total") or 0),
        int(retry_playbook_metrics.get("total") or 0),
        1,
    )
    infra_count = max(
        int(failure_domain_metrics.get("infra") or 0),
        int((retry_playbook_metrics.get("domain_counts") or {}).get("infra") or 0),
    )
    contract_count = max(
        int(failure_domain_metrics.get("contract") or 0),
        int((retry_playbook_metrics.get("domain_counts") or {}).get("contract") or 0),
    )
    no_op_rate = _safe_float(reliability_canary.get("no_op_rate"))
    wrong_root_rate = _safe_float(reliability_canary.get("wrong_root_execution_rate"))

    outcome = "retry"
    recommendation = trust_recommended_operator_action or "continue_autonomous_healing"
    reason_code = "healthy_retry_window"
    summary = "Retry budget and runtime signals still support autonomous healing."

    if paused:
        outcome = "pause"
        recommendation = "resume_repo"
        reason_code = "repo_paused"
        summary = "Repo is manually paused, so autonomous retries should stay paused."
    elif circuit_breaker_open:
        outcome = "quarantine"
        recommendation = "inspect_circuit_breaker"
        reason_code = "circuit_breaker_open"
        summary = "Recent failures opened the circuit breaker, so the repo is quarantined."
    elif infra_pause["active"]:
        outcome = "pause"
        recommendation = "repair_environment"
        reason_code = "infra_pause_active"
        summary = str(infra_pause.get("reason") or "Infrastructure pause is active for this repo.")
    elif str(trust_state or "").strip().lower() == "needs_environment_fix":
        outcome = "pause"
        recommendation = "repair_environment"
        reason_code = "environment_blocked"
        summary = "Environment blockers should be fixed before any additional retries."
    elif str(trust_state or "").strip().lower() == "needs_contract_fix":
        outcome = "require_human_fix"
        recommendation = "tighten_issue_contract"
        reason_code = "needs_contract_fix"
        summary = "Issue contracts need human clarification before autonomous retries continue."
    elif wrong_root_rate >= 0.5:
        outcome = "require_human_fix"
        recommendation = "strengthen_execution_root_hints"
        reason_code = "wrong_root_rate_high"
        summary = "Wrong-root execution is too frequent; strengthen execution-root hints before retrying."
    elif no_op_rate >= 0.5:
        outcome = "require_human_fix"
        recommendation = "tighten_issue_contract"
        reason_code = "no_op_rate_high"
        summary = "No-op attempts dominate recent runs; tighten the requested patch scope before retrying."
    elif contract_count >= 3 and (contract_count / float(domain_total)) >= 0.6:
        outcome = "require_human_fix"
        recommendation = "tighten_issue_contract"
        reason_code = "contract_failures_dominate"
        summary = "Contract failures dominate recent attempts, so a human should tighten the issue contract."
    elif infra_count >= 3 and ((infra_count / float(domain_total)) >= 0.6 or dominant_domain == "infra"):
        outcome = "throttle"
        recommendation = "stabilize_runtime"
        reason_code = "infra_failures_dominate"
        summary = "Infrastructure failures dominate recent attempts; throttle healing until runtime stability improves."

    return {
        "outcome": outcome,
        "recommendation": recommendation,
        "reason_code": reason_code,
        "summary": summary,
        "evidence": {
            "infra_pause_active": bool(infra_pause["active"]),
            "dominant_domain": dominant_domain,
            "infra_count": infra_count,
            "contract_count": contract_count,
            "domain_total": domain_total,
            "no_op_rate": round(no_op_rate, 4),
            "wrong_root_execution_rate": round(wrong_root_rate, 4),
        },
    }


def _build_issue_explanations(
    *,
    issues: list[dict[str, object]],
    trust: dict[str, object],
) -> list[dict[str, object]]:
    explanations = [_issue_explanation_for_row(issue=issue, trust=trust) for issue in issues]
    explanations.sort(
        key=lambda item: (
            0 if bool(item.get("blocking")) else 1,
            str(item.get("state") or ""),
            str(item.get("issue_id") or ""),
        )
    )
    return explanations[:25]


def _issue_explanation_for_row(
    *,
    issue: dict[str, object],
    trust: dict[str, object],
) -> dict[str, object]:
    issue_id = str(issue.get("issue_id") or "").strip()
    state = str(issue.get("state") or "unknown").strip().lower()
    last_failure_class = str(issue.get("last_failure_class") or "").strip()
    last_failure_reason = str(issue.get("last_failure_reason") or "").strip()
    backoff_until = str(issue.get("backoff_until") or "").strip()
    trust_state = str(trust.get("state") or "").strip().lower()
    trust_action = str(trust.get("recommended_operator_action") or "").strip() or "observe_issue"
    trust_summary = str(trust.get("summary") or "").strip()

    reason_code = state or "unknown_state"
    summary = trust_summary or "Issue state needs inspection."
    recommended_action = trust_action
    blocking = False

    if state == "needs_clarification":
        reason_code = "needs_clarification"
        summary = (
            last_failure_reason
            or "Issue needs more structured detail before Flow Healer can safely make changes."
        )
        recommended_action = "tighten_issue_contract"
        blocking = True
    elif state in {"claimed", "running", "verify_pending"}:
        reason_code = "actively_processing"
        summary = "Issue is currently being processed by Flow Healer."
        recommended_action = "wait_for_attempt"
    elif state == "queued":
        if trust_state == "paused":
            reason_code = "repo_paused"
            summary = "Issue is queued, but the repo is paused."
            recommended_action = trust_action
            blocking = True
        elif trust_state == "quarantined":
            reason_code = "circuit_breaker_open"
            summary = "Issue is queued, but the circuit breaker is open for this repo."
            recommended_action = trust_action
            blocking = True
        elif trust_state == "needs_environment_fix":
            reason_code = "environment_blocked"
            summary = "Issue is queued, but repo environment blockers must be repaired first."
            recommended_action = trust_action
            blocking = True
        else:
            reason_code = "eligible"
            summary = "Issue is queued and eligible for autonomous healing."
            recommended_action = "continue_autonomous_healing"
    elif state in {"failed", "blocked"}:
        if backoff_until:
            reason_code = "backoff_active"
            summary = (
                last_failure_reason
                or f"Issue is waiting for its retry window until {backoff_until}."
            )
            recommended_action = "inspect_recent_failure"
            blocking = True
        else:
            reason_code = "last_attempt_failed"
            summary = last_failure_reason or "The last healing attempt failed and needs operator review."
            recommended_action = "inspect_recent_failure"
    elif state == "pr_pending_approval":
        reason_code = "awaiting_pr_approval"
        summary = "Issue has a patch ready and is waiting for pull-request approval."
        recommended_action = "review_patch"
    elif state == "pr_open":
        reason_code = "pr_open"
        summary = "Issue has an open pull request and is waiting for review or merge."
        recommended_action = "review_pull_request"
    elif state == "resolved":
        reason_code = "resolved"
        summary = "Issue has already been resolved."
        recommended_action = "observe_issue"

    return {
        "issue_id": issue_id,
        "state": state or "unknown",
        "reason_code": reason_code,
        "summary": summary,
        "recommended_action": recommended_action,
        "blocking": blocking,
        "evidence": {
            "trust_state": trust_state,
            "last_failure_class": last_failure_class,
            "last_failure_reason": last_failure_reason,
            "backoff_until": backoff_until,
        },
    }


def _dominant_failure_domain(
    *,
    retry_playbook_metrics: dict[str, object],
    failure_domain_metrics: dict[str, int],
) -> str:
    retry_domain = str(retry_playbook_metrics.get("dominant_domain") or "").strip()
    if retry_domain:
        return retry_domain
    candidates = [
        (domain, count)
        for domain, count in failure_domain_metrics.items()
        if domain != "total" and int(count) > 0
    ]
    if not candidates:
        return ""
    domain, _count = max(candidates, key=lambda item: (item[1], item[0]))
    return domain


def _preflight_summary_is_actionably_degraded(summary: dict[str, object]) -> bool:
    overall_class = str(summary.get("overall_class") or "").strip().lower()
    if overall_class != "degraded":
        return False
    total = max(0, int(summary.get("total") or 0))
    ready = max(0, int(summary.get("ready") or 0))
    blocked = max(0, int(summary.get("blocked") or 0))
    unknown = max(0, int(summary.get("unknown") or 0))
    return not (total > 0 and ready == 0 and blocked == 0 and unknown == total)


def _infra_pause_snapshot(store: SQLiteStore) -> dict[str, object]:
    pause_until_raw = str(store.get_state("healer_infra_pause_until") or "").strip()
    reason = str(store.get_state("healer_infra_pause_reason") or "").strip()
    active = False
    if pause_until_raw:
        try:
            pause_until = datetime.strptime(pause_until_raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            active = False
        else:
            active = datetime.now(UTC) < pause_until
    return {
        "active": active,
        "until": pause_until_raw,
        "reason": reason,
    }


def _reliability_canary_metrics(store: SQLiteStore, *, window: int = 50) -> dict[str, object]:
    attempts = store.list_recent_healer_attempts(limit=max(1, int(window)))
    metrics = _compute_reliability_metrics(attempts)
    metrics["window"] = max(1, int(window))
    return metrics


def _reliability_daily_rollups(store: SQLiteStore, *, days: int = 30) -> list[dict[str, object]]:
    attempts = store.list_healer_attempts_in_window(days=max(1, int(days)), limit=10_000)
    by_day: dict[str, list[dict[str, object]]] = {}
    for attempt in attempts:
        started_at = str(attempt.get("started_at") or "").strip()
        day = started_at[:10] if len(started_at) >= 10 else ""
        if not day:
            continue
        by_day.setdefault(day, []).append(attempt)
    rollups: list[dict[str, object]] = []
    for day in sorted(by_day.keys(), reverse=True):
        metrics = _compute_reliability_metrics(by_day[day])
        rollups.append(
            {
                "day": day,
                "sample_size": metrics["sample_size"],
                "issue_count": metrics["issue_count"],
                "first_pass_success_rate": metrics["first_pass_success_rate"],
                "retries_per_success": metrics["retries_per_success"],
                "wrong_root_execution_rate": metrics["wrong_root_execution_rate"],
                "no_op_rate": metrics["no_op_rate"],
                "mean_time_to_valid_pr_minutes": metrics["mean_time_to_valid_pr_minutes"],
            }
        )
    return rollups[:max(1, int(days))]


def _reliability_trend_metrics(store: SQLiteStore) -> dict[str, object]:
    current_7 = _compute_reliability_metrics(store.list_healer_attempts_in_window(days=7, offset_days=0, limit=10_000))
    previous_7 = _compute_reliability_metrics(store.list_healer_attempts_in_window(days=7, offset_days=7, limit=10_000))
    current_30 = _compute_reliability_metrics(store.list_healer_attempts_in_window(days=30, offset_days=0, limit=20_000))
    previous_30 = _compute_reliability_metrics(store.list_healer_attempts_in_window(days=30, offset_days=30, limit=20_000))
    return {
        "7d": _trend_window_snapshot(window_days=7, current=current_7, previous=previous_7),
        "30d": _trend_window_snapshot(window_days=30, current=current_30, previous=previous_30),
    }


def _trend_window_snapshot(
    *,
    window_days: int,
    current: dict[str, object],
    previous: dict[str, object],
) -> dict[str, object]:
    current_first_pass = _safe_float(current.get("first_pass_success_rate"))
    previous_first_pass = _safe_float(previous.get("first_pass_success_rate"))
    current_no_op = _safe_float(current.get("no_op_rate"))
    previous_no_op = _safe_float(previous.get("no_op_rate"))
    current_wrong_root = _safe_float(current.get("wrong_root_execution_rate"))
    previous_wrong_root = _safe_float(previous.get("wrong_root_execution_rate"))
    current_mean_ttvp = _safe_float(current.get("mean_time_to_valid_pr_minutes"))
    previous_mean_ttvp = _safe_float(previous.get("mean_time_to_valid_pr_minutes"))
    return {
        "window_days": int(window_days),
        "current": current,
        "previous": previous,
        "changes": {
            "first_pass_success_rate": round(current_first_pass - previous_first_pass, 4),
            "no_op_rate": round(current_no_op - previous_no_op, 4),
            "wrong_root_execution_rate": round(current_wrong_root - previous_wrong_root, 4),
            "mean_time_to_valid_pr_minutes": round(current_mean_ttvp - previous_mean_ttvp, 4),
            "sample_size": int(current.get("sample_size") or 0) - int(previous.get("sample_size") or 0),
            "issue_count": int(current.get("issue_count") or 0) - int(previous.get("issue_count") or 0),
        },
        "improvements": {
            "first_pass_success_rate_up": round(current_first_pass - previous_first_pass, 4),
            "no_op_rate_down": round(previous_no_op - current_no_op, 4),
            "wrong_root_execution_rate_down": round(previous_wrong_root - current_wrong_root, 4),
            "mean_time_to_valid_pr_minutes_down": round(previous_mean_ttvp - current_mean_ttvp, 4),
        },
    }


def _compute_reliability_metrics(attempts: list[dict[str, object]]) -> dict[str, object]:
    if not attempts:
        return {
            "sample_size": 0,
            "issue_count": 0,
            "first_pass_success_rate": 0.0,
            "retries_per_success": 0.0,
            "wrong_root_execution_rate": 0.0,
            "no_op_rate": 0.0,
            "mean_time_to_valid_pr_minutes": 0.0,
        }

    issue_attempts: dict[str, list[dict[str, object]]] = {}
    wrong_root_count = 0
    no_op_count = 0
    valid_pr_durations: list[float] = []
    success_states = {"pr_open", "pr_pending_approval"}
    wrong_root_sources = {"fallback", "language_default", "unknown"}

    for attempt in attempts:
        issue_id = str(attempt.get("issue_id") or "").strip()
        if issue_id:
            issue_attempts.setdefault(issue_id, []).append(attempt)
        failure_class = str(attempt.get("failure_class") or "").strip()
        no_op = failure_class in {"no_patch", "empty_diff"} or failure_class.startswith("no_workspace_change")
        if no_op:
            no_op_count += 1
        summary = attempt.get("test_summary") or {}
        execution_root_source = ""
        if isinstance(summary, dict):
            execution_root_source = str(summary.get("execution_root_source") or "").strip().lower()
        wrong_root = failure_class == "language_unresolved" or execution_root_source in wrong_root_sources
        if wrong_root:
            wrong_root_count += 1
        state = str(attempt.get("state") or "").strip().lower()
        if state == "pr_open":
            duration = _attempt_duration_minutes(attempt)
            if duration is not None:
                valid_pr_durations.append(duration)

    first_pass_successes = 0
    retries_before_success: list[int] = []
    for per_issue_attempts in issue_attempts.values():
        sorted_attempts = sorted(
            per_issue_attempts,
            key=lambda item: int(item.get("attempt_no") or 0),
        )
        if not sorted_attempts:
            continue
        first = sorted_attempts[0]
        if str(first.get("state") or "").strip().lower() in success_states:
            first_pass_successes += 1
        first_success_attempt = next(
            (
                int(item.get("attempt_no") or 0)
                for item in sorted_attempts
                if str(item.get("state") or "").strip().lower() in success_states
            ),
            0,
        )
        if first_success_attempt > 0:
            retries_before_success.append(max(0, first_success_attempt - 1))

    sample_size = len(attempts)
    issue_count = len(issue_attempts)
    first_pass_success_rate = (
        float(first_pass_successes) / float(max(1, issue_count))
        if issue_count > 0
        else 0.0
    )
    retries_per_success = (
        float(sum(retries_before_success)) / float(len(retries_before_success))
        if retries_before_success
        else 0.0
    )
    wrong_root_execution_rate = float(wrong_root_count) / float(max(1, sample_size))
    no_op_rate = float(no_op_count) / float(max(1, sample_size))
    mean_time_to_valid_pr = (
        float(sum(valid_pr_durations)) / float(len(valid_pr_durations))
        if valid_pr_durations
        else 0.0
    )
    return {
        "sample_size": sample_size,
        "issue_count": issue_count,
        "first_pass_success_rate": round(first_pass_success_rate, 4),
        "retries_per_success": round(retries_per_success, 4),
        "wrong_root_execution_rate": round(wrong_root_execution_rate, 4),
        "no_op_rate": round(no_op_rate, 4),
        "mean_time_to_valid_pr_minutes": round(mean_time_to_valid_pr, 2),
    }


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _attempt_duration_minutes(attempt: dict[str, object]) -> float | None:
    started_at = str(attempt.get("started_at") or "").strip()
    finished_at = str(attempt.get("finished_at") or "").strip()
    if not started_at or not finished_at:
        return None
    try:
        start_dt = datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        end_dt = datetime.strptime(finished_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None
    elapsed = (end_dt - start_dt).total_seconds() / 60.0
    if elapsed < 0:
        return None
    return elapsed


def _launch_agent_path(label: str) -> str:
    if shutil.which("launchctl") is None:
        return ""
    domain = f"gui/{os.getuid()}/{label}"
    try:
        proc = subprocess.run(
            ["launchctl", "print", domain],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except OSError:
        return ""
    if proc.returncode != 0:
        return ""
    text = proc.stdout or ""
    path_matches = re.findall(r"^\s*PATH => ([^\n]+)$", text, flags=re.MULTILINE)
    if not path_matches:
        return ""
    # Prefer the explicit environment PATH, then fallback to default.
    return path_matches[-1].strip()


def _resolve_command_in_path(command: str, path_value: str) -> str:
    if not command.strip():
        return ""
    if os.path.isabs(command):
        return command if os.path.isfile(command) and os.access(command, os.X_OK) else ""
    return shutil.which(command, path=path_value or None) or ""
