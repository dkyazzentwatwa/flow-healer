from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .codex_app_server_connector import CodexAppServerConnector
from .codex_cli_connector import CodexCliConnector
from .config import AppConfig, RelaySettings
from .healer_loop import AutonomousHealerLoop
from .healer_preflight import list_cached_preflight_reports
from .healer_reconciler import HealerReconciler
from .healer_scan import FlowHealerScanner
from .healer_tracker import GitHubHealerTracker
from .healer_triage import classify_issue_route
from .local_healer_tracker import LocalHealerTracker
from .skill_contracts import audit_skill_contracts
from .store import SQLiteStore


@dataclass(slots=True)
class RepoRuntime:
    settings: RelaySettings
    store: SQLiteStore
    loop: AutonomousHealerLoop
    tracker: GitHubHealerTracker | LocalHealerTracker
    connector: object


class FlowHealerService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

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
        if self.config.service.connector_backend == "app_server":
            connector = CodexAppServerConnector(
                workspace=repo.healer_repo_path,
                codex_command=self.config.service.connector_command,
                timeout=self.config.service.connector_timeout_seconds,
                model=self.config.service.connector_model,
                reasoning_effort=self.config.service.connector_reasoning_effort,
            )
        else:
            connector = CodexCliConnector(
                workspace=repo.healer_repo_path,
                codex_command=self.config.service.connector_command,
                timeout=self.config.service.connector_timeout_seconds,
                model=self.config.service.connector_model,
                reasoning_effort=self.config.service.connector_reasoning_effort,
            )
        loop = AutonomousHealerLoop(settings=repo, store=store, connector=connector, tracker=tracker)
        if repo.healer_repo_slug and not loop.tracker.repo_slug:
            loop.tracker.repo_slug = repo.healer_repo_slug
        return RepoRuntime(settings=repo, store=store, loop=loop, tracker=loop.tracker, connector=connector)

    def start(self, repo_name: str | None = None, *, once: bool = False) -> None:
        repos = self.config.select_repos(repo_name)
        if once:
            for repo in repos:
                runtime = self.build_runtime(repo)
                try:
                    runtime.loop._tick_once()
                finally:
                    self._close_runtime(runtime)
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

        asyncio.run(_run())

    def status_rows(self, repo_name: str | None = None) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for repo in self.config.select_repos(repo_name):
            runtime = self.build_runtime(repo)
            try:
                connector_health = runtime.loop._connector_health_snapshot()
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
                            "available": connector_health.get("available"),
                            "configured_command": connector_health.get("configured_command"),
                            "resolved_command": connector_health.get("resolved_command"),
                            "availability_reason": connector_health.get("availability_reason"),
                            "last_health_error": connector_health.get("last_health_error"),
                            "last_runtime_error_kind": connector_health.get("last_runtime_error_kind"),
                            "last_runtime_stdout_tail": connector_health.get("last_runtime_stdout_tail"),
                            "last_runtime_stderr_tail": connector_health.get("last_runtime_stderr_tail"),
                            "last_checked_at": runtime.store.get_state("healer_connector_last_checked_at") or "",
                            "last_error_class": runtime.store.get_state("healer_connector_last_error_class") or "",
                            "last_error_reason": runtime.store.get_state("healer_connector_last_error_reason") or "",
                            "last_error_at": runtime.store.get_state("healer_connector_last_error_at") or "",
                            "last_failure_fingerprint": runtime.store.get_state("healer_last_failure_fingerprint") or "",
                            "last_failure_fingerprint_issue_id": runtime.store.get_state("healer_last_failure_fingerprint_issue_id") or "",
                            "last_failure_fingerprint_class": runtime.store.get_state("healer_last_failure_fingerprint_class") or "",
                            "last_contamination_paths": runtime.store.get_state("healer_last_contamination_paths") or "",
                        },
                        "resource_audit": HealerReconciler(
                            store=runtime.store,
                            workspace_manager=runtime.loop.workspace_manager,
                        ).resource_audit(),
                        "preflight": {
                            "gate_mode": repo.healer_test_gate_mode,
                            "reports": [
                                {
                                    "language": report.language,
                                    "execution_root": report.execution_root,
                                    "status": report.status,
                                    "failure_class": report.failure_class,
                                    "summary": report.summary,
                                    "checked_at": report.checked_at,
                                }
                                for report in list_cached_preflight_reports(
                                    store=runtime.store,
                                    gate_mode=repo.healer_test_gate_mode,
                                )
                            ],
                        },
                        "app_server_metrics": _app_server_metrics(runtime.store),
                        "recent_attempts": annotated_attempts,
                    }
                )
            finally:
                self._close_runtime(runtime)
        return rows

    def set_paused(self, paused: bool, repo_name: str | None = None) -> None:
        for repo in self.config.select_repos(repo_name):
            runtime = self.build_runtime(repo)
            try:
                runtime.store.set_state("healer_paused", "true" if paused else "false")
            finally:
                self._close_runtime(runtime)

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
        return results

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
                runtime.loop._record_connector_health(connector_health)
                breaker = runtime.loop._circuit_breaker_status()
                git_ok = _check_command(["git", "-C", str(repo_path), "rev-parse", "--is-inside-work-tree"])
                branch_ok = _check_command(["git", "-C", str(repo_path), "rev-parse", "--verify", repo.healer_default_branch])
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
                        "connector_command": self.config.service.connector_command,
                        "connector_resolved_command": connector_health.get("resolved_command"),
                        "connector_availability_reason": connector_health.get("availability_reason"),
                        "connector_last_health_error": connector_health.get("last_health_error"),
                        "connector_last_runtime_error_kind": connector_health.get("last_runtime_error_kind"),
                        "connector_last_runtime_stdout_tail": connector_health.get("last_runtime_stdout_tail"),
                        "connector_last_runtime_stderr_tail": connector_health.get("last_runtime_stderr_tail"),
                        "last_failure_fingerprint": runtime.store.get_state("healer_last_failure_fingerprint") or "",
                        "last_failure_fingerprint_issue_id": runtime.store.get_state("healer_last_failure_fingerprint_issue_id") or "",
                        "last_failure_fingerprint_class": runtime.store.get_state("healer_last_failure_fingerprint_class") or "",
                        "last_contamination_paths": runtime.store.get_state("healer_last_contamination_paths") or "",
                        "launchd_path": launchd_path,
                        "launchd_path_has_connector": bool(launchd_path_connector),
                        "launchd_path_connector": launchd_path_connector or "",
                        "github_token_env": token_name,
                        "github_token_present": token_present,
                        "preflight_gate_mode": repo.healer_test_gate_mode,
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

    @staticmethod
    def _close_runtime(runtime: RepoRuntime) -> None:
        try:
            runtime.connector.shutdown()  # type: ignore[call-arg]
        except Exception:
            pass
        runtime.store.close()


def _check_command(cmd: list[str]) -> bool:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=15)
    return proc.returncode == 0


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
        "zero_diff_rate_by_task_kind": zero_diff_rate_by_task_kind,
    }


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
