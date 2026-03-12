from __future__ import annotations

import json
import inspect
import hashlib
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .app_harness import AppHarnessSession, AppRuntimeProfile, LocalAppHarness
from .browser_harness import BrowserJourneyResult, LocalBrowserHarness, parse_repro_steps
from .docker_runtime import ensure_docker_runtime_running, record_docker_activity
from .language_detector import detect_language_details
from .language_strategies import (
    LanguageStrategy,
    UnsupportedLanguageError,
    ensure_supported_language,
    get_strategy,
    is_removed_language,
)
from .protocols import ConnectorProtocol, ConnectorTurnResult
from .healer_task_spec import HealerTaskSpec, task_spec_to_prompt_block

logger = logging.getLogger("apple_flow.healer_runner")
_FENCED_BLOCK_RE = re.compile(r"```(?P<lang>[^\n`]*)\n(?P<body>.*?)```", re.DOTALL)
_FENCE_PATH_RE = re.compile(r"(?:^|\s)path=(?P<path>[^\s`]+)")
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_NON_RETRYABLE_FAILURES = {"connector_unavailable", "connector_runtime_error"}
_NO_WORKSPACE_CHANGE_CLASS_PREFIX = "no_workspace_change:"
_INPUT_CONTEXT_MAX_CHARS = 12_000
_DOCKER_UNSUPPORTED_REASON = "docker_unsupported_for_language"
_COMPLETION_ARTIFACT_MODES = {"always", "fallback_only"}
_DOCKER_INFRA_OUTPUT_HINTS = (
    "cannot connect to the docker daemon",
    "is the docker daemon running",
    "error during connect",
    "500 server error",
    "internal server error",
    "context canceled",
    "docker desktop is not running",
)


@dataclass(slots=True, frozen=True)
class HealerRunResult:
    success: bool
    failure_class: str
    failure_reason: str
    failure_fingerprint: str
    proposer_output: str
    diff_paths: list[str]
    diff_files: int
    diff_lines: int
    test_summary: dict[str, Any]
    workspace_status: dict[str, Any]


@dataclass(slots=True, frozen=True)
class ResolvedExecution:
    language_detected: str
    language_effective: str
    execution_root: str
    execution_root_source: str
    execution_path: Path
    strategy: LanguageStrategy


@dataclass(slots=True, frozen=True)
class FilteredStageResult:
    kept_paths: list[str]
    excluded_paths: list[str]


@dataclass(slots=True, frozen=True)
class WorkspaceStatusEntry:
    status: str
    path: str


@dataclass(slots=True, frozen=True)
class PathFenceMaterializationResult:
    wrote_any: bool
    rejection_reason: str = ""


@dataclass(slots=True, frozen=True)
class NormalizedValidationCommandsResult:
    normalized_commands: tuple[str, ...]
    rejection_reason: str = ""


class HealerRunner:
    def __init__(
        self,
        connector: ConnectorProtocol,
        *,
        timeout_seconds: int,
        test_gate_mode: str = "local_then_docker",
        local_gate_policy: str = "auto",
        language: str = "",
        docker_image: str = "",
        test_command: str = "",
        install_command: str = "",
        default_runtime_profile: str = "",
        app_runtime_profiles: Any = None,
        app_harness: LocalAppHarness | None = None,
        browser_harness: LocalBrowserHarness | None = None,
        completion_artifact_mode: str = "fallback_only",
        auto_clean_generated_artifacts: bool = True,
    ) -> None:
        self.connector = connector
        self.timeout_seconds = max(30, int(timeout_seconds))
        self.test_gate_mode = _normalize_test_gate_mode(test_gate_mode)
        self.local_gate_policy = _normalize_local_gate_policy(local_gate_policy)
        self.completion_artifact_mode = _normalize_completion_artifact_mode(completion_artifact_mode)
        self._language = language.strip()
        self._docker_image = docker_image.strip()
        self._test_command = test_command.strip()
        self._install_command = install_command.strip()
        self._default_runtime_profile = str(default_runtime_profile or "").strip()
        self._app_runtime_profiles = _normalize_app_runtime_profiles(app_runtime_profiles)
        self._app_harness = app_harness or LocalAppHarness()
        self._browser_harness = browser_harness or LocalBrowserHarness()
        self.auto_clean_generated_artifacts = bool(auto_clean_generated_artifacts)
        self.max_proposer_retries = 1
        self.max_code_proposer_retries = 3
        self.max_artifact_proposer_retries = 2
        self.code_change_turn_timeout_seconds = max(900, self.timeout_seconds)
        # Allow one cleanup before validation and one more after validation if tests regenerate artifacts.
        self.max_generated_artifact_cleanup_cycles = 2

    def _task_requests_app_runtime(self, *, task_spec: HealerTaskSpec) -> bool:
        return any(
            (
                task_spec.app_target,
                task_spec.entry_url,
                task_spec.repro_steps,
                task_spec.runtime_profile,
            )
        )

    def _task_requests_browser_evidence(self, *, task_spec: HealerTaskSpec) -> bool:
        return bool(task_spec.repro_steps) and self._task_requests_app_runtime(task_spec=task_spec)

    def _resolve_app_runtime_profile(
        self,
        *,
        task_spec: HealerTaskSpec,
        workspace: Path,
    ) -> tuple[AppRuntimeProfile | None, str, str]:
        if not self._task_requests_app_runtime(task_spec=task_spec):
            return None, "", ""

        selected_name = str(task_spec.runtime_profile or self._default_runtime_profile).strip()
        if not selected_name and len(self._app_runtime_profiles) == 1:
            selected_name = next(iter(self._app_runtime_profiles))
        if not selected_name:
            return None, "app_runtime_profile_missing", "App-scoped task did not declare a runtime profile and no default runtime profile is configured."

        profile = self._app_runtime_profiles.get(selected_name)
        if profile is None:
            return None, "app_runtime_profile_missing", f"Runtime profile '{selected_name}' is not configured."

        cwd = profile.cwd
        if not cwd.is_absolute():
            cwd = (workspace / cwd).resolve()
        profile = AppRuntimeProfile(
            name=profile.name,
            command=profile.command,
            cwd=cwd,
            env=profile.env,
            install_command=tuple(profile.install_command or ()),
            install_marker_path=str(profile.install_marker_path or ""),
            readiness_url=profile.readiness_url,
            readiness_log_text=profile.readiness_log_text,
            fixture_driver_command=tuple(profile.fixture_driver_command or ()),
            browser=profile.browser,
            headless=profile.headless,
            viewport=dict(profile.viewport or {}) or None,
            device=profile.device,
            startup_timeout_seconds=profile.startup_timeout_seconds,
            shutdown_timeout_seconds=profile.shutdown_timeout_seconds,
            poll_interval_seconds=profile.poll_interval_seconds,
        )
        if not profile.command:
            return None, "app_runtime_profile_invalid", f"Runtime profile '{selected_name}' does not define a start command."
        return profile, "", ""

    def _run_fixture_driver(
        self,
        *,
        profile: AppRuntimeProfile,
        fixture_profile: str,
        action: str,
        extra_args: tuple[str, ...] = (),
    ) -> None:
        if not fixture_profile:
            return
        command = tuple(profile.fixture_driver_command or ())
        if not command:
            return

        env = os.environ.copy()
        if profile.env:
            env.update(profile.env)
        full_command = [*command, action, fixture_profile, *extra_args]
        result = subprocess.run(
            full_command,
            cwd=profile.cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return
        output_tail = "\n".join((result.stdout or "").splitlines()[-40:])
        raise RuntimeError(
            f"{profile.name} fixture driver '{action}' failed "
            f"(exit code {result.returncode}). Output tail:\n{output_tail}"
        )

    def _materialize_fixture_auth_state(
        self,
        *,
        profile: AppRuntimeProfile,
        fixture_profile: str,
        entry_url: str,
        browser_artifact_root: Path,
        phase: str,
    ) -> str:
        if not fixture_profile or not profile.fixture_driver_command:
            return ""

        output_path = (browser_artifact_root / "storage-state" / f"{phase}.json").resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._run_fixture_driver(
            profile=profile,
            fixture_profile=fixture_profile,
            action="auth-state",
            extra_args=(str(output_path), entry_url),
        )
        if not output_path.exists():
            raise RuntimeError(
                f"{profile.name} fixture driver did not create auth state at {output_path}"
            )
        return str(output_path)

    def run_attempt(
        self,
        *,
        issue_id: str,
        issue_title: str,
        issue_body: str,
        task_spec: HealerTaskSpec,
        learned_context: str = "",
        feedback_context: str = "",
        workspace: Path,
        max_diff_files: int,
        max_diff_lines: int,
        max_failed_tests_allowed: int,
        targeted_tests: list[str],
        native_multi_agent_profile: str = "",
        native_multi_agent_max_subagents: int = 0,
    ) -> HealerRunResult:
        self._bind_connector_workspace(workspace)
        resolved_execution = self.resolve_execution(workspace=workspace, task_spec=task_spec)
        workspace_status = _empty_workspace_status(execution_root=resolved_execution.execution_root)
        completion_parser_mode = "not_attempted"
        completion_parser_confidence = 0.0
        completion_parser_source = ""
        completion_parser_reason = ""
        _annotate_completion_artifact_parser(
            workspace_status,
            mode=completion_parser_mode,
            confidence=completion_parser_confidence,
        )
        app_server_forced_serialized_recovery_attempted = False
        app_server_forced_serialized_recovery_succeeded = False
        app_server_exec_failover_attempted = False
        app_server_exec_failover_succeeded = False

        def _annotate_app_server_recovery_status(status: dict[str, Any]) -> None:
            status["app_server_forced_serialized_recovery_attempted"] = app_server_forced_serialized_recovery_attempted
            status["app_server_forced_serialized_recovery_succeeded"] = app_server_forced_serialized_recovery_succeeded
            status["app_server_exec_failover_attempted"] = app_server_exec_failover_attempted
            status["app_server_exec_failover_succeeded"] = app_server_exec_failover_succeeded

        _annotate_app_server_recovery_status(workspace_status)
        cleanup_cycles_used = 0
        browser_evidence_requested = self._task_requests_browser_evidence(task_spec=task_spec)
        browser_profile: AppRuntimeProfile | None = None
        browser_artifact_bundle: dict[str, Any] = {}
        browser_artifact_links: list[dict[str, Any]] = []
        repro_stability: dict[str, Any] = {}
        parsed_repro_steps = parse_repro_steps(task_spec.repro_steps) if task_spec.repro_steps else ()
        browser_artifact_root = Path(
            tempfile.mkdtemp(prefix=f"flow-healer-browser-{issue_id}-", dir=os.getenv("TMPDIR") or None)
        ).resolve()

        if browser_evidence_requested:
            browser_ready, browser_reason = self._browser_harness.check_runtime_available()
            if not browser_ready:
                return HealerRunResult(
                    success=False,
                    failure_class="browser_runtime_missing",
                    failure_reason=browser_reason or "Browser runtime is unavailable.",
                    failure_fingerprint="",
                    proposer_output="",
                    diff_paths=[],
                    diff_files=0,
                    diff_lines=0,
                    test_summary=_with_workspace_status(
                        _annotate_browser_failure_family(
                            {},
                            failure_class="browser_runtime_missing",
                            failure_reason=browser_reason or "Browser runtime is unavailable.",
                        ),
                        workspace_status=workspace_status,
                        failure_fingerprint="",
                    ),
                    workspace_status=workspace_status,
                )
            browser_profile, runtime_failure_class, runtime_failure_reason = self._resolve_app_runtime_profile(
                task_spec=task_spec,
                workspace=workspace,
            )
            if browser_profile is None:
                if runtime_failure_class:
                    browser_runtime_status = {
                        "status": "unconfigured",
                        "profile": str(task_spec.runtime_profile or self._default_runtime_profile).strip(),
                        "entry_url": task_spec.entry_url,
                        "app_target": task_spec.app_target,
                        "fixture_profile": task_spec.fixture_profile,
                        "reason": runtime_failure_reason,
                    }
                    _annotate_app_runtime_status(workspace_status, browser_runtime_status)
                return HealerRunResult(
                    success=False,
                    failure_class=runtime_failure_class or "app_runtime_profile_missing",
                    failure_reason=runtime_failure_reason or "App runtime profile is required for browser evidence.",
                    failure_fingerprint="",
                    proposer_output="",
                    diff_paths=[],
                    diff_files=0,
                    diff_lines=0,
                    test_summary=_with_workspace_status(
                        _annotate_browser_failure_family(
                            {},
                            failure_class=runtime_failure_class or "app_runtime_profile_missing",
                            failure_reason=runtime_failure_reason or "App runtime profile is required for browser evidence.",
                        ),
                        workspace_status=workspace_status,
                        failure_fingerprint="",
                    ),
                    workspace_status=workspace_status,
                )

            pre_fix_session: AppHarnessSession | None = None
            browser_entry_url = task_spec.entry_url or browser_profile.readiness_url or ""
            try:
                self._run_fixture_driver(
                    profile=browser_profile,
                    fixture_profile=task_spec.fixture_profile,
                    action="prepare",
                )
                boot_result, pre_fix_session = self._app_harness.boot(browser_profile)
                pre_fix_storage_state_path = self._materialize_fixture_auth_state(
                    profile=browser_profile,
                    fixture_profile=task_spec.fixture_profile,
                    entry_url=browser_entry_url,
                    browser_artifact_root=browser_artifact_root,
                    phase="failure",
                )
                pre_fix_runtime_status = {
                    "status": "ready",
                    "profile": boot_result.profile.name,
                    "pid": boot_result.pid,
                    "process": _app_runtime_process_metadata(profile=boot_result.profile, pid=boot_result.pid),
                    "readiness_url": boot_result.readiness_url or task_spec.entry_url,
                    "entry_url": browser_entry_url,
                    "app_target": task_spec.app_target,
                    "fixture_profile": task_spec.fixture_profile,
                    "ready_via_url": boot_result.ready_via_url,
                    "ready_via_log": boot_result.ready_via_log,
                    "startup_seconds": round(boot_result.startup_seconds, 3),
                }
                _annotate_app_runtime_status(workspace_status, pre_fix_runtime_status)
                failure_journey = self._browser_harness.capture_journey(
                    profile=browser_profile,
                    entry_url=browser_entry_url,
                    repro_steps=parsed_repro_steps,
                    artifact_root=browser_artifact_root / "failure",
                    phase="failure",
                    expect_failure=True,
                    storage_state_path=pre_fix_storage_state_path,
                )
                if not failure_journey.passed and failure_journey.expected_failure_observed:
                    confirmatory_failure_journey = self._browser_harness.capture_journey(
                        profile=browser_profile,
                        entry_url=browser_entry_url,
                        repro_steps=parsed_repro_steps,
                        artifact_root=browser_artifact_root / "failure-replay",
                        phase="failure-replay",
                        expect_failure=True,
                        storage_state_path=pre_fix_storage_state_path,
                    )
                    repro_stability = _browser_repro_stability(
                        initial=failure_journey,
                        replay=confirmatory_failure_journey,
                    )
            except Exception as exc:
                failure_summary = _annotate_test_summary_browser_artifacts(
                    _annotate_test_summary_runtime(
                        {},
                        workspace_status=workspace_status,
                        task_spec=task_spec,
                    ),
                    artifact_bundle=browser_artifact_bundle,
                    artifact_links=browser_artifact_links,
                )
                return HealerRunResult(
                    success=False,
                    failure_class="browser_step_failed",
                    failure_reason=str(exc),
                    failure_fingerprint="",
                    proposer_output="",
                    diff_paths=[],
                    diff_files=0,
                    diff_lines=0,
                    test_summary=_with_workspace_status(
                        _annotate_browser_failure_family(
                            failure_summary,
                            failure_class="browser_step_failed",
                            failure_reason=str(exc),
                        ),
                        workspace_status=workspace_status,
                        failure_fingerprint="",
                    ),
                    workspace_status=workspace_status,
                )
            finally:
                if pre_fix_session is not None:
                    try:
                        pre_fix_session.stop()
                    except Exception as exc:
                        logger.warning("Failed to stop pre-fix app runtime profile '%s': %s", browser_profile.name, exc)

            browser_artifact_bundle = _browser_artifact_bundle(
                profile=browser_profile,
                entry_url=browser_entry_url,
                session_root=str(browser_artifact_root),
                failure_journey=failure_journey,
            )
            browser_artifact_links = _browser_artifact_links(browser_artifact_bundle)
            if browser_evidence_requested and not _browser_phase_artifacts_ready(
                browser_artifact_bundle,
                phase="failure_artifacts",
            ):
                missing_artifacts = ", ".join(_browser_missing_artifacts(browser_artifact_bundle))
                failure_summary = _annotate_test_summary_browser_artifacts(
                    _annotate_test_summary_runtime(
                        {},
                        workspace_status=workspace_status,
                        task_spec=task_spec,
                    ),
                    artifact_bundle=browser_artifact_bundle,
                    artifact_links=browser_artifact_links,
                )
                return HealerRunResult(
                    success=False,
                    failure_class="artifacts_missing",
                    failure_reason=(
                        "Failure browser evidence is incomplete; required screenshots are missing"
                        + (f": {missing_artifacts}" if missing_artifacts else ".")
                    ),
                    failure_fingerprint="",
                    proposer_output="",
                    diff_paths=[],
                    diff_files=0,
                    diff_lines=0,
                    test_summary=_with_workspace_status(
                        _annotate_browser_failure_family(
                            failure_summary,
                            failure_class="artifacts_missing",
                            failure_reason=(
                                "Failure browser evidence is incomplete; required screenshots are missing"
                                + (f": {missing_artifacts}" if missing_artifacts else ".")
                            ),
                        ),
                        workspace_status=workspace_status,
                        failure_fingerprint="",
                    ),
                    workspace_status=workspace_status,
                )
            if failure_journey.passed or not failure_journey.expected_failure_observed:
                failure_summary = _annotate_test_summary_browser_artifacts(
                    _annotate_test_summary_runtime(
                        {},
                        workspace_status=workspace_status,
                        task_spec=task_spec,
                    ),
                    artifact_bundle=browser_artifact_bundle,
                    artifact_links=browser_artifact_links,
                )
                failure_reason = str(failure_journey.error or "").strip()
                if failure_journey.failure_step:
                    if failure_reason:
                        failure_reason = f"{failure_reason} ({failure_journey.failure_step})"
                    else:
                        failure_reason = (
                            "Browser journey did not reproduce the reported bug before the fix "
                            f"at step '{failure_journey.failure_step}'."
                        )
                if not failure_reason:
                    failure_reason = "Browser journey did not reproduce the reported bug before the fix."
                return HealerRunResult(
                    success=False,
                    failure_class="browser_repro_failed",
                    failure_reason=failure_reason,
                    failure_fingerprint="",
                    proposer_output="",
                    diff_paths=[],
                    diff_files=0,
                    diff_lines=0,
                    test_summary=_with_workspace_status(
                        _annotate_browser_failure_family(
                            failure_summary,
                            failure_class="browser_repro_failed",
                            failure_reason=failure_reason,
                        ),
                        workspace_status=workspace_status,
                        failure_fingerprint="",
                    ),
                    workspace_status=workspace_status,
                )
            replay_reproduced = bool(repro_stability.get("reproduced_on_replay"))
            if repro_stability and not replay_reproduced:
                failure_summary = _annotate_test_summary_browser_artifacts(
                    _annotate_test_summary_runtime(
                        {},
                        workspace_status=workspace_status,
                        task_spec=task_spec,
                    ),
                    artifact_bundle=browser_artifact_bundle,
                    artifact_links=browser_artifact_links,
                )
                failure_summary["flaky_repro"] = dict(repro_stability)
                replay_error = str(repro_stability.get("replay_error") or "").strip()
                replay_step = str(repro_stability.get("replay_failure_step") or "").strip()
                failure_reason = replay_error or "Browser repro was unstable on confirmatory replay before the fix."
                if replay_step:
                    failure_reason = f"{failure_reason} ({replay_step})"
                return HealerRunResult(
                    success=False,
                    failure_class="browser_repro_failed",
                    failure_reason=failure_reason,
                    failure_fingerprint="",
                    proposer_output="",
                    diff_paths=[],
                    diff_files=0,
                    diff_lines=0,
                    test_summary=_with_workspace_status(
                        _annotate_browser_failure_family(
                            failure_summary,
                            failure_class="browser_repro_failed",
                            failure_reason=failure_reason,
                        ),
                        workspace_status=workspace_status,
                        failure_fingerprint="",
                    ),
                    workspace_status=workspace_status,
                )
        sender = f"healer:{issue_id}"
        workspace_edit_mode = _prefers_workspace_edits(connector=self.connector, task_spec=task_spec)
        # For app-server workspace-edit mode, always start each attempt with a fresh thread.
        # Reusing prior issue threads across attempts can cause stale-context "status only" responses
        # against a newly reset worktree.
        thread_id = (
            self.connector.reset_thread(sender)
            if workspace_edit_mode
            else self.connector.get_or_create_thread(sender)
        )
        language_hint = ""
        if resolved_execution.language_effective and resolved_execution.language_effective != "unknown":
            language_hint = (
                f"This repository uses {resolved_execution.language_effective}. "
                f"Follow {resolved_execution.language_effective} conventions for all edits.\n"
            )
            if resolved_execution.execution_root:
                language_hint += f"Run installs and tests from {resolved_execution.execution_root}.\n"
        prompt = _build_proposer_prompt(
            issue_id=issue_id,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            workspace=workspace,
            learned_context=learned_context,
            feedback_context=feedback_context,
            language_hint=language_hint,
            prefer_workspace_edits=workspace_edit_mode,
            native_multi_agent_profile=native_multi_agent_profile,
            native_multi_agent_max_subagents=native_multi_agent_max_subagents,
        )
        proposer_output = ""
        failure_class = ""
        failure_reason = ""
        no_workspace_change_retries_used = 0
        max_retries = _proposer_retry_budget_for_task(
            task_spec=task_spec,
            default_retries=self.max_proposer_retries,
            code_change_retries=self.max_code_proposer_retries,
            artifact_retries=self.max_artifact_proposer_retries,
        )
        turn_timeout_seconds = _turn_timeout_seconds_for_task(
            task_spec=task_spec,
            default_timeout_seconds=self.timeout_seconds,
            code_change_timeout_seconds=self.code_change_turn_timeout_seconds,
        )
        for proposer_attempt in range(max_retries + 1):
            turn_result = _run_connector_turn(
                self.connector,
                thread_id,
                prompt,
                timeout_seconds=turn_timeout_seconds,
            )
            proposer_output = turn_result.output_text
            initial_stage_result = _stage_workspace_changes_detailed(
                workspace,
                issue_title=issue_title,
                issue_body=issue_body,
                task_spec=task_spec,
                language=resolved_execution.language_effective,
            )
            stage_excluded_paths = list(initial_stage_result.excluded_paths)
            if initial_stage_result.kept_paths:
                break
            if workspace_edit_mode:
                path_fence_result = _materialize_named_code_targets_from_output(
                    task_spec=task_spec,
                    proposer_output=proposer_output,
                    workspace=workspace,
                    strict=True,
                )
                if path_fence_result.wrote_any:
                    completion_parser_mode = "strict"
                    completion_parser_confidence = 1.0
                    completion_parser_source = "named_output_targets"
                    completion_parser_reason = ""
                    _annotate_completion_artifact_parser(
                        workspace_status,
                        mode=completion_parser_mode,
                        confidence=completion_parser_confidence,
                        source=completion_parser_source,
                        reason=completion_parser_reason,
                    )
                elif self.completion_artifact_mode == "always":
                    lenient_result = _materialize_named_code_targets_from_output(
                        task_spec=task_spec,
                        proposer_output=proposer_output,
                        workspace=workspace,
                        strict=False,
                    )
                    if lenient_result.wrote_any:
                        path_fence_result = lenient_result
                        completion_parser_mode = "lenient"
                        completion_parser_confidence = 0.65
                        completion_parser_source = "named_output_targets"
                        completion_parser_reason = ""
                        _annotate_completion_artifact_parser(
                            workspace_status,
                            mode=completion_parser_mode,
                            confidence=completion_parser_confidence,
                            source=completion_parser_source,
                            reason=completion_parser_reason,
                        )
                    elif lenient_result.rejection_reason and not path_fence_result.rejection_reason:
                        path_fence_result = lenient_result
                if path_fence_result.wrote_any:
                    stage_after_path_fence = _stage_workspace_changes_detailed(
                        workspace,
                        issue_title=issue_title,
                        issue_body=issue_body,
                        task_spec=task_spec,
                        language=resolved_execution.language_effective,
                    )
                    stage_excluded_paths.extend(stage_after_path_fence.excluded_paths)
                else:
                    stage_after_path_fence = FilteredStageResult(kept_paths=[], excluded_paths=[])
                if path_fence_result.wrote_any and stage_after_path_fence.kept_paths:
                    failure_class = ""
                    failure_reason = ""
                    break
                # Fallback: accept explicit path-fenced file outputs when direct workspace
                # edits were not staged (mirrors the non-workspace-edit recovery path).
                if not _allows_named_code_target_fallback(task_spec) and _materialize_explicit_path_fenced_files(
                    task_spec=task_spec,
                    proposer_output=proposer_output,
                    workspace=workspace,
                ) and _stage_workspace_changes(
                    workspace,
                    issue_title=issue_title,
                    issue_body=issue_body,
                    task_spec=task_spec,
                    language=resolved_execution.language_effective,
                ):
                    failure_class = ""
                    failure_reason = ""
                    break
                if _allows_artifact_synthesis(task_spec) and _materialize_artifact_from_output(
                    task_spec=task_spec,
                    proposer_output=proposer_output,
                    workspace=workspace,
                ):
                    stage_after_artifact = _stage_workspace_changes_detailed(
                        workspace,
                        issue_title=issue_title,
                        issue_body=issue_body,
                        task_spec=task_spec,
                        language=resolved_execution.language_effective,
                    )
                    stage_excluded_paths.extend(stage_after_artifact.excluded_paths)
                else:
                    stage_after_artifact = FilteredStageResult(kept_paths=[], excluded_paths=[])
                if _allows_artifact_synthesis(task_spec) and stage_after_artifact.kept_paths:
                    failure_class = ""
                    failure_reason = ""
                    completion_parser_mode = "lenient"
                    completion_parser_confidence = 0.6
                    completion_parser_source = "artifact_synthesis"
                    completion_parser_reason = ""
                    _annotate_completion_artifact_parser(
                        workspace_status,
                        mode=completion_parser_mode,
                        confidence=completion_parser_confidence,
                        source=completion_parser_source,
                        reason=completion_parser_reason,
                    )
                    break
                patch = _extract_diff_block(proposer_output)
                if patch.strip():
                    if not _looks_like_unified_diff(patch):
                        failure_class = "malformed_diff"
                        failure_reason = "Proposer returned a diff fence, but the contents were not a valid unified diff."
                    else:
                        patch_applied, patch_apply_error = _apply_unified_diff_patch(
                            workspace=workspace,
                            patch=patch,
                            timeout_seconds=self.timeout_seconds,
                        )
                        if patch_applied:
                            stage_after_patch = _stage_workspace_changes_detailed(
                                workspace,
                                issue_title=issue_title,
                                issue_body=issue_body,
                                task_spec=task_spec,
                                language=resolved_execution.language_effective,
                            )
                            stage_excluded_paths.extend(stage_after_patch.excluded_paths)
                        else:
                            stage_after_patch = FilteredStageResult(kept_paths=[], excluded_paths=[])
                        if patch_applied and stage_after_patch.kept_paths:
                            failure_class = ""
                            failure_reason = ""
                            break
                        failure_class = "patch_apply_failed"
                        failure_reason = patch_apply_error or "git apply failed"
                if path_fence_result.rejection_reason:
                    completion_parser_mode = "failed"
                    completion_parser_confidence = 0.0
                    completion_parser_source = ""
                    completion_parser_reason = path_fence_result.rejection_reason
                    _annotate_completion_artifact_parser(
                        workspace_status,
                        mode=completion_parser_mode,
                        confidence=completion_parser_confidence,
                        source=completion_parser_source,
                        reason=completion_parser_reason,
                    )
                if not failure_class:
                    failure_class, failure_reason = _classify_non_patch_failure(proposer_output)
                    failure_reason = _augment_failure_reason_with_connector_health(
                        connector=self.connector,
                        failure_class=failure_class,
                        failure_reason=failure_reason,
                    )
                if (
                    failure_class not in _NON_RETRYABLE_FAILURES
                    and failure_class not in {"patch_apply_failed", "malformed_diff"}
                ):
                    failure_class, failure_reason = _classify_workspace_edit_noop(
                        proposer_output=proposer_output,
                        turn_result=turn_result,
                        path_fence_rejection_reason=path_fence_result.rejection_reason,
                        stage_excluded_paths=stage_excluded_paths,
                        task_spec=task_spec,
                    )
                    if no_workspace_change_retries_used >= 1:
                        recovery_prompt = _build_retry_prompt(
                            base_prompt=prompt,
                            failure_class=failure_class,
                            failure_reason=failure_reason,
                            task_spec=task_spec,
                            prefer_workspace_edits=False,
                            allow_exact_target_file_fallback=(
                                _allows_named_code_target_fallback(task_spec) or self.completion_artifact_mode == "always"
                            ),
                            allow_artifact_body_fallback=_allows_artifact_synthesis(task_spec),
                            continue_same_thread=False,
                            attempt_number=proposer_attempt,
                            issue_id=issue_id,
                            native_multi_agent_profile=native_multi_agent_profile,
                            native_multi_agent_max_subagents=native_multi_agent_max_subagents,
                        )
                        app_server_forced_serialized_recovery_attempted = True
                        _annotate_app_server_recovery_status(workspace_status)
                        thread_id = self.connector.reset_thread(sender)
                        recovery_turn = _run_connector_turn(
                            self.connector,
                            thread_id,
                            recovery_prompt,
                            timeout_seconds=turn_timeout_seconds,
                        )
                        proposer_output = recovery_turn.output_text
                        if _attempt_serialized_output_materialization(
                            workspace=workspace,
                            issue_title=issue_title,
                            issue_body=issue_body,
                            task_spec=task_spec,
                            language=resolved_execution.language_effective,
                            timeout_seconds=self.timeout_seconds,
                            proposer_output=proposer_output,
                        ):
                            app_server_forced_serialized_recovery_succeeded = True
                            _annotate_app_server_recovery_status(workspace_status)
                            failure_class = ""
                            failure_reason = ""
                            break
                        app_server_exec_failover_attempted = True
                        _annotate_app_server_recovery_status(workspace_status)
                        failover_thread_id = self.connector.reset_thread(sender)
                        failover_turn = _run_connector_exec_failover_turn(
                            self.connector,
                            failover_thread_id,
                            recovery_prompt,
                            timeout_seconds=turn_timeout_seconds,
                        )
                        if failover_turn is None:
                            failure_class = "no_workspace_change:forced_serialized_recovery_failed"
                            failure_reason = (
                                "Forced serialized-output recovery produced no staged workspace changes, "
                                "and exec failover is not available on this connector."
                            )
                            return HealerRunResult(
                                success=False,
                                failure_class=failure_class,
                                failure_reason=failure_reason,
                                failure_fingerprint=_execution_contract_failure_fingerprint(
                                    failure_class=failure_class,
                                    connector=self.connector,
                                    task_spec=task_spec,
                                ),
                                proposer_output=proposer_output,
                                diff_paths=[],
                                diff_files=0,
                                diff_lines=0,
                                test_summary={},
                                workspace_status=workspace_status,
                            )
                        proposer_output = failover_turn.output_text
                        if _attempt_serialized_output_materialization(
                            workspace=workspace,
                            issue_title=issue_title,
                            issue_body=issue_body,
                            task_spec=task_spec,
                            language=resolved_execution.language_effective,
                            timeout_seconds=self.timeout_seconds,
                            proposer_output=proposer_output,
                        ):
                            app_server_exec_failover_succeeded = True
                            _annotate_app_server_recovery_status(workspace_status)
                            failure_class = ""
                            failure_reason = ""
                            break
                        failure_class = "no_workspace_change:exec_failover_failed"
                        failure_reason = (
                            "Strict workspace-edit retry, forced serialized-output recovery, and exec failover "
                            "did not produce staged workspace changes."
                        )
                        return HealerRunResult(
                            success=False,
                            failure_class=failure_class,
                            failure_reason=failure_reason,
                            failure_fingerprint=_execution_contract_failure_fingerprint(
                                failure_class=failure_class,
                                connector=self.connector,
                                task_spec=task_spec,
                            ),
                            proposer_output=proposer_output,
                            diff_paths=[],
                            diff_files=0,
                            diff_lines=0,
                            test_summary={},
                            workspace_status=workspace_status,
                        )
                    no_workspace_change_retries_used += 1
                if proposer_attempt >= max_retries or failure_class in _NON_RETRYABLE_FAILURES:
                    # Last-resort: write a completion artifact so the run has some output.
                    if failure_class not in _NON_RETRYABLE_FAILURES and _materialize_completion_artifact(
                        issue_id=issue_id,
                        issue_title=issue_title,
                        task_spec=task_spec,
                        proposer_output=proposer_output,
                        failure_class=failure_class,
                        failure_reason=failure_reason,
                        workspace=workspace,
                    ) and _stage_workspace_changes(
                        workspace,
                        issue_title=issue_title,
                        issue_body=issue_body,
                        task_spec=task_spec,
                        language=resolved_execution.language_effective,
                    ):
                        failure_class = ""
                        failure_reason = ""
                        break
                    return HealerRunResult(
                        success=False,
                        failure_class=failure_class,
                        failure_reason=failure_reason,
                        failure_fingerprint=_execution_contract_failure_fingerprint(
                            failure_class=failure_class,
                            connector=self.connector,
                            task_spec=task_spec,
                        ),
                        proposer_output=proposer_output,
                        diff_paths=[],
                        diff_files=0,
                        diff_lines=0,
                        test_summary={},
                        workspace_status=workspace_status,
                    )
                same_thread_retry = _is_no_workspace_change_failure_class(failure_class)
                if not same_thread_retry:
                    thread_id = self.connector.reset_thread(sender)
                prompt = _build_retry_prompt(
                    base_prompt=prompt,
                    failure_class=failure_class,
                    failure_reason=failure_reason,
                    task_spec=task_spec,
                    prefer_workspace_edits=True,
                    allow_exact_target_file_fallback=(
                        _allows_named_code_target_fallback(task_spec) or self.completion_artifact_mode == "always"
                    ),
                    allow_artifact_body_fallback=_allows_artifact_synthesis(task_spec),
                    continue_same_thread=same_thread_retry,
                    require_exact_target_file_bodies=same_thread_retry,
                    attempt_number=proposer_attempt,
                    issue_id=issue_id,
                    native_multi_agent_profile=native_multi_agent_profile,
                    native_multi_agent_max_subagents=native_multi_agent_max_subagents,
                )
                continue
            patch = _extract_diff_block(proposer_output)
            if patch.strip():
                if not _looks_like_unified_diff(patch):
                    failure_class = "malformed_diff"
                    failure_reason = "Proposer returned a diff fence, but the contents were not a valid unified diff."
                    if proposer_attempt >= max_retries:
                        return HealerRunResult(
                            success=False,
                            failure_class=failure_class,
                            failure_reason=failure_reason,
                            failure_fingerprint="",
                            proposer_output=proposer_output,
                            diff_paths=[],
                            diff_files=0,
                            diff_lines=0,
                            test_summary={},
                            workspace_status=workspace_status,
                        )
                    thread_id = self.connector.reset_thread(sender)
                    prompt = _build_retry_prompt(
                        base_prompt=prompt,
                        failure_class=failure_class,
                        failure_reason=failure_reason,
                        task_spec=task_spec,
                        prefer_workspace_edits=workspace_edit_mode,
                        attempt_number=proposer_attempt,
                        issue_id=issue_id,
                        native_multi_agent_profile=native_multi_agent_profile,
                        native_multi_agent_max_subagents=native_multi_agent_max_subagents,
                    )
                    continue
                patch_applied, patch_apply_error = _apply_unified_diff_patch(
                    workspace=workspace,
                    patch=patch,
                    timeout_seconds=self.timeout_seconds,
                )
                if patch_applied and _stage_workspace_changes(
                    workspace,
                    issue_title=issue_title,
                    issue_body=issue_body,
                    task_spec=task_spec,
                    language=resolved_execution.language_effective,
                ):
                    break
                failure_class = "patch_apply_failed"
                failure_reason = patch_apply_error or "git apply failed"
            else:
                failure_class, failure_reason = _classify_non_patch_failure(proposer_output)
                failure_reason = _augment_failure_reason_with_connector_health(
                    connector=self.connector,
                    failure_class=failure_class,
                    failure_reason=failure_reason,
                )

            # Fallback 1: accept explicit path-fenced file outputs for any task kind.
            # This avoids hard-failing on no_patch when the proposer returned concrete file bodies
            # instead of unified diff syntax.
            if _materialize_explicit_path_fenced_files(
                task_spec=task_spec,
                proposer_output=proposer_output,
                workspace=workspace,
            ) and _stage_workspace_changes(
                workspace,
                issue_title=issue_title,
                issue_body=issue_body,
                task_spec=task_spec,
                language=resolved_execution.language_effective,
            ):
                failure_class = ""
                failure_reason = ""
                break

            # Fallback 2 (artifact-first): if proposer gives useful prose but no usable patch,
            # materialize the requested docs/research file directly.
            if _materialize_artifact_from_output(
                task_spec=task_spec,
                proposer_output=proposer_output,
                workspace=workspace,
            ) and _stage_workspace_changes(
                workspace,
                issue_title=issue_title,
                issue_body=issue_body,
                task_spec=task_spec,
                language=resolved_execution.language_effective,
            ):
                failure_class = ""
                failure_reason = ""
                break

            if (
                failure_class not in _NON_RETRYABLE_FAILURES
                and failure_class not in {"patch_apply_failed", "malformed_diff", "empty_diff"}
            ):
                failure_class, failure_reason = _classify_workspace_edit_noop(
                    proposer_output=proposer_output,
                    turn_result=turn_result,
                    path_fence_rejection_reason="",
                    stage_excluded_paths=[],
                    task_spec=task_spec,
                )

            if failure_class in _NON_RETRYABLE_FAILURES:
                    return HealerRunResult(
                        success=False,
                        failure_class=failure_class,
                        failure_reason=failure_reason,
                        failure_fingerprint=_execution_contract_failure_fingerprint(
                            failure_class=failure_class,
                            connector=self.connector,
                            task_spec=task_spec,
                        ),
                        proposer_output=proposer_output,
                        diff_paths=[],
                        diff_files=0,
                        diff_lines=0,
                    test_summary={},
                    workspace_status=workspace_status,
                )

            if proposer_attempt >= max_retries:
                # Last-resort: write a completion artifact so the run has some output.
                if _materialize_completion_artifact(
                    issue_id=issue_id,
                    issue_title=issue_title,
                    task_spec=task_spec,
                    proposer_output=proposer_output,
                    failure_class=failure_class,
                    failure_reason=failure_reason,
                    workspace=workspace,
                ) and _stage_workspace_changes(
                    workspace,
                    issue_title=issue_title,
                    issue_body=issue_body,
                    task_spec=task_spec,
                    language=resolved_execution.language_effective,
                ):
                    failure_class = ""
                    failure_reason = ""
                    break
                return HealerRunResult(
                    success=False,
                    failure_class=failure_class,
                    failure_reason=failure_reason,
                    failure_fingerprint=_execution_contract_failure_fingerprint(
                        failure_class=failure_class,
                        connector=self.connector,
                        task_spec=task_spec,
                    ),
                    proposer_output=proposer_output,
                    diff_paths=[],
                    diff_files=0,
                    diff_lines=0,
                    test_summary={},
                    workspace_status=workspace_status,
                )

            thread_id = self.connector.reset_thread(sender)
            prompt = _build_retry_prompt(
                base_prompt=prompt,
                failure_class=failure_class,
                failure_reason=failure_reason,
                task_spec=task_spec,
                prefer_workspace_edits=workspace_edit_mode,
                attempt_number=proposer_attempt,
                issue_id=issue_id,
                native_multi_agent_profile=native_multi_agent_profile,
                native_multi_agent_max_subagents=native_multi_agent_max_subagents,
            )

        workspace_status, cleaned_paths, contamination_reason = _stabilize_workspace_hygiene(
            workspace,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            language=resolved_execution.language_effective,
            execution_root=resolved_execution.execution_root,
            allow_cleanup=self.auto_clean_generated_artifacts and cleanup_cycles_used < self.max_generated_artifact_cleanup_cycles,
        )
        _annotate_completion_artifact_parser(
            workspace_status,
            mode=completion_parser_mode,
            confidence=completion_parser_confidence,
            source=completion_parser_source,
            reason=completion_parser_reason,
        )
        _annotate_app_server_recovery_status(workspace_status)
        if cleaned_paths:
            cleanup_cycles_used += 1
        workspace_status["cleanup_cycles_used"] = cleanup_cycles_used
        if contamination_reason:
            fingerprint = _generated_artifact_failure_fingerprint(
                workspace_status.get("contamination_paths") or workspace_status.get("cleaned_paths") or [],
                execution_root=resolved_execution.execution_root,
            )
            test_summary = _with_workspace_status(
                {},
                workspace_status=workspace_status,
                failure_fingerprint=fingerprint,
            )
            return HealerRunResult(
                success=False,
                failure_class="generated_artifact_contamination",
                failure_reason=contamination_reason,
                failure_fingerprint=fingerprint,
                proposer_output=proposer_output,
                diff_paths=[],
                diff_files=0,
                diff_lines=0,
                test_summary=test_summary,
                workspace_status=workspace_status,
            )

        diff_paths = _changed_paths(workspace)
        diff_files, diff_lines = _diff_stats(workspace)
        if not diff_paths:
            return HealerRunResult(
                success=False,
                failure_class="no_workspace_change:connector_noop",
                failure_reason="Proposer finished without producing any staged file changes.",
                failure_fingerprint="",
                proposer_output=proposer_output,
                diff_paths=[],
                diff_files=0,
                diff_lines=0,
                test_summary={},
                workspace_status=workspace_status,
            )
        if _requires_non_artifact_diff(task_spec=task_spec) and not _has_non_artifact_diff(diff_paths):
            return HealerRunResult(
                success=False,
                failure_class="no_code_diff",
                failure_reason="Code-change task produced only docs/artifact edits.",
                failure_fingerprint="",
                proposer_output=proposer_output,
                diff_paths=diff_paths,
                diff_files=diff_files,
                diff_lines=diff_lines,
                test_summary={},
                workspace_status=workspace_status,
            )
        scope_violations = _scope_violation_paths(
            diff_paths,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
        )
        if scope_violations:
            return HealerRunResult(
                success=False,
                failure_class="scope_violation",
                failure_reason=_scope_violation_reason(scope_violations),
                failure_fingerprint="",
                proposer_output=proposer_output,
                diff_paths=diff_paths,
                diff_files=diff_files,
                diff_lines=diff_lines,
                test_summary={},
                workspace_status=workspace_status,
            )
        if diff_files > max_diff_files or diff_lines > max_diff_lines:
            return HealerRunResult(
                success=False,
                failure_class="diff_limit_exceeded",
                failure_reason=f"Diff too large: files={diff_files}/{max_diff_files}, lines={diff_lines}/{max_diff_lines}",
                failure_fingerprint="",
                proposer_output=proposer_output,
                diff_paths=diff_paths,
                diff_files=diff_files,
                diff_lines=diff_lines,
                test_summary={},
                workspace_status=workspace_status,
            )

        app_runtime_session: AppHarnessSession | None = None
        app_runtime_status: dict[str, Any] = {}
        runtime_storage_state_path = ""

        def _stop_app_runtime() -> None:
            nonlocal app_runtime_session
            if app_runtime_session is None:
                return
            try:
                app_runtime_session.stop()
            except Exception as exc:
                logger.warning("Failed to stop app runtime profile '%s': %s", app_runtime_session.profile.name, exc)
            finally:
                app_runtime_session = None

        runtime_profile, runtime_failure_class, runtime_failure_reason = self._resolve_app_runtime_profile(
            task_spec=task_spec,
            workspace=workspace,
        )
        if runtime_profile is not None:
            try:
                if browser_evidence_requested:
                    self._run_fixture_driver(
                        profile=runtime_profile,
                        fixture_profile=task_spec.fixture_profile,
                        action="prepare",
                    )
                boot_result, app_runtime_session = self._app_harness.boot(runtime_profile)
                if browser_evidence_requested:
                    runtime_storage_state_path = self._materialize_fixture_auth_state(
                        profile=runtime_profile,
                        fixture_profile=task_spec.fixture_profile,
                        entry_url=task_spec.entry_url or runtime_profile.readiness_url or "",
                        browser_artifact_root=browser_artifact_root,
                        phase="resolution",
                    )
            except Exception as exc:
                app_runtime_status = {
                    "status": "failed",
                    "profile": runtime_profile.name,
                    "entry_url": task_spec.entry_url,
                    "app_target": task_spec.app_target,
                    "fixture_profile": task_spec.fixture_profile,
                    "reason": str(exc),
                }
                _annotate_app_runtime_status(workspace_status, app_runtime_status)
                return HealerRunResult(
                    success=False,
                    failure_class="app_runtime_boot_failed",
                    failure_reason=str(exc),
                    failure_fingerprint="",
                    proposer_output=proposer_output,
                    diff_paths=diff_paths,
                    diff_files=diff_files,
                    diff_lines=diff_lines,
                    test_summary=_with_workspace_status(
                        _annotate_browser_failure_family(
                            {},
                            failure_class="app_runtime_boot_failed",
                            failure_reason=str(exc),
                        ),
                        workspace_status=workspace_status,
                        failure_fingerprint="",
                    ),
                    workspace_status=workspace_status,
                )
            app_runtime_status = {
                "status": "ready",
                "profile": boot_result.profile.name,
                "pid": boot_result.pid,
                "process": _app_runtime_process_metadata(profile=boot_result.profile, pid=boot_result.pid),
                "readiness_url": boot_result.readiness_url or task_spec.entry_url,
                "entry_url": task_spec.entry_url,
                "app_target": task_spec.app_target,
                "fixture_profile": task_spec.fixture_profile,
                "ready_via_url": boot_result.ready_via_url,
                "ready_via_log": boot_result.ready_via_log,
                "startup_seconds": round(boot_result.startup_seconds, 3),
            }
            _annotate_app_runtime_status(workspace_status, app_runtime_status)
        elif runtime_failure_class:
            app_runtime_status = {
                "status": "unconfigured",
                "profile": str(task_spec.runtime_profile or self._default_runtime_profile).strip(),
                "entry_url": task_spec.entry_url,
                "app_target": task_spec.app_target,
                "fixture_profile": task_spec.fixture_profile,
                "reason": runtime_failure_reason,
            }
            _annotate_app_runtime_status(workspace_status, app_runtime_status)
            return HealerRunResult(
                success=False,
                failure_class=runtime_failure_class,
                failure_reason=runtime_failure_reason,
                failure_fingerprint="",
                proposer_output=proposer_output,
                diff_paths=diff_paths,
                diff_files=diff_files,
                diff_lines=diff_lines,
                test_summary=_with_workspace_status(
                    _annotate_browser_failure_family(
                        {},
                        failure_class=runtime_failure_class,
                        failure_reason=runtime_failure_reason,
                    ),
                    workspace_status=workspace_status,
                    failure_fingerprint="",
                ),
                workspace_status=workspace_status,
            )

        if task_spec.validation_profile == "artifact_only":
            artifact_summary = _validate_artifact_outputs(workspace=workspace, diff_paths=diff_paths)
            if not artifact_summary["passed"]:
                _stop_app_runtime()
                return HealerRunResult(
                    success=False,
                    failure_class="artifact_validation_failed",
                    failure_reason=str(artifact_summary.get("summary") or "Artifact validation failed."),
                    failure_fingerprint="",
                    proposer_output=proposer_output,
                    diff_paths=diff_paths,
                    diff_files=diff_files,
                    diff_lines=diff_lines,
                    test_summary=artifact_summary,
                    workspace_status=workspace_status,
                )
            test_summary = {
                "mode": "skipped_artifact_only",
                "failed_tests": 0,
                "targeted_tests": targeted_tests,
                "skipped": True,
                "language_detected": resolved_execution.language_detected,
                "language_effective": resolved_execution.language_effective,
                "docker_image_effective": resolved_execution.strategy.docker_image,
                "execution_root": resolved_execution.execution_root,
                "execution_root_source": resolved_execution.execution_root_source,
                "local_gate_policy": self.local_gate_policy,
                "artifact_validation": artifact_summary,
            }
        else:
            test_summary = self.validate_workspace(
                workspace,
                task_spec=task_spec,
                targeted_tests=targeted_tests,
            )
        if browser_evidence_requested and runtime_profile is not None and app_runtime_session is not None:
            browser_entry_url = task_spec.entry_url or runtime_profile.readiness_url or ""
            try:
                resolution_journey = self._browser_harness.capture_journey(
                    profile=runtime_profile,
                    entry_url=browser_entry_url,
                    repro_steps=parsed_repro_steps,
                    artifact_root=browser_artifact_root / "resolution",
                    phase="resolution",
                    expect_failure=False,
                    storage_state_path=runtime_storage_state_path,
                )
            except Exception as exc:
                test_summary = _annotate_test_summary_browser_artifacts(
                    _annotate_test_summary_runtime(
                        test_summary,
                        workspace_status=workspace_status,
                        task_spec=task_spec,
                    ),
                    artifact_bundle=browser_artifact_bundle,
                    artifact_links=browser_artifact_links,
                )
                _stop_app_runtime()
                return HealerRunResult(
                    success=False,
                    failure_class="browser_step_failed",
                    failure_reason=str(exc),
                    failure_fingerprint="",
                    proposer_output=proposer_output,
                    diff_paths=diff_paths,
                    diff_files=diff_files,
                    diff_lines=diff_lines,
                    test_summary=_with_workspace_status(
                        _annotate_browser_failure_family(
                            test_summary,
                            failure_class="browser_step_failed",
                            failure_reason=str(exc),
                        ),
                        workspace_status=workspace_status,
                        failure_fingerprint="",
                    ),
                    workspace_status=workspace_status,
                )
            browser_artifact_bundle = _browser_artifact_bundle(
                profile=runtime_profile,
                entry_url=browser_entry_url,
                session_root=str(browser_artifact_root),
                failure_journey=_browser_bundle_phase_result(browser_artifact_bundle, phase="failure"),
                resolution_journey=resolution_journey,
            )
            browser_artifact_links = _browser_artifact_links(browser_artifact_bundle)
            app_runtime_status["browser_profile"] = _browser_profile_summary(runtime_profile)
            app_runtime_status["artifacts_ready"] = _browser_artifacts_ready(browser_artifact_bundle)
            app_runtime_status["bundle_status"] = str(browser_artifact_bundle.get("status") or "")
            _annotate_app_runtime_status(workspace_status, app_runtime_status)
            if browser_evidence_requested and not _browser_artifacts_ready(browser_artifact_bundle):
                missing_artifacts = ", ".join(_browser_missing_artifacts(browser_artifact_bundle))
                test_summary = _annotate_test_summary_browser_artifacts(
                    _annotate_test_summary_runtime(
                        test_summary,
                        workspace_status=workspace_status,
                        task_spec=task_spec,
                    ),
                    artifact_bundle=browser_artifact_bundle,
                    artifact_links=browser_artifact_links,
                )
                _stop_app_runtime()
                return HealerRunResult(
                    success=False,
                    failure_class="artifacts_missing",
                    failure_reason=(
                        "Browser evidence is incomplete; required screenshots are missing"
                        + (f": {missing_artifacts}" if missing_artifacts else ".")
                    ),
                    failure_fingerprint="",
                    proposer_output=proposer_output,
                    diff_paths=diff_paths,
                    diff_files=diff_files,
                    diff_lines=diff_lines,
                    test_summary=_with_workspace_status(
                        _annotate_browser_failure_family(
                            test_summary,
                            failure_class="artifacts_missing",
                            failure_reason=(
                                "Browser evidence is incomplete; required screenshots are missing"
                                + (f": {missing_artifacts}" if missing_artifacts else ".")
                            ),
                        ),
                        workspace_status=workspace_status,
                        failure_fingerprint="",
                    ),
                    workspace_status=workspace_status,
                )
            if not resolution_journey.passed:
                failure_reason = str(resolution_journey.error or "").strip()
                if resolution_journey.failure_step:
                    if failure_reason:
                        failure_reason = f"{failure_reason} ({resolution_journey.failure_step})"
                    else:
                        failure_reason = (
                            "Browser journey failed after the fix "
                            f"at step '{resolution_journey.failure_step}'."
                        )
                if not failure_reason:
                    failure_reason = "Browser journey failed after the fix."
                test_summary = _annotate_test_summary_browser_artifacts(
                    _annotate_test_summary_runtime(
                        test_summary,
                        workspace_status=workspace_status,
                        task_spec=task_spec,
                    ),
                    artifact_bundle=browser_artifact_bundle,
                    artifact_links=browser_artifact_links,
                )
                _stop_app_runtime()
                return HealerRunResult(
                    success=False,
                    failure_class="browser_step_failed",
                    failure_reason=failure_reason,
                    failure_fingerprint="",
                    proposer_output=proposer_output,
                    diff_paths=diff_paths,
                    diff_files=diff_files,
                    diff_lines=diff_lines,
                    test_summary=_with_workspace_status(
                        _annotate_browser_failure_family(
                            test_summary,
                            failure_class="browser_step_failed",
                            failure_reason=failure_reason,
                        ),
                        workspace_status=workspace_status,
                        failure_fingerprint="",
                    ),
                    workspace_status=workspace_status,
                )
        test_summary = _annotate_test_summary_runtime(
            test_summary,
            workspace_status=workspace_status,
            task_spec=task_spec,
        )
        test_summary = _annotate_test_summary_browser_artifacts(
            test_summary,
            artifact_bundle=browser_artifact_bundle,
            artifact_links=browser_artifact_links,
        )
        test_summary = _with_workspace_status(
            test_summary,
            workspace_status=workspace_status,
            failure_fingerprint="",
        )
        post_validation_status = _workspace_status_summary(
            workspace,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            language=resolved_execution.language_effective,
            execution_root=resolved_execution.execution_root,
        )
        if post_validation_status["contamination_paths"]:
            workspace_status, cleaned_paths, contamination_reason = _stabilize_workspace_hygiene(
                workspace,
                issue_title=issue_title,
                issue_body=issue_body,
                task_spec=task_spec,
                language=resolved_execution.language_effective,
                execution_root=resolved_execution.execution_root,
                allow_cleanup=self.auto_clean_generated_artifacts and cleanup_cycles_used < self.max_generated_artifact_cleanup_cycles,
            )
            if app_runtime_status:
                _annotate_app_runtime_status(workspace_status, app_runtime_status)
            _annotate_completion_artifact_parser(
                workspace_status,
                mode=completion_parser_mode,
                confidence=completion_parser_confidence,
                source=completion_parser_source,
                reason=completion_parser_reason,
            )
            _annotate_app_server_recovery_status(workspace_status)
            if cleaned_paths:
                cleanup_cycles_used += 1
            workspace_status["cleanup_cycles_used"] = cleanup_cycles_used
            if contamination_reason:
                fingerprint = _generated_artifact_failure_fingerprint(
                    workspace_status.get("contamination_paths") or workspace_status.get("cleaned_paths") or [],
                    execution_root=resolved_execution.execution_root,
                )
                test_summary = _with_workspace_status(
                    test_summary,
                    workspace_status=workspace_status,
                    failure_fingerprint=fingerprint,
                )
                _stop_app_runtime()
                return HealerRunResult(
                    success=False,
                    failure_class="generated_artifact_contamination",
                    failure_reason=contamination_reason,
                    failure_fingerprint=fingerprint,
                    proposer_output=proposer_output,
                    diff_paths=diff_paths,
                    diff_files=diff_files,
                    diff_lines=diff_lines,
                    test_summary=test_summary,
                    workspace_status=workspace_status,
                )
            diff_paths = _changed_paths(workspace)
            diff_files, diff_lines = _diff_stats(workspace)
            if not diff_paths:
                _stop_app_runtime()
                return HealerRunResult(
                    success=False,
                    failure_class="no_workspace_change:connector_noop",
                    failure_reason="Proposer finished without producing any staged file changes.",
                    failure_fingerprint="",
                    proposer_output=proposer_output,
                    diff_paths=[],
                    diff_files=0,
                    diff_lines=0,
                    test_summary=_with_workspace_status(
                        {},
                        workspace_status=workspace_status,
                        failure_fingerprint="",
                    ),
                    workspace_status=workspace_status,
                )
            scope_violations = _scope_violation_paths(
                diff_paths,
                issue_title=issue_title,
                issue_body=issue_body,
                task_spec=task_spec,
            )
            if scope_violations:
                _stop_app_runtime()
                return HealerRunResult(
                    success=False,
                    failure_class="scope_violation",
                    failure_reason=_scope_violation_reason(scope_violations),
                    failure_fingerprint="",
                    proposer_output=proposer_output,
                    diff_paths=diff_paths,
                    diff_files=diff_files,
                    diff_lines=diff_lines,
                    test_summary=_with_workspace_status(
                        test_summary,
                        workspace_status=workspace_status,
                        failure_fingerprint="",
                    ),
                    workspace_status=workspace_status,
                )
            if task_spec.validation_profile == "artifact_only":
                artifact_summary = _validate_artifact_outputs(workspace=workspace, diff_paths=diff_paths)
                artifact_summary["workspace_hygiene_rerun"] = True
                test_summary = {
                    "mode": "skipped_artifact_only",
                    "failed_tests": 0,
                    "targeted_tests": targeted_tests,
                    "skipped": True,
                    "language_detected": resolved_execution.language_detected,
                    "language_effective": resolved_execution.language_effective,
                    "docker_image_effective": resolved_execution.strategy.docker_image,
                    "execution_root": resolved_execution.execution_root,
                    "execution_root_source": resolved_execution.execution_root_source,
                    "local_gate_policy": self.local_gate_policy,
                    "artifact_validation": artifact_summary,
                    "workspace_hygiene_rerun": True,
                }
                if not artifact_summary["passed"]:
                    _stop_app_runtime()
                    return HealerRunResult(
                        success=False,
                        failure_class="artifact_validation_failed",
                        failure_reason=str(artifact_summary.get("summary") or "Artifact validation failed."),
                        failure_fingerprint="",
                        proposer_output=proposer_output,
                        diff_paths=diff_paths,
                        diff_files=diff_files,
                        diff_lines=diff_lines,
                        test_summary=_with_workspace_status(
                            test_summary,
                            workspace_status=workspace_status,
                            failure_fingerprint="",
                        ),
                        workspace_status=workspace_status,
                    )
            else:
                test_summary = self.validate_workspace(
                    workspace,
                    task_spec=task_spec,
                    targeted_tests=targeted_tests,
                )
                test_summary["workspace_hygiene_rerun"] = True
            test_summary = _annotate_test_summary_runtime(
                test_summary,
                workspace_status=workspace_status,
                task_spec=task_spec,
            )
            final_workspace_status = _workspace_status_summary(
                workspace,
                issue_title=issue_title,
                issue_body=issue_body,
                task_spec=task_spec,
                language=resolved_execution.language_effective,
                execution_root=resolved_execution.execution_root,
            )
            if final_workspace_status["contamination_paths"]:
                final_workspace_status["contamination_paths"] = [
                    path
                    for path in final_workspace_status["contamination_paths"]
                    if not (
                        _is_tolerated_runtime_artifact(path, language=resolved_execution.language_effective)
                        and path not in final_workspace_status.get("staged_paths", [])
                    )
                ]
            if final_workspace_status["contamination_paths"]:
                final_workspace_status["cleanup_performed"] = True
                final_workspace_status["cleaned_paths"] = list(workspace_status.get("cleaned_paths") or [])
                final_workspace_status["cleanup_cycles_used"] = cleanup_cycles_used
                _annotate_completion_artifact_parser(
                    final_workspace_status,
                    mode=completion_parser_mode,
                    confidence=completion_parser_confidence,
                    source=completion_parser_source,
                    reason=completion_parser_reason,
                )
                _annotate_app_server_recovery_status(final_workspace_status)
                if app_runtime_status:
                    _annotate_app_runtime_status(final_workspace_status, app_runtime_status)
                fingerprint = _generated_artifact_failure_fingerprint(
                    final_workspace_status["contamination_paths"],
                    execution_root=resolved_execution.execution_root,
                )
                test_summary = _with_workspace_status(
                    test_summary,
                    workspace_status=final_workspace_status,
                    failure_fingerprint=fingerprint,
                )
                _stop_app_runtime()
                return HealerRunResult(
                    success=False,
                    failure_class="generated_artifact_contamination",
                    failure_reason=_generated_artifact_contamination_reason(
                        list(final_workspace_status["contamination_paths"]),
                        execution_root=resolved_execution.execution_root,
                    ),
                    failure_fingerprint=fingerprint,
                    proposer_output=proposer_output,
                    diff_paths=diff_paths,
                    diff_files=diff_files,
                    diff_lines=diff_lines,
                    test_summary=test_summary,
                    workspace_status=final_workspace_status,
                )
            test_summary = _with_workspace_status(
                test_summary,
                workspace_status=workspace_status,
                failure_fingerprint="",
            )
        _stop_app_runtime()
        if app_runtime_status:
            workspace_status, cleaned_paths, contamination_reason = _stabilize_workspace_hygiene(
                workspace,
                issue_title=issue_title,
                issue_body=issue_body,
                task_spec=task_spec,
                language=resolved_execution.language_effective,
                execution_root=resolved_execution.execution_root,
                allow_cleanup=self.auto_clean_generated_artifacts and cleanup_cycles_used < self.max_generated_artifact_cleanup_cycles,
            )
            _annotate_app_runtime_status(workspace_status, app_runtime_status)
            _annotate_completion_artifact_parser(
                workspace_status,
                mode=completion_parser_mode,
                confidence=completion_parser_confidence,
                source=completion_parser_source,
                reason=completion_parser_reason,
            )
            _annotate_app_server_recovery_status(workspace_status)
            if cleaned_paths:
                cleanup_cycles_used += 1
            workspace_status["cleanup_cycles_used"] = cleanup_cycles_used
            if contamination_reason:
                fingerprint = _generated_artifact_failure_fingerprint(
                    workspace_status.get("contamination_paths") or workspace_status.get("cleaned_paths") or [],
                    execution_root=resolved_execution.execution_root,
                )
                test_summary = _with_workspace_status(
                    test_summary,
                    workspace_status=workspace_status,
                    failure_fingerprint=fingerprint,
                )
                return HealerRunResult(
                    success=False,
                    failure_class="generated_artifact_contamination",
                    failure_reason=contamination_reason,
                    failure_fingerprint=fingerprint,
                    proposer_output=proposer_output,
                    diff_paths=diff_paths,
                    diff_files=diff_files,
                    diff_lines=diff_lines,
                    test_summary=test_summary,
                    workspace_status=workspace_status,
                )
        _annotate_completion_artifact_parser(
            workspace_status,
            mode=completion_parser_mode,
            confidence=completion_parser_confidence,
            source=completion_parser_source,
            reason=completion_parser_reason,
        )
        _annotate_app_server_recovery_status(workspace_status)
        failed_tests = int(test_summary.get("failed_tests", 0))
        if failed_tests > max_failed_tests_allowed:
            test_failure_class = str(test_summary.get("failure_class") or "").strip()
            test_failure_reason = str(test_summary.get("failure_reason") or "").strip()
            return HealerRunResult(
                success=False,
                failure_class=test_failure_class or "tests_failed",
                failure_reason=(
                    test_failure_reason
                    or f"Failed tests={failed_tests} exceeds cap={max_failed_tests_allowed}"
                ),
                failure_fingerprint="",
                proposer_output=proposer_output,
                diff_paths=diff_paths,
                diff_files=diff_files,
                diff_lines=diff_lines,
                test_summary=test_summary,
                workspace_status=workspace_status,
            )

        return HealerRunResult(
            success=True,
            failure_class="",
            failure_reason="",
            failure_fingerprint="",
            proposer_output=proposer_output,
            diff_paths=diff_paths,
            diff_files=diff_files,
            diff_lines=diff_lines,
            test_summary=test_summary,
            workspace_status=workspace_status,
        )

    def resolve_execution(self, *, workspace: Path, task_spec: HealerTaskSpec) -> ResolvedExecution:
        execution_root, root_source = _resolve_execution_root(workspace=workspace, task_spec=task_spec)
        execution_path = workspace / execution_root if execution_root else workspace
        if not execution_path.exists() or not execution_path.is_dir():
            execution_root = ""
            root_source = "repo"
            execution_path = workspace
        execution_detection = detect_language_details(execution_path)
        repo_detection = detect_language_details(workspace)
        issue_language = task_spec.language if task_spec.language else ""
        config_override_allowed = not issue_language
        ensure_supported_language(issue_language, source="issue instructions")
        if config_override_allowed:
            ensure_supported_language(self._language, source="repo config")
        detected_language = ""
        if execution_detection.language and execution_detection.language != "unknown":
            detected_language = execution_detection.language
        elif repo_detection.language and repo_detection.language != "unknown":
            detected_language = repo_detection.language
        effective_language = (
            issue_language
            or (self._language if config_override_allowed else "")
            or detected_language
        )
        if is_removed_language(effective_language):
            raise UnsupportedLanguageError(
                f"Unsupported language '{effective_language}'. "
                "Flow Healer does not support java_maven; use java_gradle for Java reference targets."
            )
        if effective_language == "unknown":
            effective_language = ""
        strategy = get_strategy(
            effective_language,
            framework=task_spec.framework,
            docker_image=self._docker_image if config_override_allowed else "",
            test_command=self._test_command if config_override_allowed else "",
            install_command=self._install_command if config_override_allowed else "",
        )
        return ResolvedExecution(
            language_detected=detected_language,
            language_effective=effective_language,
            execution_root=execution_root,
            execution_root_source=root_source,
            execution_path=execution_path,
            strategy=strategy,
        )

    def validate_workspace(
        self,
        workspace: Path,
        *,
        task_spec: HealerTaskSpec,
        targeted_tests: list[str],
        timeout_seconds: int | None = None,
        mode: str | None = None,
        local_gate_policy: str | None = None,
    ) -> dict[str, Any]:
        resolved_execution = self.resolve_execution(workspace=workspace, task_spec=task_spec)
        return _run_test_gates(
            workspace,
            targeted_tests=targeted_tests,
            timeout_seconds=timeout_seconds or self.timeout_seconds,
            mode=mode or self.test_gate_mode,
            resolved_execution=resolved_execution,
            validation_commands=task_spec.validation_commands,
            task_spec=task_spec,
            local_gate_policy=local_gate_policy or self.local_gate_policy,
        )

    def evaluate_existing_workspace(
        self,
        *,
        workspace: Path,
        issue_id: str,
        issue_title: str,
        issue_body: str,
        task_spec: HealerTaskSpec,
        targeted_tests: list[str],
        max_diff_files: int,
        max_diff_lines: int,
        max_failed_tests_allowed: int,
        proposer_output: str = "",
        workspace_status: dict[str, Any] | None = None,
    ) -> HealerRunResult:
        self._bind_connector_workspace(workspace)
        resolved_execution = self.resolve_execution(workspace=workspace, task_spec=task_spec)
        current_workspace_status = dict(
            workspace_status or _empty_workspace_status(execution_root=resolved_execution.execution_root)
        )
        current_workspace_status.setdefault("execution_root", resolved_execution.execution_root)
        current_workspace_status.setdefault("execution_root_source", resolved_execution.execution_root_source)
        current_workspace_status.setdefault("app_server_forced_serialized_recovery_attempted", False)
        current_workspace_status.setdefault("app_server_forced_serialized_recovery_succeeded", False)
        current_workspace_status.setdefault("app_server_exec_failover_attempted", False)
        current_workspace_status.setdefault("app_server_exec_failover_succeeded", False)
        current_workspace_status.setdefault("completion_artifact_parser_mode", "not_attempted")
        current_workspace_status.setdefault("completion_artifact_parser_confidence", 0.0)
        current_workspace_status.setdefault("completion_artifact_parser_source", "")
        current_workspace_status.setdefault("completion_artifact_parser_reason", "")

        if not _stage_workspace_changes(
            workspace,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            language=resolved_execution.language_effective,
        ):
            return HealerRunResult(
                success=False,
                failure_class="no_workspace_change:swarm_repair_noop",
                failure_reason="Swarm repair executor finished without producing staged workspace changes.",
                failure_fingerprint=_execution_contract_failure_fingerprint(
                    failure_class="no_workspace_change:swarm_repair_noop",
                    connector=self.connector,
                    task_spec=task_spec,
                ),
                proposer_output=proposer_output,
                diff_paths=[],
                diff_files=0,
                diff_lines=0,
                test_summary=_with_workspace_status(
                    {},
                    workspace_status=current_workspace_status,
                    failure_fingerprint="",
                ),
                workspace_status=current_workspace_status,
            )

        diff_paths = _changed_paths(workspace)
        diff_files, diff_lines = _diff_stats(workspace)
        if not diff_paths:
            return HealerRunResult(
                success=False,
                failure_class="no_workspace_change:swarm_repair_noop",
                failure_reason="Swarm repair executor finished without producing staged workspace changes.",
                failure_fingerprint=_execution_contract_failure_fingerprint(
                    failure_class="no_workspace_change:swarm_repair_noop",
                    connector=self.connector,
                    task_spec=task_spec,
                ),
                proposer_output=proposer_output,
                diff_paths=[],
                diff_files=0,
                diff_lines=0,
                test_summary=_with_workspace_status(
                    {},
                    workspace_status=current_workspace_status,
                    failure_fingerprint="",
                ),
                workspace_status=current_workspace_status,
            )
        if _requires_non_artifact_diff(task_spec=task_spec) and not _has_non_artifact_diff(diff_paths):
            return HealerRunResult(
                success=False,
                failure_class="no_code_diff",
                failure_reason="Code-change task produced only docs/artifact edits.",
                failure_fingerprint="",
                proposer_output=proposer_output,
                diff_paths=diff_paths,
                diff_files=diff_files,
                diff_lines=diff_lines,
                test_summary={},
                workspace_status=current_workspace_status,
            )
        scope_violations = _scope_violation_paths(
            diff_paths,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
        )
        if scope_violations:
            return HealerRunResult(
                success=False,
                failure_class="scope_violation",
                failure_reason=_scope_violation_reason(scope_violations),
                failure_fingerprint="",
                proposer_output=proposer_output,
                diff_paths=diff_paths,
                diff_files=diff_files,
                diff_lines=diff_lines,
                test_summary={},
                workspace_status=current_workspace_status,
            )
        if diff_files > max_diff_files or diff_lines > max_diff_lines:
            return HealerRunResult(
                success=False,
                failure_class="diff_limit_exceeded",
                failure_reason=f"Diff too large: files={diff_files}/{max_diff_files}, lines={diff_lines}/{max_diff_lines}",
                failure_fingerprint="",
                proposer_output=proposer_output,
                diff_paths=diff_paths,
                diff_files=diff_files,
                diff_lines=diff_lines,
                test_summary={},
                workspace_status=current_workspace_status,
            )

        if task_spec.validation_profile == "artifact_only":
            artifact_summary = _validate_artifact_outputs(workspace=workspace, diff_paths=diff_paths)
            if not artifact_summary["passed"]:
                return HealerRunResult(
                    success=False,
                    failure_class="artifact_validation_failed",
                    failure_reason=str(artifact_summary.get("summary") or "Artifact validation failed."),
                    failure_fingerprint="",
                    proposer_output=proposer_output,
                    diff_paths=diff_paths,
                    diff_files=diff_files,
                    diff_lines=diff_lines,
                    test_summary=artifact_summary,
                    workspace_status=current_workspace_status,
                )
            test_summary = {
                "mode": "skipped_artifact_only",
                "failed_tests": 0,
                "targeted_tests": targeted_tests,
                "skipped": True,
                "language_detected": resolved_execution.language_detected,
                "language_effective": resolved_execution.language_effective,
                "docker_image_effective": resolved_execution.strategy.docker_image,
                "execution_root": resolved_execution.execution_root,
                "execution_root_source": resolved_execution.execution_root_source,
                "local_gate_policy": self.local_gate_policy,
                "artifact_validation": artifact_summary,
            }
        else:
            test_summary = self.validate_workspace(
                workspace,
                task_spec=task_spec,
                targeted_tests=targeted_tests,
            )
        test_summary = _with_workspace_status(
            test_summary,
            workspace_status=current_workspace_status,
            failure_fingerprint="",
        )

        post_validation_status = _workspace_status_summary(
            workspace,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            language=resolved_execution.language_effective,
            execution_root=resolved_execution.execution_root,
        )
        if post_validation_status["contamination_paths"]:
            stabilized_status, cleaned_paths, contamination_reason = _stabilize_workspace_hygiene(
                workspace,
                issue_title=issue_title,
                issue_body=issue_body,
                task_spec=task_spec,
                language=resolved_execution.language_effective,
                execution_root=resolved_execution.execution_root,
                allow_cleanup=self.auto_clean_generated_artifacts,
            )
            stabilized_status.setdefault("swarm_strategy", current_workspace_status.get("swarm_strategy", "repair"))
            stabilized_status.setdefault("swarm_summary", current_workspace_status.get("swarm_summary", ""))
            if cleaned_paths:
                stabilized_status["cleanup_cycles_used"] = 1
            if contamination_reason:
                fingerprint = _generated_artifact_failure_fingerprint(
                    stabilized_status.get("contamination_paths") or stabilized_status.get("cleaned_paths") or [],
                    execution_root=resolved_execution.execution_root,
                )
                test_summary = _with_workspace_status(
                    test_summary,
                    workspace_status=stabilized_status,
                    failure_fingerprint=fingerprint,
                )
                return HealerRunResult(
                    success=False,
                    failure_class="generated_artifact_contamination",
                    failure_reason=contamination_reason,
                    failure_fingerprint=fingerprint,
                    proposer_output=proposer_output,
                    diff_paths=diff_paths,
                    diff_files=diff_files,
                    diff_lines=diff_lines,
                    test_summary=test_summary,
                    workspace_status=stabilized_status,
                )
            diff_paths = _changed_paths(workspace)
            diff_files, diff_lines = _diff_stats(workspace)
            if not diff_paths:
                return HealerRunResult(
                    success=False,
                    failure_class="no_workspace_change:swarm_repair_noop",
                    failure_reason="Swarm repair executor finished without producing staged workspace changes.",
                    failure_fingerprint=_execution_contract_failure_fingerprint(
                        failure_class="no_workspace_change:swarm_repair_noop",
                        connector=self.connector,
                        task_spec=task_spec,
                    ),
                    proposer_output=proposer_output,
                    diff_paths=[],
                    diff_files=0,
                    diff_lines=0,
                    test_summary=_with_workspace_status(
                        {},
                        workspace_status=stabilized_status,
                        failure_fingerprint="",
                    ),
                    workspace_status=stabilized_status,
                )
            scope_violations = _scope_violation_paths(
                diff_paths,
                issue_title=issue_title,
                issue_body=issue_body,
                task_spec=task_spec,
            )
            if scope_violations:
                return HealerRunResult(
                    success=False,
                    failure_class="scope_violation",
                    failure_reason=_scope_violation_reason(scope_violations),
                    failure_fingerprint="",
                    proposer_output=proposer_output,
                    diff_paths=diff_paths,
                    diff_files=diff_files,
                    diff_lines=diff_lines,
                    test_summary=_with_workspace_status(
                        test_summary,
                        workspace_status=stabilized_status,
                        failure_fingerprint="",
                    ),
                    workspace_status=stabilized_status,
                )
            if task_spec.validation_profile == "artifact_only":
                artifact_summary = _validate_artifact_outputs(workspace=workspace, diff_paths=diff_paths)
                artifact_summary["workspace_hygiene_rerun"] = True
                test_summary = {
                    "mode": "skipped_artifact_only",
                    "failed_tests": 0,
                    "targeted_tests": targeted_tests,
                    "skipped": True,
                    "language_detected": resolved_execution.language_detected,
                    "language_effective": resolved_execution.language_effective,
                    "docker_image_effective": resolved_execution.strategy.docker_image,
                    "execution_root": resolved_execution.execution_root,
                    "execution_root_source": resolved_execution.execution_root_source,
                    "local_gate_policy": self.local_gate_policy,
                    "artifact_validation": artifact_summary,
                    "workspace_hygiene_rerun": True,
                }
                if not artifact_summary["passed"]:
                    return HealerRunResult(
                        success=False,
                        failure_class="artifact_validation_failed",
                        failure_reason=str(artifact_summary.get("summary") or "Artifact validation failed."),
                        failure_fingerprint="",
                        proposer_output=proposer_output,
                        diff_paths=diff_paths,
                        diff_files=diff_files,
                        diff_lines=diff_lines,
                        test_summary=_with_workspace_status(
                            test_summary,
                            workspace_status=stabilized_status,
                            failure_fingerprint="",
                        ),
                        workspace_status=stabilized_status,
                    )
            else:
                test_summary = self.validate_workspace(
                    workspace,
                    task_spec=task_spec,
                    targeted_tests=targeted_tests,
                )
                test_summary["workspace_hygiene_rerun"] = True
            final_workspace_status = _workspace_status_summary(
                workspace,
                issue_title=issue_title,
                issue_body=issue_body,
                task_spec=task_spec,
                language=resolved_execution.language_effective,
                execution_root=resolved_execution.execution_root,
            )
            final_workspace_status.setdefault("swarm_strategy", current_workspace_status.get("swarm_strategy", "repair"))
            final_workspace_status.setdefault("swarm_summary", current_workspace_status.get("swarm_summary", ""))
            if final_workspace_status["contamination_paths"]:
                final_workspace_status["contamination_paths"] = [
                    path
                    for path in final_workspace_status["contamination_paths"]
                    if not (
                        _is_tolerated_runtime_artifact(path, language=resolved_execution.language_effective)
                        and path not in final_workspace_status.get("staged_paths", [])
                    )
                ]
            if final_workspace_status["contamination_paths"]:
                final_workspace_status["cleanup_performed"] = True
                final_workspace_status["cleaned_paths"] = list(stabilized_status.get("cleaned_paths") or [])
                final_workspace_status["cleanup_cycles_used"] = int(stabilized_status.get("cleanup_cycles_used") or 1)
                fingerprint = _generated_artifact_failure_fingerprint(
                    final_workspace_status["contamination_paths"],
                    execution_root=resolved_execution.execution_root,
                )
                test_summary = _with_workspace_status(
                    test_summary,
                    workspace_status=final_workspace_status,
                    failure_fingerprint=fingerprint,
                )
                return HealerRunResult(
                    success=False,
                    failure_class="generated_artifact_contamination",
                    failure_reason=_generated_artifact_contamination_reason(
                        list(final_workspace_status["contamination_paths"]),
                        execution_root=resolved_execution.execution_root,
                    ),
                    failure_fingerprint=fingerprint,
                    proposer_output=proposer_output,
                    diff_paths=diff_paths,
                    diff_files=diff_files,
                    diff_lines=diff_lines,
                    test_summary=test_summary,
                    workspace_status=final_workspace_status,
                )
            current_workspace_status = final_workspace_status
            test_summary = _with_workspace_status(
                test_summary,
                workspace_status=current_workspace_status,
                failure_fingerprint="",
            )

        failed_tests = int(test_summary.get("failed_tests", 0) or 0)
        if failed_tests > max_failed_tests_allowed:
            test_failure_class = str(test_summary.get("failure_class") or "").strip()
            test_failure_reason = str(test_summary.get("failure_reason") or "").strip()
            return HealerRunResult(
                success=False,
                failure_class=test_failure_class or "tests_failed",
                failure_reason=(
                    test_failure_reason
                    or f"Failed tests={failed_tests} exceeds cap={max_failed_tests_allowed}"
                ),
                failure_fingerprint=str(test_summary.get("failure_fingerprint") or ""),
                proposer_output=proposer_output,
                diff_paths=diff_paths,
                diff_files=diff_files,
                diff_lines=diff_lines,
                test_summary=test_summary,
                workspace_status=current_workspace_status,
            )

        return HealerRunResult(
            success=True,
            failure_class="",
            failure_reason="",
            failure_fingerprint=str(test_summary.get("failure_fingerprint") or ""),
            proposer_output=proposer_output,
            diff_paths=diff_paths,
            diff_files=diff_files,
            diff_lines=diff_lines,
            test_summary=test_summary,
            workspace_status=current_workspace_status,
        )

    def _bind_connector_workspace(self, workspace: Path) -> None:
        # CodexCliConnector executes with cwd=self.workspace; update it per issue
        # so direct edits land in the active healer worktree, not repo root.
        if hasattr(self.connector, "workspace"):
            try:
                setattr(self.connector, "workspace", workspace)
            except Exception:
                pass


def _resolve_execution_root(*, workspace: Path, task_spec: HealerTaskSpec) -> tuple[str, str]:
    hinted = _safe_rel_path(task_spec.execution_root)
    if hinted and (workspace / hinted).is_dir():
        return hinted.as_posix(), "issue"

    candidates: list[str] = []
    for raw_target in task_spec.output_targets:
        target = _safe_rel_path(raw_target)
        if not target:
            continue
        candidate = _infer_execution_root_from_target(target)
        if candidate and (workspace / candidate).is_dir():
            candidates.append(candidate)
    unique_candidates = sorted(set(candidates))
    if len(unique_candidates) == 1:
        return unique_candidates[0], "output_target"
    return "", "repo"


def _infer_execution_root_from_target(target: str) -> str:
    parts = PurePosixPath(target).parts
    if len(parts) >= 2 and parts[0] == "e2e-smoke":
        return PurePosixPath(parts[0], parts[1]).as_posix()
    return ""


def _extract_diff_block(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"```diff\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip() + "\n"
    if text.lstrip().startswith("diff --git "):
        return text.strip() + "\n"
    return ""


def _changed_paths(workspace: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(workspace), "diff", "--name-only", "--cached"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]


def _enforces_exact_output_targets(task_spec: HealerTaskSpec) -> bool:
    if not task_spec.output_targets:
        return False
    return task_spec.validation_profile != "artifact_only"


def _scope_violation_paths(
    diff_paths: list[str],
    *,
    issue_title: str,
    issue_body: str,
    task_spec: HealerTaskSpec,
) -> list[str]:
    if not _enforces_exact_output_targets(task_spec):
        return []
    unexpected: list[str] = []
    for path in diff_paths:
        normalized = str(path or "").strip().lstrip("./")
        if not normalized:
            continue
        if _is_explicit_output_target(normalized, task_spec):
            continue
        if _issue_allows_lockfile_change(
            normalized,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
        ):
            continue
        unexpected.append(normalized)
    return sorted(set(unexpected))


def _scope_violation_reason(paths: list[str]) -> str:
    preview = ", ".join(paths[:5])
    if len(paths) > 5:
        preview += ", ..."
    return (
        "Tracked changes escaped the exact issue output targets: "
        f"{preview}. Keep edits limited to the declared output files."
    )


def _diff_stats(workspace: Path) -> tuple[int, int]:
    proc = subprocess.run(
        ["git", "-C", str(workspace), "diff", "--cached", "--numstat"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return 0, 0
    files = 0
    lines = 0
    for line in (proc.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        files += 1
        try:
            adds = int(parts[0]) if parts[0].isdigit() else 0
            dels = int(parts[1]) if parts[1].isdigit() else 0
            lines += adds + dels
        except Exception:
            continue
    return files, lines


def _run_test_gates(
    workspace: Path,
    *,
    targeted_tests: list[str],
    timeout_seconds: int,
    mode: str,
    resolved_execution: ResolvedExecution | None = None,
    validation_commands: tuple[str, ...] = (),
    task_spec: HealerTaskSpec | None = None,
    local_gate_policy: str = "auto",
) -> dict[str, Any]:
    if resolved_execution is None:
        resolved_execution = ResolvedExecution(
            language_detected="unknown",
            language_effective="unknown",
            execution_root="",
            execution_root_source="repo",
            execution_path=workspace,
            strategy=get_strategy("unknown"),
        )
    summary: dict[str, Any] = {
        "mode": mode,
        "failed_tests": 0,
        "targeted_tests": targeted_tests,
        "language_detected": resolved_execution.language_detected,
        "language_effective": resolved_execution.language_effective,
        "docker_image_effective": resolved_execution.strategy.docker_image,
        "execution_root": resolved_execution.execution_root,
        "execution_root_source": resolved_execution.execution_root_source,
        "local_gate_policy": local_gate_policy,
    }
    runners = _gate_runners_for_mode(mode)
    strategy = resolved_execution.strategy
    execution_path = resolved_execution.execution_path
    normalized_validation_result = _normalize_explicit_validation_commands(
        commands=tuple(str(command).strip() for command in validation_commands if str(command).strip()),
        execution_root=resolved_execution.execution_root,
    )
    if normalized_validation_result.rejection_reason:
        summary["failed_tests"] = 1
        summary["validation_commands"] = list(normalized_validation_result.normalized_commands)
        summary["failure_class"] = "validation_command_invalid"
        summary["failure_reason"] = normalized_validation_result.rejection_reason
        summary["local_full_exit_code"] = 1
        summary["local_full_output_tail"] = normalized_validation_result.rejection_reason
        summary["local_full_status"] = "failed"
        summary["local_full_reason"] = "validation_command_invalid"
        summary["local_full_runner"] = "explicit_validation_commands"
        summary["docker_full_exit_code"] = 0
        summary["docker_full_output_tail"] = "(docker full gate skipped: invalid explicit validation command)"
        summary["docker_full_status"] = "skipped"
        summary["docker_full_reason"] = "validation_command_invalid"
        return _finalize_validation_summary(summary, targeted_requested=bool(targeted_tests))
    explicit_validation_commands = _expand_issue_scoped_validation_commands(
        commands=normalized_validation_result.normalized_commands,
        task_spec=task_spec,
    )
    if (
        not explicit_validation_commands
        and not strategy.local_test_cmd
        and not strategy.docker_test_cmd
    ):
        reason = (
            "Language could not be resolved safely from repo markers. "
            "Provide an explicit issue language or validation command."
        )
        summary["failed_tests"] = 1
        summary["failure_class"] = "language_unresolved"
        summary["failure_reason"] = reason
        summary["local_full_exit_code"] = 1
        summary["local_full_output_tail"] = reason
        summary["local_full_status"] = "failed"
        summary["local_full_reason"] = "language_unresolved"
        summary["docker_full_exit_code"] = 0
        summary["docker_full_output_tail"] = "(docker full gate skipped: language unresolved)"
        summary["docker_full_status"] = "skipped"
        summary["docker_full_reason"] = "language_unresolved"
        return _finalize_validation_summary(summary, targeted_requested=bool(targeted_tests))

    if targeted_tests:
        targeted_cmd = _compose_targeted_command(strategy, targeted_tests)
        for runner_name, runner in runners:
            if runner_name == "docker" and not strategy.supports_docker:
                targeted = _unsupported_docker_gate_result(mode=mode)
            else:
                targeted = _invoke_gate_runner(
                    runner,
                    execution_path,
                    targeted_cmd,
                    timeout_seconds,
                    strategy=strategy,
                    local_gate_policy=local_gate_policy,
                )
            targeted_status = str(
                targeted.get("gate_status") or ("passed" if int(targeted.get("exit_code", 1)) == 0 else "failed")
            )
            if mode == "local_only" and runner_name == "local" and targeted_status == "skipped":
                targeted_status = "failed"
                if not targeted.get("gate_reason"):
                    targeted["gate_reason"] = "local_only_requires_local_gate"
            targeted_status = _maybe_soft_fail_docker_infra_gate(
                mode=mode,
                runner_name=runner_name,
                phase="targeted",
                summary=summary,
                gate_result=targeted,
                gate_status=targeted_status,
            )
            summary[f"{runner_name}_targeted_exit_code"] = targeted["exit_code"]
            summary[f"{runner_name}_targeted_output_tail"] = targeted["output_tail"]
            summary[f"{runner_name}_targeted_status"] = targeted_status
            if targeted.get("gate_reason"):
                summary[f"{runner_name}_targeted_reason"] = targeted["gate_reason"]
            if targeted_status == "failed":
                summary["failed_tests"] += 1

    if _should_use_explicit_validation_commands(strategy=strategy, validation_commands=explicit_validation_commands):
        full = _run_explicit_validation_commands(
            execution_path,
            explicit_validation_commands,
            timeout_seconds,
        )
        full_status = str(full.get("gate_status") or ("passed" if int(full.get("exit_code", 1)) == 0 else "failed"))
        if mode == "local_only" and full_status == "skipped":
            full_status = "failed"
            if not full.get("gate_reason"):
                full["gate_reason"] = "local_only_requires_local_gate"
        summary["local_full_exit_code"] = full["exit_code"]
        summary["local_full_output_tail"] = full["output_tail"]
        summary["local_full_status"] = full_status
        if full.get("gate_reason"):
            summary["local_full_reason"] = full["gate_reason"]
        summary["local_full_runner"] = "explicit_validation_commands"
        summary["validation_commands"] = list(explicit_validation_commands)
        docker_full = {
            "exit_code": 0,
            "output_tail": "(docker full gate skipped: using issue validation commands)",
            "gate_status": "skipped",
            "gate_reason": "explicit_validation_commands",
        }
        if mode == "docker_only":
            docker_full = {
                "exit_code": 0,
                "output_tail": "(docker-only mode satisfied by issue validation commands)",
                "gate_status": "passed",
                "gate_reason": "explicit_validation_commands",
            }
        summary["docker_full_exit_code"] = docker_full["exit_code"]
        summary["docker_full_output_tail"] = docker_full["output_tail"]
        summary["docker_full_status"] = docker_full["gate_status"]
        if docker_full.get("gate_reason"):
            summary["docker_full_reason"] = docker_full["gate_reason"]
        if full_status == "failed":
            summary["failed_tests"] += 1
        return _finalize_validation_summary(summary, targeted_requested=bool(targeted_tests))

    full_cmd = list(strategy.docker_test_cmd)
    for runner_name, runner in runners:
        if runner_name == "docker" and not strategy.supports_docker:
            full = _unsupported_docker_gate_result(mode=mode)
        else:
            full = _invoke_gate_runner(
                runner,
                execution_path,
                full_cmd,
                timeout_seconds,
                strategy=strategy,
                local_gate_policy=local_gate_policy,
            )
        full_status = str(full.get("gate_status") or ("passed" if int(full.get("exit_code", 1)) == 0 else "failed"))
        if mode == "local_only" and runner_name == "local" and full_status == "skipped":
            full_status = "failed"
            if not full.get("gate_reason"):
                full["gate_reason"] = "local_only_requires_local_gate"
        full_status = _maybe_soft_fail_docker_infra_gate(
            mode=mode,
            runner_name=runner_name,
            phase="full",
            summary=summary,
            gate_result=full,
            gate_status=full_status,
        )
        summary[f"{runner_name}_full_exit_code"] = full["exit_code"]
        summary[f"{runner_name}_full_output_tail"] = full["output_tail"]
        summary[f"{runner_name}_full_status"] = full_status
        if full.get("gate_reason"):
            summary[f"{runner_name}_full_reason"] = full["gate_reason"]
        if full_status == "failed":
            summary["failed_tests"] += 1
    return _finalize_validation_summary(summary, targeted_requested=bool(targeted_tests))


def _finalize_validation_summary(summary: dict[str, Any], *, targeted_requested: bool) -> dict[str, Any]:
    targeted_statuses = [
        str(summary[key]).strip().lower()
        for key in ("local_targeted_status", "docker_targeted_status")
        if key in summary
    ]
    full_statuses = [
        str(summary[key]).strip().lower()
        for key in ("local_full_status", "docker_full_status")
        if key in summary
    ]
    fast_pass = bool(targeted_requested and targeted_statuses and all(status != "failed" for status in targeted_statuses))
    full_pass = bool(full_statuses and all(status != "failed" for status in full_statuses))
    promotion_ready = bool(full_pass and (not targeted_requested or fast_pass))
    summary["validation_lane"] = "fast_then_full" if targeted_requested else "full_only"
    summary["promotion_state"] = "promotion_ready" if promotion_ready else "merge_blocked"
    summary["phase_states"] = {
        "fast_pass": fast_pass,
        "full_pass": full_pass,
        "promotion_ready": promotion_ready,
        "merge_blocked": not promotion_ready,
    }
    return summary


def _run_explicit_validation_commands(
    workspace: Path,
    commands: tuple[str, ...],
    timeout_seconds: int,
) -> dict[str, Any]:
    env = os.environ.copy()
    bundle_bootstrap_required = any(_is_bundle_exec_rspec_command(command) for command in commands)
    if bundle_bootstrap_required:
        _configure_bundle_environment(env)
    output_chunks: list[str] = []
    bundle_bootstrap_done = False
    for command in commands:
        if bundle_bootstrap_required and not bundle_bootstrap_done:
            bootstrap_result = _bootstrap_bundle_runtime(
                workspace=workspace,
                env=env,
                timeout_seconds=timeout_seconds,
                output_chunks=output_chunks,
            )
            bundle_bootstrap_done = True
            if bootstrap_result is not None:
                return bootstrap_result
        output_chunks.append(f"$ {command}")
        try:
            proc = subprocess.run(
                ["/bin/zsh", "-lc", command],
                cwd=str(workspace),
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=max(30, timeout_seconds),
            )
        except FileNotFoundError:
            return {
                "exit_code": 127,
                "output_tail": "(/bin/zsh unavailable for explicit validation commands)",
                "gate_status": "failed",
                "gate_reason": "tool_missing",
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": 124,
                "output_tail": "\n".join(output_chunks)[-2000:],
                "gate_status": "failed",
                "gate_reason": "timeout",
            }

        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        if output:
            output_chunks.append(output)
        if int(proc.returncode) != 0:
            fallback_command = _bundle_exec_rspec_fallback_command(command)
            if fallback_command and _looks_like_bundle_exec_rspec_resolution_failure(output):
                output_chunks.append(
                    "(bundle exec rspec could not resolve executable; retrying via ruby entrypoint fallback)"
                )
                output_chunks.append(f"$ {fallback_command}")
                try:
                    fallback_proc = subprocess.run(
                        ["/bin/zsh", "-lc", fallback_command],
                        cwd=str(workspace),
                        env=env,
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=max(30, timeout_seconds),
                    )
                except FileNotFoundError:
                    return {
                        "exit_code": 127,
                        "output_tail": "(/bin/zsh unavailable for explicit validation commands)",
                        "gate_status": "failed",
                        "gate_reason": "tool_missing",
                    }
                except subprocess.TimeoutExpired:
                    return {
                        "exit_code": 124,
                        "output_tail": "\n".join(output_chunks)[-2000:],
                        "gate_status": "failed",
                        "gate_reason": "timeout",
                    }
                fallback_output = ((fallback_proc.stdout or "") + "\n" + (fallback_proc.stderr or "")).strip()
                if fallback_output:
                    output_chunks.append(fallback_output)
                if int(fallback_proc.returncode) == 0:
                    continue
            return {
                "exit_code": int(proc.returncode),
                "output_tail": "\n".join(output_chunks)[-2000:],
                "gate_status": "failed",
                "gate_reason": "",
            }
    return {
        "exit_code": 0,
        "output_tail": "\n".join(output_chunks)[-2000:],
        "gate_status": "passed",
        "gate_reason": "",
    }


def _is_bundle_exec_rspec_command(command: str) -> bool:
    normalized = _normalize_validation_command(command)
    return len(normalized) >= 3 and normalized[0] == "bundle" and normalized[1] == "exec" and normalized[2] == "rspec"


def _configure_bundle_environment(env: dict[str, str]) -> None:
    bundle_path = Path(str(env.get("BUNDLE_PATH") or _DEFAULT_BUNDLE_PATH)).expanduser()
    bundle_app_config = Path(str(env.get("BUNDLE_APP_CONFIG") or _DEFAULT_BUNDLE_APP_CONFIG)).expanduser()
    try:
        bundle_path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    try:
        bundle_app_config.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    env.setdefault("BUNDLE_PATH", str(bundle_path))
    env.setdefault("BUNDLE_APP_CONFIG", str(bundle_app_config))


def _bootstrap_bundle_runtime(
    *,
    workspace: Path,
    env: dict[str, str],
    timeout_seconds: int,
    output_chunks: list[str],
) -> dict[str, Any] | None:
    bootstrap_command = "bundle check >/dev/null 2>&1 || bundle install --jobs 2 --retry 1"
    output_chunks.append(f"$ {bootstrap_command}")
    try:
        proc = subprocess.run(
            ["/bin/zsh", "-lc", bootstrap_command],
            cwd=str(workspace),
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(30, timeout_seconds),
        )
    except FileNotFoundError:
        return {
            "exit_code": 127,
            "output_tail": "(/bin/zsh unavailable for explicit validation commands)",
            "gate_status": "failed",
            "gate_reason": "tool_missing",
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": 124,
            "output_tail": "\n".join(output_chunks)[-2000:],
            "gate_status": "failed",
            "gate_reason": "timeout",
        }
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if output:
        output_chunks.append(output)
    if int(proc.returncode) == 0:
        return None
    gate_reason = ""
    lowered = output.lower()
    if "command not found" in lowered or "no such file or directory" in lowered:
        gate_reason = "tool_missing"
    return {
        "exit_code": int(proc.returncode),
        "output_tail": "\n".join(output_chunks)[-2000:],
        "gate_status": "failed",
        "gate_reason": gate_reason,
    }


def _bundle_exec_rspec_fallback_command(command: str) -> str:
    normalized = _normalize_validation_command(command)
    if not _is_bundle_exec_rspec_command(command):
        return ""
    return _bundle_exec_rspec_fallback_command_from_args(list(normalized[3:]))


def _looks_like_bundle_exec_rspec_resolution_failure(output: str) -> bool:
    normalized = str(output or "").strip().lower()
    if not normalized:
        return False
    return "command not found: rspec" in normalized or "no such file or directory -- rspec" in normalized


def _bundle_exec_rspec_fallback_command_from_args(args: list[str]) -> str:
    fallback = [
        "bundle",
        "exec",
        "ruby",
        "-e",
        'load Gem.bin_path("rspec-core", "rspec")',
    ]
    if args:
        fallback.append("--")
        fallback.extend(args)
    return " ".join(shlex.quote(part) for part in fallback)


def _should_use_explicit_validation_commands(
    *,
    strategy: LanguageStrategy,
    validation_commands: tuple[str, ...],
) -> bool:
    commands = tuple(command for command in validation_commands if command)
    if not commands:
        return False
    if len(commands) != 1:
        return True
    normalized = _normalize_validation_command(commands[0])
    if not normalized:
        return False
    return normalized not in {tuple(strategy.local_test_cmd), tuple(strategy.docker_test_cmd)}


def _normalize_validation_command(command: str) -> tuple[str, ...]:
    candidate = str(command or "").strip()
    if not candidate:
        return ()
    cd_match = re.match(r"^cd\s+([^\n&|;]+?)\s*&&\s*(.+)$", candidate, re.IGNORECASE)
    if cd_match:
        candidate = cd_match.group(2).strip()
    try:
        return tuple(shlex.split(candidate))
    except ValueError:
        return ()


def _normalize_explicit_validation_commands(
    *,
    commands: tuple[str, ...],
    execution_root: str,
) -> NormalizedValidationCommandsResult:
    if not commands:
        return NormalizedValidationCommandsResult(())
    normalized_commands: list[str] = []
    for command in commands:
        normalized_command, rejection_reason = _normalize_explicit_validation_command(
            command=command,
            execution_root=execution_root,
        )
        if rejection_reason:
            return NormalizedValidationCommandsResult(tuple(normalized_commands), rejection_reason)
        normalized_commands.append(normalized_command)
    return NormalizedValidationCommandsResult(tuple(normalized_commands))


def _normalize_explicit_validation_command(*, command: str, execution_root: str) -> tuple[str, str]:
    candidate = str(command or "").strip()
    if not candidate:
        return "", ""
    match = re.match(
        r"^(?P<prefix>.*?)(?:^|;\s*)cd\s+(?P<cd>[^\n&|;]+?)\s*&&\s*(?P<rest>.+)$",
        candidate,
        re.IGNORECASE,
    )
    if not match:
        return candidate, ""

    raw_prefix = str(match.group("prefix") or "").strip()
    raw_cd = str(match.group("cd") or "").strip().strip("'\"")
    rest = str(match.group("rest") or "").strip()
    normalized_execution_root = _normalize_repo_relative_shell_path(execution_root)
    normalized_cd = _normalize_repo_relative_shell_path(raw_cd)

    if not rest:
        return _normalize_issue_validation_aliases(candidate, normalized_execution_root), ""
    if not normalized_cd or normalized_cd == ".":
        return _normalize_issue_validation_aliases(
            _join_shell_prefix_and_command(raw_prefix, rest),
            normalized_execution_root,
        ), ""
    if not normalized_execution_root:
        return _normalize_issue_validation_aliases(candidate, normalized_execution_root), ""
    if normalized_cd == normalized_execution_root:
        return _normalize_issue_validation_aliases(
            _join_shell_prefix_and_command(raw_prefix, rest),
            normalized_execution_root,
        ), ""
    if normalized_cd.startswith(f"{normalized_execution_root}/"):
        relative_cd = normalized_cd[len(normalized_execution_root) + 1 :]
        rewritten = f"cd {shlex.quote(relative_cd)} && {rest}"
        return _normalize_issue_validation_aliases(
            _join_shell_prefix_and_command(raw_prefix, rewritten),
            normalized_execution_root,
        ), ""
    return (
        candidate,
        (
            f"Explicit validation command '{candidate}' resolves outside the execution root "
            f"'{normalized_execution_root}'."
        ),
    )


def _normalize_issue_validation_aliases(command: str, execution_root: str) -> str:
    normalized_execution_root = _normalize_repo_relative_shell_path(execution_root)
    if normalized_execution_root != "e2e-apps/prosper-chat":
        return command

    normalized = _normalize_validation_command(command)
    if normalized[:2] != ("./scripts/healer_validate.sh", "frontend"):
        return command

    rebuilt = [normalized[0], "web", *normalized[2:]]
    return " ".join(shlex.quote(part) for part in rebuilt)


def _normalize_repo_relative_shell_path(path: str) -> str:
    normalized = str(path or "").strip().strip("'\"").replace("\\", "/")
    if not normalized:
        return ""
    if normalized == ".":
        return "."
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.rstrip("/")
    if not normalized:
        return "."
    return PurePosixPath(normalized).as_posix()


def _join_shell_prefix_and_command(prefix: str, command: str) -> str:
    cleaned_command = str(command or "").strip()
    cleaned_prefix = str(prefix or "").strip().rstrip(";")
    if not cleaned_prefix:
        return cleaned_command
    if not cleaned_command:
        return cleaned_prefix
    return f"{cleaned_prefix}; {cleaned_command}"


def _expand_issue_scoped_validation_commands(
    *,
    commands: tuple[str, ...],
    task_spec: HealerTaskSpec | None,
) -> tuple[str, ...]:
    if not commands:
        return ()
    assertion_targets = _issue_scoped_sql_assertion_targets(task_spec)
    if not assertion_targets:
        return commands
    expanded: list[str] = []
    serialized_targets = json.dumps(assertion_targets)
    for command in commands:
        normalized = _normalize_validation_command(command)
        if _is_sql_validation_command(normalized):
            expanded.append(
                _wrap_shell_command_with_env(
                    command,
                    set_vars={"FLOW_HEALER_SQL_CHECK_PATHS_JSON": serialized_targets},
                    unset_vars=("FLOW_HEALER_SQL_SKIP_RESET",),
                )
            )
            expanded.append(
                _wrap_shell_command_with_env(
                    command,
                    set_vars={"FLOW_HEALER_SQL_SKIP_RESET": "1"},
                    unset_vars=("FLOW_HEALER_SQL_CHECK_PATHS_JSON",),
                )
            )
            continue
        expanded.append(command)
    return tuple(expanded)


def _issue_scoped_sql_assertion_targets(task_spec: HealerTaskSpec | None) -> tuple[str, ...]:
    if task_spec is None:
        return ()
    targets: list[str] = []
    for raw_target in task_spec.output_targets:
        normalized = str(raw_target or "").strip().replace("\\", "/").lstrip("./")
        if not normalized or Path(normalized).suffix.lower() != ".sql":
            continue
        parts = PurePosixPath(normalized).parts
        if "assertions" not in parts:
            continue
        targets.append(normalized)
    return tuple(sorted(set(targets)))


def _is_sql_validation_command(command: tuple[str, ...]) -> bool:
    if not command:
        return False
    head = command[0]
    if head.endswith("scripts/healer_validate.sh"):
        return len(command) >= 2 and command[1] == "db"
    if head in {"python", "python3"} and len(command) >= 2:
        return command[1].endswith("scripts/flow_healer_sql_validate.py")
    return head.endswith("scripts/flow_healer_sql_validate.py")


def _wrap_shell_command_with_env(
    command: str,
    *,
    set_vars: dict[str, str],
    unset_vars: tuple[str, ...] = (),
) -> str:
    statements: list[str] = []
    for name in unset_vars:
        cleaned = str(name or "").strip()
        if cleaned:
            statements.append(f"unset {cleaned}")
    for name, value in set_vars.items():
        cleaned = str(name or "").strip()
        if cleaned:
            statements.append(f"export {cleaned}={shlex.quote(str(value))}")
    statements.append(command)
    return "; ".join(statements)


def _compose_targeted_command(strategy: LanguageStrategy, targeted_tests: list[str]) -> list[str]:
    base = list(strategy.docker_test_cmd)
    if not targeted_tests or not strategy.supports_targeted_paths:
        return base
    return [*base, *targeted_tests]


def _unsupported_docker_gate_result(*, mode: str) -> dict[str, Any]:
    return {
        "exit_code": 1 if mode == "docker_only" else 0,
        "output_tail": "(docker gate unsupported for this language)",
        "gate_status": "failed" if mode == "docker_only" else "skipped",
        "gate_reason": _DOCKER_UNSUPPORTED_REASON,
    }


def _maybe_soft_fail_docker_infra_gate(
    *,
    mode: str,
    runner_name: str,
    phase: str,
    summary: dict[str, Any],
    gate_result: dict[str, Any],
    gate_status: str,
) -> str:
    if mode != "local_then_docker" or runner_name != "docker" or gate_status != "failed":
        return gate_status
    local_key = "local_targeted_status" if phase == "targeted" else "local_full_status"
    if str(summary.get(local_key) or "").strip().lower() != "passed":
        return gate_status
    gate_reason = str(gate_result.get("gate_reason") or "").strip().lower()
    output_tail = str(gate_result.get("output_tail") or "")
    if gate_reason in {"tool_missing", "infra_unavailable", "docker_infra_unavailable"} or _looks_like_docker_infra_failure(output_tail):
        gate_result["gate_status"] = "warning"
        gate_result["gate_reason"] = "docker_infra_unavailable"
        return "warning"
    return gate_status


def _looks_like_docker_infra_failure(output_tail: str) -> bool:
    lowered = str(output_tail or "").lower()
    return any(marker in lowered for marker in _DOCKER_INFRA_OUTPUT_HINTS)


def _invoke_gate_runner(
    runner: Any,
    execution_path: Path,
    command: list[str],
    timeout_seconds: int,
    *,
    strategy: LanguageStrategy,
    local_gate_policy: str,
) -> dict[str, Any]:
    try:
        parameters = inspect.signature(runner).parameters
    except (TypeError, ValueError):
        parameters = {}
    supports_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters.values())
    accepts_strategy = supports_kwargs or "strategy" in parameters
    accepts_policy = supports_kwargs or "local_gate_policy" in parameters
    if accepts_strategy or accepts_policy:
        return runner(
            execution_path,
            command,
            timeout_seconds,
            strategy=strategy,
            local_gate_policy=local_gate_policy,
        )
    return runner(execution_path, command, timeout_seconds)


def _run_tests_locally(
    workspace: Path,
    command: list[str],
    timeout_seconds: int,
    *,
    strategy: LanguageStrategy,
    local_gate_policy: str,
) -> dict[str, Any]:
    if local_gate_policy == "skip":
        return {
            "exit_code": 0,
            "output_tail": "(local gate skipped by policy)",
            "gate_status": "skipped",
            "gate_reason": "policy_skip",
        }

    local_cmd = list(strategy.local_test_cmd)
    if not local_cmd:
        return {
            "exit_code": 0,
            "output_tail": "(local gate skipped: no local test command for this language)",
            "gate_status": "skipped",
            "gate_reason": "no_local_test_command",
        }

    if not _local_tool_available(local_cmd):
        message = f"(local gate unavailable: command not found: {local_cmd[0]})"
        if local_gate_policy == "force":
            return {
                "exit_code": 127,
                "output_tail": message,
                "gate_status": "failed",
                "gate_reason": "tool_missing",
            }
        return {
            "exit_code": 0,
            "output_tail": message,
            "gate_status": "skipped",
            "gate_reason": "tool_missing",
        }

    final_cmd = _compose_local_command(local_cmd=local_cmd, command=command, strategy=strategy)
    env = os.environ.copy()
    output_chunks: list[str] = []
    if _is_pytest_style_command(local_cmd):
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(workspace) if not existing else f"{workspace}{os.pathsep}{existing}"
    bundle_exec_rspec = _is_bundle_exec_rspec_local_command(final_cmd)
    if bundle_exec_rspec:
        _configure_bundle_environment(env)
        bootstrap_result = _bootstrap_bundle_runtime(
            workspace=workspace,
            env=env,
            timeout_seconds=timeout_seconds,
            output_chunks=output_chunks,
        )
        if bootstrap_result is not None:
            return bootstrap_result

    try:
        proc = subprocess.run(
            final_cmd,
            cwd=str(workspace),
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(30, timeout_seconds),
        )
    except FileNotFoundError:
        message = f"(local gate unavailable: command not found: {local_cmd[0]})"
        if local_gate_policy == "force":
            return {
                "exit_code": 127,
                "output_tail": message,
                "gate_status": "failed",
                "gate_reason": "tool_missing",
            }
        return {
            "exit_code": 0,
            "output_tail": message,
            "gate_status": "skipped",
            "gate_reason": "tool_missing",
        }

    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if output:
        output_chunks.append(output)
    if int(proc.returncode) != 0 and bundle_exec_rspec and _looks_like_bundle_exec_rspec_resolution_failure(output):
        fallback_command = _bundle_exec_rspec_fallback_command_from_args(list(final_cmd[3:]))
        output_chunks.append(
            "(bundle exec rspec could not resolve executable; retrying via ruby entrypoint fallback)"
        )
        output_chunks.append(f"$ {fallback_command}")
        try:
            fallback_proc = subprocess.run(
                ["/bin/zsh", "-lc", fallback_command],
                cwd=str(workspace),
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=max(30, timeout_seconds),
            )
        except FileNotFoundError:
            return {
                "exit_code": 127,
                "output_tail": "(/bin/zsh unavailable for local test gate fallback)",
                "gate_status": "failed",
                "gate_reason": "tool_missing",
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": 124,
                "output_tail": "\n".join(output_chunks)[-2000:],
                "gate_status": "failed",
                "gate_reason": "timeout",
            }
        fallback_output = ((fallback_proc.stdout or "") + "\n" + (fallback_proc.stderr or "")).strip()
        if fallback_output:
            output_chunks.append(fallback_output)
        if int(fallback_proc.returncode) == 0:
            return {
                "exit_code": 0,
                "output_tail": "\n".join(output_chunks)[-2000:],
                "gate_status": "passed",
                "gate_reason": "",
            }
    status = "passed" if int(proc.returncode) == 0 else "failed"
    return {
        "exit_code": int(proc.returncode),
        "output_tail": "\n".join(output_chunks)[-2000:],
        "gate_status": status,
        "gate_reason": "",
    }


def _local_tool_available(command: list[str]) -> bool:
    if not command:
        return False
    executable = command[0]
    if executable in {"pytest", "py.test"}:
        return True
    if executable.startswith(("/", "./")):
        return True
    return shutil.which(executable) is not None


def _compose_local_command(*, local_cmd: list[str], command: list[str], strategy: LanguageStrategy) -> list[str]:
    extra_args: list[str] = []
    if strategy.supports_targeted_paths and len(command) > len(strategy.docker_test_cmd):
        extra_args = command[len(strategy.docker_test_cmd):]
    merged = [*local_cmd, *extra_args]
    if _starts_with_any(merged, ["pytest"], ["py.test"]):
        return [sys.executable, "-m", *merged]
    return merged


def _starts_with_any(command: list[str], *prefixes: list[str]) -> bool:
    return any(command[: len(prefix)] == prefix for prefix in prefixes)


def _is_pytest_style_command(command: list[str]) -> bool:
    if _starts_with_any(command, ["pytest"], ["py.test"]):
        return True
    return bool(command) and command[0].startswith("python") and "pytest" in command


def _is_bundle_exec_rspec_local_command(command: list[str]) -> bool:
    return len(command) >= 3 and command[0] == "bundle" and command[1] == "exec" and command[2] == "rspec"


def _run_tests_in_docker(
    workspace: Path,
    command: list[str],
    timeout_seconds: int,
    *,
    strategy: LanguageStrategy,
    local_gate_policy: str,
) -> dict[str, Any]:
    del local_gate_policy
    if not strategy.supports_docker:
        return _unsupported_docker_gate_result(mode="docker_only")
    ensure_docker_runtime_running(reason="docker_test_gate")
    record_docker_activity(reason="docker_test_gate")
    container_name, docker_labels = _managed_docker_container_metadata(
        workspace=workspace,
        timeout_seconds=timeout_seconds,
        role="test-gate",
    )
    bash_script = _build_docker_test_script(command, strategy)
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
    ]
    for key, value in docker_labels.items():
        docker_cmd.extend(["--label", f"{key}={value}"])
    docker_cmd.extend(
        [
        "-v",
        f"{workspace}:/workspace",
        "-w",
        "/workspace",
        strategy.docker_image,
        "sh",
        "-c",
        bash_script,
        ]
    )
    try:
        proc = subprocess.run(
            docker_cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(60, timeout_seconds),
        )
    except FileNotFoundError:
        return {
            "exit_code": 127,
            "output_tail": "(docker gate unavailable: command not found: docker)",
            "gate_status": "failed",
            "gate_reason": "tool_missing",
        }
    except subprocess.TimeoutExpired:
        _cleanup_managed_docker_container(container_name)
        return {
            "exit_code": 124,
            "output_tail": "(docker gate unavailable: timed out while waiting for docker)",
            "gate_status": "failed",
            "gate_reason": "infra_unavailable",
        }
    status = "passed" if int(proc.returncode) == 0 else "failed"
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if status == "failed":
        _cleanup_managed_docker_container(container_name)
    gate_reason = ""
    if status == "failed" and _looks_like_docker_infra_failure(output):
        gate_reason = "infra_unavailable"
    record_docker_activity(reason="docker_test_gate")
    return {
        "exit_code": int(proc.returncode),
        "output_tail": output[-2000:],
        "gate_status": status,
        "gate_reason": gate_reason,
    }


def _managed_docker_container_metadata(
    *, workspace: Path, timeout_seconds: int, role: str
) -> tuple[str, dict[str, str]]:
    repo_name = _sanitize_docker_name_component(workspace.name or "repo")
    repo_hash = hashlib.sha1(str(workspace.resolve()).encode("utf-8")).hexdigest()[:12]
    labels = {
        "io.flow_healer.managed": "true",
        "io.flow_healer.repo_name": repo_name,
        "io.flow_healer.repo_hash": repo_hash,
        "io.flow_healer.role": role,
        "io.flow_healer.timeout_seconds": str(max(1, int(timeout_seconds))),
    }
    container_name = f"flow-healer-{repo_name}-{role}-{repo_hash}"
    return container_name[:128], labels


def _sanitize_docker_name_component(value: str) -> str:
    candidate = re.sub(r"[^a-z0-9_.-]+", "-", value.strip().lower()).strip("-.")
    return candidate or "repo"


def _cleanup_managed_docker_container(container_name: str) -> None:
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        return


def _build_retry_prompt(
    *,
    base_prompt: str,
    failure_class: str,
    failure_reason: str,
    task_spec: HealerTaskSpec | None = None,
    prefer_workspace_edits: bool = False,
    allow_exact_target_file_fallback: bool = False,
    allow_artifact_body_fallback: bool = False,
    continue_same_thread: bool = False,
    require_exact_target_file_bodies: bool = False,
    attempt_number: int = 0,
    issue_id: str = "",
    native_multi_agent_profile: str = "",
    native_multi_agent_max_subagents: int = 0,
) -> str:
    tailored_lines: list[str] = []
    sandbox_scoped = _is_issue_scoped_sandbox(task_spec)
    native_guidance = _native_multi_agent_guidance(
        task_spec=task_spec,
        profile=native_multi_agent_profile,
        max_subagents=native_multi_agent_max_subagents,
        prefer_workspace_edits=prefer_workspace_edits,
    ).strip()
    if native_guidance:
        tailored_lines.append(native_guidance)
    if failure_class in {"no_patch", "empty_diff"} or _is_no_workspace_change_failure_class(failure_class):
        if prefer_workspace_edits:
            tailored_lines.append(
                "STOP. You must edit files directly in the managed workspace now using your file editor."
                " Do not return a diff, plan, or status-only reply."
            )
            if continue_same_thread:
                tailored_lines.append("Keep working in the current thread and workspace; do not restart from scratch.")
            if allow_exact_target_file_fallback:
                tailored_lines.append(
                    "If direct edits still do not stick, return complete final file bodies in path-fenced blocks for the named output targets only."
                )
                if require_exact_target_file_bodies:
                    tailored_lines.append(
                        "This retry is strict: if direct edits do not persist, you must include complete path-fenced final file bodies for the named output targets."
                    )
            if allow_artifact_body_fallback:
                tailored_lines.append(
                    "If direct edits still do not stick, return the exact final artifact body for each named output target."
                )
            tailored_lines.append(
                "After editing, leave a concise summary of what changed and what validation you ran."
            )
            if attempt_number >= 1:
                tailored_lines.append(
                    "This is your second attempt. Open the target file with your editor, make the change, and save. Do not describe the change - make it."
                )
            if attempt_number >= 2 and issue_id:
                tailored_lines.append(
                    f"If you cannot make direct file edits, write a structured markdown summary of your findings to docs/healer-runs/{issue_id}-summary.md instead."
                )
        else:
            tailored_lines.append(
                "You must produce concrete file edits now. Do not return explanations, plans, or summaries."
            )
            tailored_lines.append(
                "Return exactly one valid unified diff fenced block:\n"
                "```diff\n"
                "diff --git a/path/to/file.py b/path/to/file.py\n"
                "--- a/path/to/file.py\n"
                "+++ b/path/to/file.py\n"
                "@@ -1,3 +1,3 @@\n"
                "-old line\n"
                "+new line\n"
                "```"
            )
            if attempt_number >= 1:
                tailored_lines.append(
                    "If a unified diff is not possible, return path-fenced file bodies:\n"
                    "```python path=src/module.py\n"
                    "# full file content here\n"
                    "```"
                )
            if attempt_number >= 2 and issue_id:
                tailored_lines.append(
                    f"If you cannot produce a diff or file body, write a structured markdown summary of your findings to docs/healer-runs/{issue_id}-summary.md."
                )
    if failure_class == "empty_diff":
        tailored_lines.append(
            "The previous response used a diff fence but left it empty. Return a complete patch body inside the fence."
        )
    if failure_class == "malformed_diff":
        tailored_lines.append(
            "The previous response used a diff fence with invalid patch syntax. Include real unified diff headers and hunks."
        )
    if failure_class == "no_code_diff":
        tailored_lines.append(
            "The previous output changed docs/artifacts only. This task requires at least one non-doc code/config file edit."
        )
        tailored_lines.append("Ensure the staged diff includes files outside docs/*.md style artifacts.")
    if failure_class == "artifact_validation_failed":
        tailored_lines.append(
            "The docs/config artifact patch is invalid. Fix the broken relative links or file references and keep the change scoped to artifacts."
        )
    if failure_class == "patch_apply_failed":
        tailored_lines.append(
            "Regenerate hunks against the current tree and keep paths/hunk headers exact to avoid apply errors."
        )
    if failure_class == "tests_failed":
        if sandbox_scoped:
            tailored_lines.append(
                "Carefully read the sandbox-local test output and fix only the issue-scoped regression."
            )
            tailored_lines.append(
                "Do not add or claim repo-root pytest/full-suite validation unless the issue explicitly requires it."
            )
        else:
            tailored_lines.append(
                "Carefully read the test output and fix the specific assertion or import that broke."
            )
    if failure_class == "verifier_failed":
        tailored_lines.append(
            "The AI verifier rejected the previous fix. Address the underlying root cause."
        )
        tailored_lines.append(
            "Stay narrowly scoped to the named targets and nearby existing files. Do not rebuild sandbox scaffolding, package manifests, or test harnesses unless the issue explicitly requires them."
        )
        if sandbox_scoped:
            tailored_lines.append(
                "For this sandbox-scoped issue, validation expectations are limited to the issue-declared execution root and commands."
            )

    guidance = "\n".join(tailored_lines).strip()
    if guidance:
        guidance = f"{guidance}\n"
    reset_line = "Reset your assumptions and edit the current workspace directly.\n" if prefer_workspace_edits else (
        "Reset your assumptions and produce a fresh unified diff that applies cleanly to the current tree.\n"
    )
    strict_line = (
        "Be strict about real file edits, scoped changes, and concise end-of-turn summaries."
        if prefer_workspace_edits
        else "Be strict about valid diff syntax, file paths, and hunk headers."
    )
    return (
        f"{base_prompt}\n\n"
        "Previous proposer output was unusable.\n"
        f"- Failure class: {failure_class}\n"
        f"- Failure reason: {failure_reason}\n"
        f"{guidance}"
        f"{reset_line}"
        f"{strict_line}"
    )


def _build_proposer_prompt(
    *,
    issue_id: str,
    issue_title: str,
    issue_body: str,
    task_spec: HealerTaskSpec,
    workspace: Path,
    learned_context: str,
    feedback_context: str,
    language_hint: str,
    prefer_workspace_edits: bool,
    native_multi_agent_profile: str = "",
    native_multi_agent_max_subagents: int = 0,
) -> str:
    output_contract = (
        "Your output MUST be direct file edits via your file editor tools."
        " Do not write a diff or describe changes in prose - the system only accepts workspace file edits."
        if prefer_workspace_edits
        else "Your output MUST contain a fenced diff block (```diff ... ```) or path-fenced file bodies"
        " (```lang path=/file ... ```). Plain prose responses are rejected and will cause a retry."
    )
    sections = [
        "### Role And Trusted Inputs\n"
        "You are the proposer agent for autonomous code healing.\n"
        "Treat the issue title/body, task contract, and loaded input-context files as trusted run instructions.\n"
        + (
            "Operate directly in the checked-out workspace, edit files in place, run the requested validation, and end with a brief operator summary."
            if prefer_workspace_edits
            else "Operate directly in the checked-out workspace and optimize for a valid finished patch, not commentary."
        )
        + f"\n{output_contract}",
        "### Task Context\n"
        + (language_hint.strip() + "\n" if language_hint.strip() else "")
        + (f"{learned_context.strip()}\n\n" if learned_context.strip() else "")
        + f"Issue #{issue_id}: {issue_title}\n\n{issue_body}",
    ]
    if feedback_context.strip():
        sections.append(f"### User Feedback For PR\n{feedback_context.strip()}")
    input_context = _render_input_context_block(task_spec=task_spec, workspace=workspace).strip()
    if input_context:
        sections.append(input_context)
    sections.extend(
        [
            task_spec_to_prompt_block(task_spec),
            _task_execution_instructions(task_spec),
            _native_multi_agent_guidance(
                task_spec=task_spec,
                profile=native_multi_agent_profile,
                max_subagents=native_multi_agent_max_subagents,
                prefer_workspace_edits=prefer_workspace_edits,
            ),
            _output_rules(task_spec, prefer_workspace_edits=prefer_workspace_edits),
            _completion_criteria(task_spec, prefer_workspace_edits=prefer_workspace_edits),
        ]
    )
    return "\n\n".join(section.strip() for section in sections if section.strip())


def _native_multi_agent_guidance(
    *,
    task_spec: HealerTaskSpec | None,
    profile: str,
    max_subagents: int,
    prefer_workspace_edits: bool,
) -> str:
    normalized_profile = str(profile or "").strip().lower()
    if normalized_profile not in {"initial", "recovery"}:
        return ""
    if task_spec is None:
        return ""
    normalized_task_kind = str(task_spec.task_kind or "").strip().lower()
    if normalized_task_kind not in {"fix", "build", "edit"}:
        return ""
    limit = max(1, int(max_subagents or 3))
    final_output = (
        "produce the final workspace edit"
        if prefer_workspace_edits
        else "produce the final patch"
    )
    lines = ["### Codex Native Multi-Agent"]
    if normalized_profile == "recovery":
        lines.append(
            "This is a native multi-agent recovery attempt. Re-evaluate the failure before changing the fix path."
        )
        lines.append(
            f"Spawn at most {limit} read-only subagents using the `explorer`, `test_forensics`, and `patch_critic` roles."
        )
        lines.append(f"Synthesize their findings, then {final_output} in the parent session.")
    else:
        lines.append(
            f"Use Codex native multi-agent only for read-heavy parallel work. Spawn at most {limit} read-only subagents."
        )
        lines.append("Use the `explorer`, `test_forensics`, and `patch_critic` roles when delegation will reduce context noise.")
    lines.append(
        "Delegate only codebase exploration, failing-test analysis, or patch critique. Do not delegate the immediate blocking code change."
    )
    lines.append(f"Only the parent session may {final_output}.")
    lines.append(
        "If child-agent findings conflict, choose the narrowest fix path that satisfies the issue contract and validation."
    )
    return "\n".join(lines)


def _task_execution_instructions(task_spec: HealerTaskSpec) -> str:
    targets = ", ".join(task_spec.output_targets) if task_spec.output_targets else "the minimum necessary repo files"
    lines = ["### Execution Rules"]
    if task_spec.task_kind == "research":
        lines.extend(
            [
                f"Research only what is needed to write the target artifact into: {targets}.",
                "Browse when needed, then synthesize the answer directly into the artifact instead of returning notes or status updates.",
            ]
        )
    elif task_spec.task_kind == "docs":
        lines.extend(
            [
                f"Write or revise the requested artifact directly in: {targets}.",
                "Do not stop at planning or analysis prose.",
            ]
        )
    else:
        lines.extend(
            [
                f"Implement the smallest safe patch in: {targets}.",
                "Inspect only enough files to identify the likely fix path, then edit.",
                "Prefer acting once the likely root cause is confirmed; do not return exploratory summaries.",
                "Escalate to a retry only when output format or patch validity failed.",
            ]
        )
    if task_spec.output_targets:
        lines.append(
            "If the named target files already exist, patch them in place. Do not recreate surrounding scaffolding, manifests, or test runners unless they are explicitly requested or genuinely missing."
        )
        lines.append(
            "Prefer the repo's existing test style and fallback patterns. Do not add new framework-specific test clients or dependencies when existing local patterns already cover the behavior."
        )
    if task_spec.language and task_spec.language != "unknown":
        lines.append(f"Follow {task_spec.language} conventions for imports, dependencies, tests, and file organization.")
    if task_spec.input_context_paths:
        input_context = ", ".join(task_spec.input_context_paths)
        lines.append(f"Treat these files as input-only context, not output targets: {input_context}.")
    if task_spec.tool_policy == "repo_plus_web":
        lines.append("Use web browsing only when repo context is insufficient for the requested research artifact.")
    else:
        lines.append("Rely on repo and local context unless the task explicitly requires outside facts.")
    if _is_issue_scoped_sandbox(task_spec):
        lines.append(
            f"This issue is sandbox-scoped to `{task_spec.execution_root}`. Treat only the issue-declared validation commands and files in that root as the required validation contract."
        )
        lines.append(
            "For sandbox-scoped issues, `Required code outputs` is an exact allowlist for edits. Do not change sibling files, manifests, lockfiles, or other nearby tests unless the issue explicitly names them."
        )
        lines.append(
            "Do not suggest or claim repo-root pytest/full-suite validation unless the issue explicitly asks for it."
        )
    if _requires_non_artifact_diff(task_spec=task_spec):
        lines.append(
            "This is a code-change task: ensure at least one non-doc file is modified (docs-only changes are invalid)."
        )
    return "\n".join(lines)


def _output_rules(task_spec: HealerTaskSpec, *, prefer_workspace_edits: bool) -> str:
    lines = [
        "### Output Rules",
        "Do not return plan-only prose, exploratory summaries, or status notes.",
    ]
    if prefer_workspace_edits:
        lines.append("Edit files directly in the workspace. Do not serialize a diff as the normal success path.")
        lines.append("End with a short summary of the files changed and the validation that ran.")
        if _allows_named_code_target_fallback(task_spec):
            lines.append(
                "If direct edits fail in this run, the only accepted fallback is complete path-fenced file bodies for the named output targets."
            )
    else:
        lines.append("Preferred output order: direct workspace edits first, unified diff second, path-fenced file bodies last.")
    if _allows_artifact_synthesis(task_spec):
        lines.append("Artifact synthesis is allowed for this task profile only when direct edits are unavailable.")
    else:
        lines.append("Artifact synthesis is not allowed for this task profile.")
    if prefer_workspace_edits:
        lines.append("Return a unified diff only if direct workspace edits are genuinely unavailable in this run.")
    else:
        lines.append(
            "If direct edits are unavailable, return ONLY one valid unified diff fenced block. Use path-fenced blocks only if a unified diff is not possible."
        )
    lines.append(_artifact_fallback_contract(task_spec).strip())
    return "\n".join(line for line in lines if line.strip())


def _completion_criteria(task_spec: HealerTaskSpec, *, prefer_workspace_edits: bool) -> str:
    if task_spec.validation_profile == "artifact_only":
        return (
            "### Completion Criteria\n"
            "Finish only when the target artifact content is written in the requested files and relative artifact links remain valid."
        )
    if prefer_workspace_edits:
        return (
            "### Completion Criteria\n"
            "Finish only when repo files changed materially in the workspace, the requested validation can pass, and the final response is a concise summary rather than a serialized patch."
        )
    return (
        "### Completion Criteria\n"
        "Finish only when repo files changed materially, the output format is valid, and the requested validation can pass without extra narrative."
    )


def _is_issue_scoped_sandbox(task_spec: HealerTaskSpec | None) -> bool:
    if task_spec is None:
        return False
    execution_root = str(getattr(task_spec, "execution_root", "") or "").strip().strip("/")
    if not execution_root:
        return False
    return execution_root.startswith("e2e-smoke/") or execution_root.startswith("e2e-apps/")


def _prefers_workspace_edits(*, connector: ConnectorProtocol, task_spec: HealerTaskSpec) -> bool:
    return connector.__class__.__name__ == "CodexAppServerConnector"


def _run_connector_turn(
    connector: ConnectorProtocol,
    thread_id: str,
    prompt: str,
    *,
    timeout_seconds: int,
) -> ConnectorTurnResult:
    if hasattr(connector, "run_turn_detailed"):
        detailed = getattr(connector, "run_turn_detailed")
        try:
            return detailed(thread_id, prompt, timeout_seconds=timeout_seconds)
        except TypeError:
            pass
    return ConnectorTurnResult(output_text=connector.run_turn(thread_id, prompt, timeout_seconds=timeout_seconds))


def _run_connector_exec_failover_turn(
    connector: ConnectorProtocol,
    thread_id: str,
    prompt: str,
    *,
    timeout_seconds: int,
) -> ConnectorTurnResult | None:
    if not hasattr(connector, "run_turn_exec_failover"):
        return None
    failover = getattr(connector, "run_turn_exec_failover")
    try:
        result = failover(thread_id, prompt, timeout_seconds=timeout_seconds)
    except TypeError:
        result = failover(thread_id, prompt)
    if isinstance(result, ConnectorTurnResult):
        return result
    return ConnectorTurnResult(output_text=str(result or "").strip())


def _attempt_serialized_output_materialization(
    *,
    workspace: Path,
    issue_title: str,
    issue_body: str,
    task_spec: HealerTaskSpec,
    language: str,
    timeout_seconds: int,
    proposer_output: str,
) -> bool:
    patch = _extract_diff_block(proposer_output)
    if patch.strip() and _looks_like_unified_diff(patch):
        patch_applied, _ = _apply_unified_diff_patch(
            workspace=workspace,
            patch=patch,
            timeout_seconds=timeout_seconds,
        )
        if patch_applied and _stage_workspace_changes(
            workspace,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            language=language,
        ):
            return True
    if _materialize_explicit_path_fenced_files(
        task_spec=task_spec,
        proposer_output=proposer_output,
        workspace=workspace,
    ) and _stage_workspace_changes(
        workspace,
        issue_title=issue_title,
        issue_body=issue_body,
        task_spec=task_spec,
        language=language,
    ):
        return True
    if _materialize_artifact_from_output(
        task_spec=task_spec,
        proposer_output=proposer_output,
        workspace=workspace,
    ) and _stage_workspace_changes(
        workspace,
        issue_title=issue_title,
        issue_body=issue_body,
        task_spec=task_spec,
        language=language,
    ):
        return True
    return False


def _allows_named_code_target_fallback(task_spec: HealerTaskSpec) -> bool:
    if task_spec.validation_profile == "artifact_only":
        return False
    if not task_spec.output_targets:
        return False
    return _requires_non_artifact_diff(task_spec=task_spec)


def _execution_contract_failure_fingerprint(
    *,
    failure_class: str,
    connector: ConnectorProtocol,
    task_spec: HealerTaskSpec,
) -> str:
    normalized_failure_class = str(failure_class or "").strip()
    if _is_no_workspace_change_failure_class(normalized_failure_class):
        pass
    elif normalized_failure_class not in {
        "empty_diff",
        "malformed_diff",
        "no_patch",
        "patch_apply_failed",
    }:
        return ""
    mode = "workspace_edit" if _prefers_workspace_edits(connector=connector, task_spec=task_spec) else "serialized_patch"
    return f"execution_contract|{mode}|{normalized_failure_class}"


def _render_input_context_block(*, task_spec: HealerTaskSpec, workspace: Path) -> str:
    if not task_spec.input_context_paths:
        return ""
    entries: list[str] = []
    for relative_path in task_spec.input_context_paths:
        rendered = _render_input_context_file(relative_path=relative_path, workspace=workspace)
        if rendered:
            entries.append(rendered)
    if not entries:
        return ""
    return "### Input Context Files\n" + "\n\n".join(entries) + "\n\n"


def _render_input_context_file(*, relative_path: str, workspace: Path) -> str:
    candidate = (workspace / relative_path).resolve()
    try:
        candidate.relative_to(workspace.resolve())
    except ValueError:
        logger.warning("Skipping input context outside workspace: %s", relative_path)
        return f"#### {relative_path}\n- Unable to load: path resolved outside the workspace."
    if not candidate.exists() or not candidate.is_file():
        return f"#### {relative_path}\n- Unable to load: file is missing."
    try:
        text = candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"#### {relative_path}\n- Unable to load: file is not UTF-8 text."
    body = text.strip()
    if not body:
        return f"#### {relative_path}\n- File is empty."
    if len(body) > _INPUT_CONTEXT_MAX_CHARS:
        body = body[:_INPUT_CONTEXT_MAX_CHARS].rstrip() + "\n...[truncated]"
    return f"#### {relative_path}\n```text\n{body}\n```"


def _validate_artifact_outputs(*, workspace: Path, diff_paths: list[str]) -> dict[str, Any]:
    checked_files: list[str] = []
    broken_links: list[dict[str, str]] = []
    parse_errors: list[dict[str, str]] = []
    for rel_path in diff_paths:
        file_path = workspace / rel_path
        if not file_path.exists() or not file_path.is_file():
            continue
        if _is_markdown_artifact_path(rel_path):
            checked_files.append(rel_path)
            broken_links.extend(_find_broken_markdown_links(file_path=file_path, rel_path=rel_path))
            continue
        structured_error = _validate_structured_artifact(file_path=file_path, rel_path=rel_path)
        if structured_error is None:
            continue
        checked_files.append(rel_path)
        parse_errors.append(structured_error)
    passed = not broken_links and not parse_errors
    summary = _artifact_validation_summary(broken_links=broken_links, parse_errors=parse_errors)
    return {
        "mode": "artifact_validation",
        "passed": passed,
        "failed_tests": 0 if passed else 1,
        "checked_files": checked_files,
        "broken_links": broken_links,
        "parse_errors": parse_errors,
        "summary": summary,
    }


def _is_markdown_artifact_path(path: str) -> bool:
    return Path(path).suffix.lower() in {".md", ".mdx", ".rst", ".txt"}


def _structured_artifact_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix == ".toml":
        return "toml"
    return ""


def _artifact_validation_summary(*, broken_links: list[dict[str, str]], parse_errors: list[dict[str, str]]) -> str:
    if not broken_links and not parse_errors:
        return "Artifact validation passed."
    parts: list[str] = []
    if broken_links:
        parts.append(f"{len(broken_links)} broken relative link(s)")
    if parse_errors:
        parts.append(f"{len(parse_errors)} structured file parse error(s)")
    return "Artifact validation failed with " + " and ".join(parts) + "."


def _validate_structured_artifact(*, file_path: Path, rel_path: str) -> dict[str, str] | None:
    artifact_type = _structured_artifact_type(rel_path)
    if not artifact_type:
        return None
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return {"file": rel_path, "type": artifact_type, "error": f"Unicode decode error: {exc}"}
    if artifact_type == "json":
        try:
            json.loads(content)
            return None
        except json.JSONDecodeError as exc:
            return {
                "file": rel_path,
                "type": artifact_type,
                "line": str(exc.lineno),
                "column": str(exc.colno),
                "error": exc.msg,
            }
    if artifact_type == "yaml":
        try:
            yaml.safe_load(content)
            return None
        except yaml.YAMLError as exc:
            problem_mark = getattr(exc, "problem_mark", None)
            error: dict[str, str] = {
                "file": rel_path,
                "type": artifact_type,
                "error": str(exc).splitlines()[0],
            }
            if problem_mark is not None:
                error["line"] = str(int(getattr(problem_mark, "line", 0)) + 1)
                error["column"] = str(int(getattr(problem_mark, "column", 0)) + 1)
            return error
    try:
        tomllib.loads(content)
        return None
    except tomllib.TOMLDecodeError as exc:
        error: dict[str, str] = {"file": rel_path, "type": artifact_type, "error": str(exc)}
        lineno = getattr(exc, "lineno", None)
        colno = getattr(exc, "colno", None)
        if lineno is not None:
            error["line"] = str(lineno)
        if colno is not None:
            error["column"] = str(colno)
        return error


def _find_broken_markdown_links(*, file_path: Path, rel_path: str) -> list[dict[str, str]]:
    content = file_path.read_text(encoding="utf-8", errors="replace")
    broken: list[dict[str, str]] = []
    in_fence = False
    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in _MARKDOWN_LINK_RE.finditer(raw_line):
            target = str(match.group(1) or "").strip()
            if not target or target.startswith("#") or _is_external_link_target(target):
                continue
            target_path = target.split("#", 1)[0].strip()
            if not target_path:
                continue
            resolved = (file_path.parent / target_path).resolve()
            if resolved.exists():
                continue
            broken.append(
                {
                    "file": rel_path,
                    "line": str(line_no),
                    "target": target,
                }
            )
    return broken


def _is_external_link_target(target: str) -> bool:
    lowered = target.lower()
    return lowered.startswith(("http://", "https://", "mailto:", "tel:"))


def _proposer_retry_budget_for_task(
    *,
    task_spec: HealerTaskSpec,
    default_retries: int,
    code_change_retries: int,
    artifact_retries: int,
) -> int:
    if _allows_artifact_synthesis(task_spec):
        return max(0, int(artifact_retries))
    if task_spec.validation_profile == "code_change":
        return max(0, int(code_change_retries))
    return max(0, int(default_retries))


def _turn_timeout_seconds_for_task(
    *,
    task_spec: HealerTaskSpec,
    default_timeout_seconds: int,
    code_change_timeout_seconds: int,
) -> int:
    if task_spec.validation_profile == "code_change":
        return max(30, int(code_change_timeout_seconds))
    return max(30, int(default_timeout_seconds))


def _requires_non_artifact_diff(*, task_spec: HealerTaskSpec) -> bool:
    if task_spec.validation_profile != "code_change":
        return False
    return task_spec.task_kind in {"build", "fix", "edit"}


def _has_non_artifact_diff(diff_paths: list[str]) -> bool:
    return any(not _is_artifact_path(path) for path in diff_paths)


def _artifact_fallback_contract(task_spec: HealerTaskSpec) -> str:
    if not _allows_artifact_synthesis(task_spec):
        return ""
    targets = list(task_spec.output_targets) if task_spec.output_targets else ["docs/output.md"]
    if len(targets) == 1:
        target = targets[0]
        return (
            "For artifact-only docs/research tasks, if you cannot emit a valid diff, "
            f"return the final file contents for `{target}` in exactly one fenced block like "
            f"```markdown path={target}```.\n"
            "Return file body only inside the fence, with no narration before or after it."
        )
    rendered_targets = ", ".join(f"`{target}`" for target in targets)
    examples = "\n".join(
        "\n".join([f"```markdown path={target}", "...", "```"])
        for target in targets
    )
    return (
        "For artifact-only docs/research tasks with multiple targets, if you cannot emit a valid diff, "
        "return one fenced block per target using explicit `path=` markers.\n"
        f"Required targets: {rendered_targets}\n"
        f"Example format:\n{examples}\n"
        "Return file bodies only inside fences, with no narration before or after them."
    )


_GENERIC_ARTIFACT_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".bundle",
    ".gradle",
    ".next",
    ".nuxt",
    ".yarn",
    "coverage",
    "dist",
    "build",
    ".cache",
    "pip-wheel-metadata",
    ".build",
    ".swiftpm",
    ".temp",
    ".branches",
}
_GENERIC_ARTIFACT_FILES = {
    ".ds_store",
    ".coverage",
}
_GENERIC_ARTIFACT_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".class",
}
_LANGUAGE_ARTIFACT_DIRS = {
    "python": {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".venv", "venv", "env", "dist", "build", "pip-wheel-metadata"},
    "node": {"node_modules", "dist", "build", "coverage", ".next", ".nuxt"},
    "rust": {"target"},
    "swift": {".build", ".swiftpm"},
}
_LOCKFILE_GROUPS = {
    "package-lock.json": {"package.json", "dependency", "dependencies", "lockfile"},
    "pnpm-lock.yaml": {"package.json", "dependency", "dependencies", "lockfile"},
    "yarn.lock": {"package.json", "dependency", "dependencies", "lockfile"},
    "gemfile.lock": {"gemfile", "dependency", "dependencies", "lockfile"},
    "cargo.lock": {"cargo.toml", "dependency", "dependencies", "lockfile"},
}
_RUBY_BUNDLE_BINSTUB_FILES = {"rspec"}
_DEFAULT_BUNDLE_PATH = str((Path.home() / ".flow-healer" / "bundle").resolve())
_DEFAULT_BUNDLE_APP_CONFIG = str((Path.home() / ".flow-healer" / "bundle-config").resolve())


def _stage_workspace_changes(
    workspace: Path,
    *,
    issue_title: str = "",
    issue_body: str = "",
    task_spec: HealerTaskSpec | None = None,
    language: str = "",
) -> bool:
    result = _stage_workspace_changes_detailed(
        workspace,
        issue_title=issue_title,
        issue_body=issue_body,
        task_spec=task_spec,
        language=language,
    )
    return bool(result.kept_paths)


def _stage_workspace_changes_detailed(
    workspace: Path,
    *,
    issue_title: str = "",
    issue_body: str = "",
    task_spec: HealerTaskSpec | None = None,
    language: str = "",
) -> bool:
    subprocess.run(
        ["git", "-C", str(workspace), "add", "-A"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    result = _filter_staged_changes(
        workspace,
        issue_title=issue_title,
        issue_body=issue_body,
        task_spec=task_spec,
        language=language,
    )
    if result.excluded_paths:
        preview = ", ".join(result.excluded_paths[:5])
        if len(result.excluded_paths) > 5:
            preview += ", ..."
        logger.info(
            "Excluded %d generated artifact path(s) from staged diff in %s: %s",
            len(result.excluded_paths),
            workspace,
            preview,
        )
    return result


def _filter_staged_changes(
    workspace: Path,
    *,
    issue_title: str,
    issue_body: str,
    task_spec: HealerTaskSpec | None,
    language: str,
) -> FilteredStageResult:
    staged_paths = _changed_paths(workspace)
    excluded_paths = [
        path
        for path in staged_paths
        if _should_exclude_generated_artifact(
            path,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            language=language,
        )
    ]
    if excluded_paths:
        _cleanup_workspace_paths(workspace, excluded_paths)
    return FilteredStageResult(
        kept_paths=_changed_paths(workspace),
        excluded_paths=excluded_paths,
    )


def _workspace_status_entries(workspace: Path) -> list[WorkspaceStatusEntry]:
    proc = subprocess.run(
        ["git", "-C", str(workspace), "status", "--short", "--untracked-files=all"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        return []
    entries: list[WorkspaceStatusEntry] = []
    for raw_line in (proc.stdout or "").splitlines():
        line = raw_line.rstrip()
        if len(line) < 4:
            continue
        status = line[:2]
        path = line[3:].strip()
        if " -> " in path and status[0] in {"R", "C"}:
            path = path.split(" -> ", 1)[1].strip()
        if not path:
            continue
        entries.append(WorkspaceStatusEntry(status=status, path=path))
    return entries


def _empty_workspace_status(*, execution_root: str) -> dict[str, Any]:
    return {
        "execution_root": execution_root,
        "staged_paths": [],
        "unstaged_paths": [],
        "untracked_paths": [],
        "contamination_paths": [],
        "cleanup_performed": False,
        "cleaned_paths": [],
        "cleanup_cycles_used": 0,
    }


def _workspace_status_summary(
    workspace: Path,
    *,
    issue_title: str,
    issue_body: str,
    task_spec: HealerTaskSpec | None,
    language: str,
    execution_root: str,
) -> dict[str, Any]:
    entries = _workspace_status_entries(workspace)
    staged_paths: list[str] = []
    unstaged_paths: list[str] = []
    untracked_paths: list[str] = []
    contamination_paths: list[str] = []
    for entry in entries:
        status = entry.status
        path = entry.path
        if status == "??":
            untracked_paths.append(path)
        else:
            if status[0] not in {" ", "?"}:
                staged_paths.append(path)
            if status[1] not in {" ", "?"}:
                unstaged_paths.append(path)
        if _should_exclude_generated_artifact(
            path,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            language=language,
        ):
            contamination_paths.append(path)
    return {
        "execution_root": execution_root,
        "staged_paths": sorted(set(staged_paths)),
        "unstaged_paths": sorted(set(unstaged_paths)),
        "untracked_paths": sorted(set(untracked_paths)),
        "contamination_paths": sorted(set(contamination_paths)),
        "cleanup_performed": False,
        "cleaned_paths": [],
        "cleanup_cycles_used": 0,
    }


def _cleanup_workspace_paths(workspace: Path, paths: list[str]) -> None:
    for path in paths:
        full_path = workspace / path
        try:
            if full_path.is_symlink() or full_path.is_file():
                full_path.unlink(missing_ok=True)
            elif full_path.is_dir():
                shutil.rmtree(full_path, ignore_errors=True)
        except Exception:
            pass
        subprocess.run(
            ["git", "-C", str(workspace), "restore", "--staged", "--worktree", "--", path],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        subprocess.run(
            ["git", "-C", str(workspace), "reset", "HEAD", "--", path],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        subprocess.run(
            ["git", "-C", str(workspace), "clean", "-fdx", "--", path],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )


def _generated_artifact_contamination_reason(paths: list[str], *, execution_root: str) -> str:
    label = execution_root or "repo"
    preview = ", ".join(paths[:5])
    if len(paths) > 5:
        preview += ", ..."
    return (
        f"Workspace contains generated artifact contamination outside the requested diff in {label}: "
        f"{preview}. Clean the artifact(s) or keep them out of the worktree."
    )


def _generated_artifact_failure_fingerprint(paths: list[str], *, execution_root: str) -> str:
    normalized_paths = [str(path).strip().lower() for path in paths if str(path).strip()]
    normalized_paths = sorted(set(normalized_paths))
    root = execution_root.strip().lower() or "repo"
    return f"generated_artifact_contamination|{root}|{'|'.join(normalized_paths)}"


def _stabilize_workspace_hygiene(
    workspace: Path,
    *,
    issue_title: str,
    issue_body: str,
    task_spec: HealerTaskSpec | None,
    language: str,
    execution_root: str,
    allow_cleanup: bool,
) -> tuple[dict[str, Any], list[str], str]:
    summary = _workspace_status_summary(
        workspace,
        issue_title=issue_title,
        issue_body=issue_body,
        task_spec=task_spec,
        language=language,
        execution_root=execution_root,
    )
    contamination_paths = list(summary["contamination_paths"])
    if not contamination_paths:
        return summary, [], ""
    if not allow_cleanup:
        return summary, [], _generated_artifact_contamination_reason(contamination_paths, execution_root=execution_root)
    _cleanup_workspace_paths(workspace, contamination_paths)
    _stage_workspace_changes(
        workspace,
        issue_title=issue_title,
        issue_body=issue_body,
        task_spec=task_spec,
        language=language,
    )
    refreshed = _workspace_status_summary(
        workspace,
        issue_title=issue_title,
        issue_body=issue_body,
        task_spec=task_spec,
        language=language,
        execution_root=execution_root,
    )
    refreshed["cleanup_performed"] = True
    refreshed["cleaned_paths"] = contamination_paths
    if refreshed["contamination_paths"]:
        tolerated_paths = [
            path
            for path in refreshed["contamination_paths"]
            if _is_tolerated_runtime_artifact(path, language=language)
            and path not in refreshed.get("staged_paths", [])
        ]
        if tolerated_paths:
            refreshed["contamination_paths"] = [
                path for path in refreshed["contamination_paths"] if path not in tolerated_paths
            ]
    if refreshed["contamination_paths"]:
        return (
            refreshed,
            contamination_paths,
            _generated_artifact_contamination_reason(list(refreshed["contamination_paths"]), execution_root=execution_root),
        )
    return refreshed, contamination_paths, ""


def _is_tolerated_runtime_artifact(path: str, *, language: str) -> bool:
    normalized = str(path or "").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        return False
    normalized_lower = normalized.lower()
    effective_language = str(language or "").strip().lower()
    lockfile_name = PurePosixPath(normalized_lower).name
    if lockfile_name in _LOCKFILE_GROUPS:
        # Validation tools can regenerate lockfiles even when lockfile edits are not part
        # of the requested patch. Treat these as tolerated runtime noise while unstaged.
        return (
            (effective_language == "node" and lockfile_name == "package-lock.json")
            or (effective_language == "ruby" and lockfile_name == "gemfile.lock")
            or (effective_language == "rust" and lockfile_name == "cargo.lock")
        )
    if _is_ruby_bundle_binstub_path(normalized, language=effective_language):
        return True

    parts = _normalized_path_parts(normalized)
    filename = parts[-1] if parts else normalized_lower
    if filename in _GENERIC_ARTIFACT_FILES:
        return True
    if any(part in _GENERIC_ARTIFACT_DIRS for part in parts[:-1]):
        return True
    if any(filename.endswith(suffix) for suffix in _GENERIC_ARTIFACT_SUFFIXES):
        return True
    if any(part.endswith(".egg-info") for part in parts):
        return True

    language_dirs = _LANGUAGE_ARTIFACT_DIRS.get(effective_language, set())
    return any(part in language_dirs for part in parts[:-1])


def _with_workspace_status(
    summary: dict[str, Any],
    *,
    workspace_status: dict[str, Any],
    failure_fingerprint: str,
) -> dict[str, Any]:
    enriched = dict(summary or {})
    enriched["workspace_status"] = dict(workspace_status or {})
    if failure_fingerprint:
        enriched["failure_fingerprint"] = failure_fingerprint
    promotion_transitions = _local_promotion_transitions(enriched)
    if promotion_transitions:
        enriched["promotion_transitions"] = promotion_transitions
    return enriched


def _local_promotion_transitions(summary: dict[str, Any]) -> list[str]:
    transitions = _normalized_promotion_transitions(summary.get("promotion_transitions"))
    failure_screenshot_present = _browser_summary_has_phase_screenshot(summary, phase="failure")
    resolution_screenshot_present = _browser_summary_has_phase_screenshot(summary, phase="resolution")
    browser_evidence_required = bool(summary.get("browser_evidence_required"))
    artifact_proof_ready = bool(summary.get("artifact_proof_ready")) or (
        browser_evidence_required and failure_screenshot_present and resolution_screenshot_present
    )
    promotion_state = str(summary.get("promotion_state") or "").strip().lower()
    phase_states = summary.get("phase_states")
    phase_state_map = dict(phase_states) if isinstance(phase_states, dict) else {}

    if failure_screenshot_present:
        _append_promotion_transition(transitions, "failure_artifacts_captured")
    if resolution_screenshot_present:
        _append_promotion_transition(transitions, "resolution_artifacts_captured")
    if (promotion_state == "promotion_ready" or bool(phase_state_map.get("promotion_ready"))) and (
        not browser_evidence_required or artifact_proof_ready
    ):
        _append_promotion_transition(transitions, "local_validated")
    if (
        promotion_state == "merge_blocked"
        or bool(phase_state_map.get("merge_blocked"))
        or (browser_evidence_required and not artifact_proof_ready)
    ):
        _append_promotion_transition(transitions, "merge_blocked")
    return transitions


def _browser_summary_has_phase_screenshot(summary: dict[str, Any], *, phase: str) -> bool:
    artifact_bundle = summary.get("artifact_bundle")
    if isinstance(artifact_bundle, dict):
        phase_payload = artifact_bundle.get(f"{phase}_artifacts")
        if isinstance(phase_payload, dict) and str(phase_payload.get("screenshot_path") or "").strip():
            return True
    artifact_links = summary.get("artifact_links")
    if not isinstance(artifact_links, list):
        return False
    expected_label = f"{phase}_screenshot"
    return any(
        isinstance(item, dict) and str(item.get("label") or "").strip().lower() == expected_label
        for item in artifact_links
    )


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


def _append_promotion_transition(transitions: list[str], label: str) -> None:
    normalized = str(label or "").strip().lower()
    if normalized and normalized not in transitions:
        transitions.append(normalized)


def _unstage_paths(workspace: Path, paths: list[str]) -> None:
    for start in range(0, len(paths), 100):
        chunk = paths[start:start + 100]
        subprocess.run(
            ["git", "-C", str(workspace), "restore", "--staged", "--", *chunk],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )


def _should_exclude_generated_artifact(
    path: str,
    *,
    issue_title: str,
    issue_body: str,
    task_spec: HealerTaskSpec | None,
    language: str,
) -> bool:
    normalized = str(path or "").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        return False
    if _is_explicit_output_target(normalized, task_spec):
        return False

    normalized_lower = normalized.lower()
    lockfile_name = PurePosixPath(normalized_lower).name
    if lockfile_name in _LOCKFILE_GROUPS:
        return not _issue_allows_lockfile_change(
            normalized,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
        )
    if _is_ruby_bundle_binstub_path(normalized, language=language):
        return True

    parts = _normalized_path_parts(normalized)
    filename = parts[-1] if parts else normalized_lower
    if filename in _GENERIC_ARTIFACT_FILES:
        return True
    if any(part in _GENERIC_ARTIFACT_DIRS for part in parts[:-1]):
        return True
    if any(filename.endswith(suffix) for suffix in _GENERIC_ARTIFACT_SUFFIXES):
        return True
    if any(part.endswith(".egg-info") for part in parts):
        return True

    effective_language = str(language or "").strip().lower()
    language_dirs = _LANGUAGE_ARTIFACT_DIRS.get(effective_language, set())
    if any(part in language_dirs for part in parts[:-1]):
        return True

    return False


def _normalized_path_parts(path: str) -> list[str]:
    normalized = str(path or "").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        return []
    return [part.lower() for part in normalized.split("/") if part]


def _is_ruby_bundle_binstub_path(path: str, *, language: str) -> bool:
    if str(language or "").strip().lower() != "ruby":
        return False
    parts = _normalized_path_parts(path)
    if len(parts) < 2:
        return False
    return parts[-2] == "bin" and parts[-1] in _RUBY_BUNDLE_BINSTUB_FILES


def _is_explicit_output_target(path: str, task_spec: HealerTaskSpec | None) -> bool:
    if task_spec is None:
        return False
    normalized = str(path or "").strip().lstrip("./").lower()
    if not normalized:
        return False
    for target in task_spec.output_targets:
        raw_target = str(target or "").strip().lstrip("./")
        normalized_target = raw_target.lower().rstrip("/")
        if not normalized_target:
            continue
        if raw_target.endswith("/"):
            if normalized == normalized_target or normalized.startswith(f"{normalized_target}/"):
                return True
            continue
        if normalized == normalized_target:
            return True
    return False


def _issue_allows_lockfile_change(
    path: str,
    *,
    issue_title: str,
    issue_body: str,
    task_spec: HealerTaskSpec | None,
) -> bool:
    normalized = str(path or "").strip().lstrip("./")
    normalized_lower = normalized.lower()
    lockfile_name = PurePosixPath(normalized_lower).name
    if _is_explicit_output_target(normalized, task_spec):
        return True
    issue_text = " ".join(
        part.strip().lower()
        for part in (issue_title, issue_body)
        if str(part or "").strip()
    )
    if not issue_text:
        return False
    if normalized_lower in issue_text or PurePosixPath(normalized_lower).name in issue_text:
        return True
    keywords = _LOCKFILE_GROUPS.get(lockfile_name, set())
    return any(keyword in issue_text for keyword in keywords)


def _classify_non_patch_failure(proposer_output: str) -> tuple[str, str]:
    text = (proposer_output or "").strip()
    lowered = text.lower()
    if lowered.startswith("connectorunavailable:"):
        return "connector_unavailable", text[:500]
    if lowered.startswith("connectorruntimeerror:"):
        return "connector_runtime_error", text[:500]
    if "codex cli not found" in lowered or "unable to resolve codex command" in lowered:
        return "connector_unavailable", text[:500]
    if "timed out" in lowered or "mcp startup" in lowered or "transport channel closed" in lowered:
        return "connector_runtime_error", text[:500]
    if lowered.startswith("error:") and "codex" in lowered:
        return "connector_runtime_error", text[:500]
    if _contains_diff_fence(text):
        return "empty_diff", "Proposer returned an empty diff fenced block."
    return "no_patch", "Proposer did not return a unified diff block."


def _augment_failure_reason_with_connector_health(
    *,
    connector: ConnectorProtocol,
    failure_class: str,
    failure_reason: str,
) -> str:
    if failure_class not in {"connector_unavailable", "connector_runtime_error"}:
        return failure_reason
    snapshot_fn = getattr(connector, "health_snapshot", None)
    if not callable(snapshot_fn):
        return failure_reason
    try:
        snapshot = snapshot_fn()
    except Exception:
        return failure_reason
    if not isinstance(snapshot, dict):
        return failure_reason

    details: list[str] = []
    resolved_command = str(snapshot.get("resolved_command") or "").strip()
    if resolved_command:
        details.append(f"resolved_command={resolved_command}")
    runtime_kind = str(snapshot.get("last_runtime_error_kind") or "").strip()
    if runtime_kind:
        details.append(f"runtime_kind={runtime_kind}")
    stdout_tail = str(snapshot.get("last_runtime_stdout_tail") or "").strip()
    if stdout_tail:
        details.append(f"stdout_tail={stdout_tail}")
    stderr_tail = str(snapshot.get("last_runtime_stderr_tail") or "").strip()
    if stderr_tail:
        details.append(f"stderr_tail={stderr_tail}")
    availability_reason = str(snapshot.get("availability_reason") or "").strip()
    if failure_class == "connector_unavailable" and availability_reason:
        details.append(f"availability_reason={availability_reason}")
    last_health_error = str(snapshot.get("last_health_error") or "").strip()
    if last_health_error:
        details.append(f"last_health_error={last_health_error}")
    if not details:
        return failure_reason

    summary = f"{failure_reason} | " + " | ".join(details)
    return summary[:500]


def _contains_diff_fence(text: str) -> bool:
    return bool(re.search(r"```diff(?:[^\n`]*)\n", text or "", re.IGNORECASE))


def _looks_like_unified_diff(patch: str) -> bool:
    normalized = (patch or "").strip()
    if not normalized:
        return False
    has_diff_header = "diff --git " in normalized
    has_file_headers = "--- " in normalized and "+++ " in normalized
    has_hunks = "@@ " in normalized or "\n@@" in normalized
    has_metadata_change = any(
        marker in normalized
        for marker in (
            "new file mode ",
            "deleted file mode ",
            "rename from ",
            "rename to ",
            "copy from ",
            "copy to ",
            "Binary files ",
            "GIT binary patch",
        )
    )
    if has_file_headers and (has_hunks or has_metadata_change or has_diff_header):
        return True
    return has_diff_header and has_metadata_change


def _apply_unified_diff_patch(*, workspace: Path, patch: str, timeout_seconds: int) -> tuple[bool, str]:
    if not workspace.is_dir():
        return False, f"workspace missing before git apply: {workspace}"
    patch_path = workspace / ".apple-flow-healer.patch"
    try:
        patch_path.write_text(patch, encoding="utf-8")
    except OSError as exc:
        return False, f"failed to write patch file in workspace {workspace}: {exc}"
    try:
        apply_proc = subprocess.run(
            ["git", "-C", str(workspace), "apply", "--index", "--reject", str(patch_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    finally:
        if patch_path.exists():
            patch_path.unlink(missing_ok=True)
    if apply_proc.returncode == 0:
        return True, ""
    _reset_workspace_after_failed_apply(workspace)
    return False, (apply_proc.stderr or apply_proc.stdout or "git apply failed").strip()[:500]


def _materialize_artifact_from_output(
    *,
    task_spec: HealerTaskSpec,
    proposer_output: str,
    workspace: Path,
) -> bool:
    if not _allows_artifact_synthesis(task_spec):
        return False
    text = (proposer_output or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered.startswith("connectorunavailable:") or lowered.startswith("connectorruntimeerror:"):
        return False
    if lowered.startswith("error:") and "codex" in lowered:
        return False

    target_rels = [
        rel for rel in (_safe_rel_path(path) for path in task_spec.output_targets) if rel is not None
    ]
    if not target_rels:
        return False
    path_fenced_bodies = _extract_path_fenced_bodies(text)
    require_explicit_path = len(target_rels) > 1
    workspace_root = workspace.resolve()
    wrote_any = False
    for target_rel in target_rels:
        target_abs = (workspace / target_rel).resolve()
        if not _is_within_workspace(path=target_abs, workspace=workspace_root):
            continue
        content = _extract_artifact_content(
            text=text,
            target_path=target_rel,
            path_fenced_bodies=path_fenced_bodies,
            require_explicit_path=require_explicit_path,
        )
        if not content.strip():
            continue
        if _looks_like_status_update_summary(content):
            continue
        if not content.endswith("\n"):
            content += "\n"
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        existing = target_abs.read_text(encoding="utf-8") if target_abs.exists() else None
        if existing == content:
            continue
        target_abs.write_text(content, encoding="utf-8")
        wrote_any = True
    return wrote_any


def _materialize_completion_artifact(
    *,
    issue_id: str,
    issue_title: str,
    task_spec: HealerTaskSpec,
    proposer_output: str,
    failure_class: str,
    failure_reason: str,
    workspace: Path,
) -> bool:
    """Write a structured run-summary artifact when the agent ran but produced no file changes."""
    is_no_workspace_change = _is_no_workspace_change_failure_class(failure_class)
    if failure_class not in {"no_patch", "empty_diff"} and not is_no_workspace_change:
        return False
    if is_no_workspace_change and task_spec.validation_profile != "artifact_only":
        return False
    output_text = (proposer_output or "").strip()
    if not output_text:
        return False
    # If the agent returned a structured diff or path-fenced files, don't replace
    # with an artifact - the structured output should be retried or escalated instead.
    if _contains_diff_fence(proposer_output) or bool(_extract_path_fenced_bodies(proposer_output)):
        return False
    slug = re.sub(r"[^a-z0-9]+", "-", issue_title.lower()).strip("-")[:40]
    artifact_path = workspace / "docs" / "healer-runs" / f"{issue_id}-{slug}.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    targets = ", ".join(task_spec.output_targets) if task_spec.output_targets else "(inferred from issue)"
    output_excerpt = output_text[:2000] + ("..." if len(output_text) > 2000 else "")
    content = (
        f"# Healer Run: Issue #{issue_id}\n\n"
        f"**Title:** {issue_title}  \n"
        f"**Task kind:** {task_spec.task_kind}  \n"
        f"**Validation profile:** {task_spec.validation_profile}  \n"
        f"**Output targets:** {targets}  \n"
        f"**Generated:** {now}\n\n"
        f"## Status\n\n"
        f"The agent completed but did not produce direct file changes.\n\n"
        f"- Failure class: `{failure_class}`\n"
        f"- Reason: {failure_reason}\n\n"
        f"## Agent Response\n\n"
        f"```\n{output_excerpt}\n```\n"
    )
    existing = artifact_path.read_text(encoding="utf-8") if artifact_path.exists() else None
    if existing == content:
        return False
    artifact_path.write_text(content, encoding="utf-8")
    return True


def _materialize_explicit_path_fenced_files(
    *,
    task_spec: HealerTaskSpec,
    proposer_output: str,
    workspace: Path,
) -> bool:
    text = (proposer_output or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered.startswith("connectorunavailable:") or lowered.startswith("connectorruntimeerror:"):
        return False
    if lowered.startswith("error:") and "codex" in lowered:
        return False

    fenced = _extract_path_fenced_bodies(text)
    if not fenced:
        return False

    workspace_root = workspace.resolve()
    disallowed_targets = {
        rel.as_posix()
        for rel in (
            _safe_rel_path(path)
            for path in (task_spec.input_context_paths or ())
        )
        if rel is not None
    }
    wrote_any = False
    for rel_path, body in fenced.items():
        if rel_path in disallowed_targets:
            continue
        target_rel = _safe_rel_path(rel_path)
        if target_rel is None:
            continue
        target_abs = (workspace / target_rel).resolve()
        if not _is_within_workspace(path=target_abs, workspace=workspace_root):
            continue
        if not body.strip():
            continue
        if _looks_like_status_update_summary(body):
            continue
        content = body if body.endswith("\n") else f"{body}\n"
        existing = target_abs.read_text(encoding="utf-8") if target_abs.exists() else None
        if existing == content:
            continue
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        target_abs.write_text(content, encoding="utf-8")
        wrote_any = True
    return wrote_any


def _materialize_named_code_targets_from_output(
    *,
    task_spec: HealerTaskSpec,
    proposer_output: str,
    workspace: Path,
    strict: bool = True,
) -> PathFenceMaterializationResult:
    if not _allows_named_code_target_fallback(task_spec):
        return PathFenceMaterializationResult(wrote_any=False)
    text = (proposer_output or "").strip()
    if not text:
        return PathFenceMaterializationResult(wrote_any=False)
    fenced = _extract_path_fenced_bodies(text)
    if not fenced:
        return PathFenceMaterializationResult(wrote_any=False)

    allowed_targets = {
        rel.as_posix()
        for rel in (_safe_rel_path(path) for path in task_spec.output_targets)
        if rel is not None and not _is_artifact_path(rel.as_posix())
    }
    if not allowed_targets:
        return PathFenceMaterializationResult(wrote_any=False)
    emitted_paths = set(fenced)
    unexpected = sorted(path for path in emitted_paths if path not in allowed_targets)
    if strict and unexpected:
        return PathFenceMaterializationResult(
            wrote_any=False,
            rejection_reason=f"fallback included unnamed paths: {', '.join(unexpected)}",
        )

    workspace_root = workspace.resolve()
    entries = list(fenced.items()) if strict else [(path, body) for path, body in fenced.items() if path in allowed_targets]
    if not entries:
        return PathFenceMaterializationResult(
            wrote_any=False,
            rejection_reason="fallback omitted all named output targets",
        )
    wrote_any = False
    for rel_path, body in entries:
        target_rel = _safe_rel_path(rel_path)
        if target_rel is None:
            return PathFenceMaterializationResult(wrote_any=False, rejection_reason=f"invalid fallback path: {rel_path}")
        target_abs = (workspace / target_rel).resolve()
        if not _is_within_workspace(path=target_abs, workspace=workspace_root):
            return PathFenceMaterializationResult(
                wrote_any=False,
                rejection_reason=f"fallback escaped workspace: {target_rel.as_posix()}",
            )
        if not body.strip() or _looks_like_status_update_summary(body):
            return PathFenceMaterializationResult(
                wrote_any=False,
                rejection_reason=f"fallback for {target_rel.as_posix()} was not a full file body",
            )
        content = body if body.endswith("\n") else f"{body}\n"
        existing = target_abs.read_text(encoding="utf-8") if target_abs.exists() else None
        if existing == content:
            continue
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        target_abs.write_text(content, encoding="utf-8")
        wrote_any = True
    if not wrote_any:
        return PathFenceMaterializationResult(
            wrote_any=False,
            rejection_reason="fallback contained no material file-body changes",
        )
    return PathFenceMaterializationResult(wrote_any=True)


def _allows_artifact_synthesis(task_spec: HealerTaskSpec) -> bool:
    if not task_spec.output_targets:
        return False
    if task_spec.validation_profile == "artifact_only":
        return True
    if task_spec.task_kind in {"research", "docs"}:
        return all(_is_artifact_path(path) for path in task_spec.output_targets)
    return False


def _extract_artifact_content(
    *,
    text: str,
    target_path: Path,
    path_fenced_bodies: dict[str, str] | None = None,
    require_explicit_path: bool = False,
) -> str:
    recovered = _recover_artifact_from_diff(text=text, target_path=target_path)
    if recovered:
        return recovered
    target_key = target_path.as_posix()
    path_fenced_bodies = path_fenced_bodies or {}
    if target_key in path_fenced_bodies:
        return path_fenced_bodies[target_key]
    if require_explicit_path:
        return ""
    suffix = target_path.suffix.lower()
    preferred_langs = _preferred_languages_for_suffix(suffix)
    best_match = ""
    fallback_match = ""
    for match in _FENCED_BLOCK_RE.finditer(text):
        lang = str(match.group("lang") or "").strip().lower().split(" ", 1)[0]
        body = str(match.group("body") or "").strip("\n")
        if not body:
            continue
        if lang == "diff":
            continue
        if not fallback_match:
            fallback_match = body
        if lang in preferred_langs:
            best_match = body
            break
    if best_match:
        return best_match
    if fallback_match:
        return fallback_match
    return text.strip()


def _extract_path_fenced_bodies(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in _FENCED_BLOCK_RE.finditer(text or ""):
        header = str(match.group("lang") or "").strip()
        body = str(match.group("body") or "").strip("\n")
        if not header or not body:
            continue
        lang = header.lower().split(" ", 1)[0]
        if lang == "diff":
            continue
        path_match = _FENCE_PATH_RE.search(header)
        if path_match is None:
            continue
        raw_path = str(path_match.group("path") or "").strip().strip("\"'")
        rel = _safe_rel_path(raw_path)
        if rel is None:
            continue
        out[rel.as_posix()] = body
    return out


def _looks_like_status_update_summary(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    narrative_prefixes = ("updated ", "created ", "added ", "wrote ", "fixed ", "changed ", "implemented ")
    if lowered.startswith(narrative_prefixes):
        if any(
            phrase in lowered
            for phrase in (
                "ran tests",
                "did not run tests",
                "this should work now",
                "should work now",
                "requested note",
                "requested change",
                "requested update",
            )
        ):
            return True
    if "i did not run tests" in lowered or "artifact_only" in lowered:
        if lowered.startswith(narrative_prefixes):
            return True
        if lowered.startswith(tuple(f"{prefix}[" for prefix in narrative_prefixes)):
            return True
    if lowered.startswith(tuple(f"{prefix}[" for prefix in narrative_prefixes)) and " with " in lowered:
        return True
    return False


def _is_no_workspace_change_failure_class(failure_class: str) -> bool:
    normalized = str(failure_class or "").strip()
    return normalized == "no_workspace_change" or normalized.startswith(_NO_WORKSPACE_CHANGE_CLASS_PREFIX)


def _classify_workspace_edit_noop(
    *,
    proposer_output: str,
    turn_result: ConnectorTurnResult,
    path_fence_rejection_reason: str,
    stage_excluded_paths: list[str],
    task_spec: HealerTaskSpec,
) -> tuple[str, str]:
    if stage_excluded_paths:
        unique_paths = sorted({str(path).strip() for path in stage_excluded_paths if str(path).strip()})
        preview = ", ".join(unique_paths[:5])
        if len(unique_paths) > 5:
            preview += ", ..."
        return (
            "no_workspace_change:staging_filtered_all",
            "Workspace edits landed, but staging filtered all changes as generated/runtime artifacts"
            + (f": {preview}" if preview else "."),
        )
    if path_fence_rejection_reason:
        return (
            "no_workspace_change:artifact_not_materialized",
            f"Agent returned exact-target fallback output, but it was rejected: {path_fence_rejection_reason}.",
        )
    text = (proposer_output or "").strip()
    if _allows_artifact_synthesis(task_spec) and text and not _contains_diff_fence(text) and not _looks_like_status_update_summary(text):
        return (
            "no_workspace_change:artifact_not_materialized",
            "Artifact-capable task returned plain output, but no material artifact was written to output targets.",
        )
    if _looks_like_status_update_summary(text):
        return (
            "no_workspace_change:narrative_only",
            "Agent returned a status summary without leaving workspace edits or exact target file bodies.",
        )
    if turn_result.final_answer_present and text:
        return (
            "no_workspace_change:narrative_only",
            "Agent returned a final answer, but it did not leave workspace edits or exact target file bodies.",
        )
    if turn_result.commentary_tail:
        return (
            "no_workspace_change:connector_noop",
            "Agent stayed in commentary mode and did not leave workspace edits or exact target file bodies.",
        )
    return (
        "no_workspace_change:connector_noop",
        "Agent completed the turn without producing durable workspace edits in the managed workspace.",
    )


def _recover_artifact_from_diff(*, text: str, target_path: Path) -> str:
    diff_text = _extract_diff_block(text)
    if not diff_text.strip():
        return ""
    target_posix = target_path.as_posix()
    current_target = ""
    in_hunk = False
    is_new_file = False
    collected: list[str] = []
    for raw in diff_text.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("diff --git "):
            in_hunk = False
            is_new_file = False
            current_target = ""
            parts = line.split(" ")
            if len(parts) >= 4:
                b_path = parts[3]
                if b_path.startswith("b/"):
                    current_target = b_path[2:]
            continue
        if current_target != target_posix:
            continue
        if line.startswith("new file mode "):
            is_new_file = True
            continue
        if line.startswith("@@ "):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        if is_new_file:
            if line.startswith("+"):
                collected.append(line[1:])
            continue
        if line.startswith(" "):
            collected.append(line[1:])
            continue
        if line.startswith("+"):
            collected.append(line[1:])
            continue
    if not collected:
        return ""
    return "\n".join(collected).strip("\n")


def _preferred_languages_for_suffix(suffix: str) -> set[str]:
    if suffix in {".md", ".mdx"}:
        return {"markdown", "md", "mdx", "text", "txt"}
    if suffix in {".rst"}:
        return {"rst", "text", "txt"}
    if suffix in {".txt"}:
        return {"text", "txt", ""}
    if suffix in {".json"}:
        return {"json"}
    if suffix in {".yml", ".yaml"}:
        return {"yaml", "yml"}
    if suffix in {".toml"}:
        return {"toml"}
    if suffix in {".ini", ".cfg", ".conf"}:
        return {"ini", "cfg", "conf", "text", "txt"}
    return {"", "text", "txt"}


def _safe_rel_path(path: str) -> Path | None:
    candidate = Path(str(path).strip())
    if not candidate.parts or candidate.is_absolute():
        return None
    if any(part == ".." for part in candidate.parts):
        return None
    return candidate


def _is_within_workspace(*, path: Path, workspace: Path) -> bool:
    try:
        path.relative_to(workspace)
        return True
    except ValueError:
        return False


def _is_artifact_path(path: str) -> bool:
    lowered = str(path or "").strip().lower()
    suffix = Path(lowered).suffix
    return lowered.startswith("docs/") or suffix in {".md", ".mdx", ".rst", ".txt"}


def _reset_workspace_after_failed_apply(workspace: Path) -> None:
    subprocess.run(
        ["git", "-C", str(workspace), "reset", "--hard", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _build_docker_test_script(command: list[str], strategy: LanguageStrategy | None = None) -> str:
    active_strategy = strategy or get_strategy("unknown")
    parts: list[str] = []
    if active_strategy.docker_install_cmd:
        parts.append(active_strategy.docker_install_cmd)
    parts.append(" ".join(_shell_quote(part) for part in command))
    return " && ".join(parts)


def _shell_quote(value: str) -> str:
    return json.dumps(value)


def _normalize_test_gate_mode(mode: str) -> str:
    candidate = str(mode or "").strip().lower().replace("-", "_")
    if candidate in {"docker_only", "local_only", "local_then_docker"}:
        return candidate
    return "local_then_docker"


def _normalize_completion_artifact_mode(mode: str) -> str:
    candidate = str(mode or "").strip().lower()
    if candidate in _COMPLETION_ARTIFACT_MODES:
        return candidate
    return "fallback_only"


def _normalize_local_gate_policy(policy: str) -> str:
    candidate = str(policy or "").strip().lower().replace("-", "_")
    if candidate in {"auto", "skip", "force"}:
        return candidate
    return "auto"


def _annotate_completion_artifact_parser(
    workspace_status: dict[str, Any],
    *,
    mode: str,
    confidence: float,
    source: str = "",
    reason: str = "",
) -> None:
    workspace_status["completion_artifact_parser_mode"] = mode
    workspace_status["completion_artifact_parser_confidence"] = round(max(0.0, min(1.0, float(confidence))), 2)
    if source:
        workspace_status["completion_artifact_parser_source"] = source
    elif "completion_artifact_parser_source" in workspace_status:
        workspace_status.pop("completion_artifact_parser_source", None)
    if reason:
        workspace_status["completion_artifact_parser_reason"] = reason
    elif "completion_artifact_parser_reason" in workspace_status:
        workspace_status.pop("completion_artifact_parser_reason", None)


def _annotate_app_runtime_status(
    workspace_status: dict[str, Any],
    app_runtime_status: dict[str, Any],
) -> None:
    runtime_copy = dict(app_runtime_status or {})
    workspace_status["app_runtime"] = runtime_copy
    workspace_status["runtime_summary"] = {"app_harness": runtime_copy}


def _app_runtime_process_metadata(
    *,
    profile: AppRuntimeProfile,
    pid: int,
) -> dict[str, Any]:
    return {
        "pid": int(pid),
        "profile": profile.name,
        "command": list(profile.command),
        "cwd": str(profile.cwd),
    }


def _annotate_browser_failure_family(
    summary: dict[str, Any],
    *,
    failure_class: str,
    failure_reason: str | None,
) -> dict[str, Any]:
    enriched = dict(summary or {})
    family = _browser_failure_family(failure_class=failure_class, failure_reason=failure_reason)
    if family:
        enriched["browser_failure_family"] = family
    return enriched


def _browser_failure_family(*, failure_class: str, failure_reason: str | None) -> str:
    normalized_class = str(failure_class or "").strip().lower()
    normalized_reason = str(failure_reason or "").strip().lower()
    if normalized_class == "app_runtime_boot_failed":
        return "runtime_boot"
    if normalized_class in {
        "app_runtime_profile_invalid",
        "app_runtime_profile_missing",
        "browser_runtime_missing",
    }:
        return "runtime_readiness"
    if normalized_class == "artifacts_missing":
        return "artifact_publish"
    if normalized_class == "browser_repro_failed":
        return "journey_step"
    if normalized_class == "browser_step_failed":
        if any(
            needle in normalized_reason
            for needle in (
                "artifact capture",
                "capture failed",
                "console log",
                "network log",
                "screenshot",
                "video",
            )
        ):
            return "artifact_capture"
        return "journey_step"
    return ""


def _annotate_test_summary_runtime(
    summary: dict[str, Any],
    *,
    workspace_status: dict[str, Any],
    task_spec: HealerTaskSpec,
) -> dict[str, Any]:
    enriched = dict(summary or {})
    runtime_summary = workspace_status.get("runtime_summary")
    if isinstance(runtime_summary, dict) and runtime_summary:
        enriched["runtime_summary"] = dict(runtime_summary)
    if task_spec.artifact_requirements:
        enriched["artifact_requirements"] = list(task_spec.artifact_requirements)
    browser_evidence_required = bool(task_spec.repro_steps) and any(
        (
            task_spec.app_target,
            task_spec.entry_url,
            task_spec.runtime_profile,
        )
    )
    if browser_evidence_required:
        enriched["browser_evidence_required"] = True
        phase_states = enriched.get("phase_states")
        phase_state_map = dict(phase_states) if isinstance(phase_states, dict) else {}
        phase_state_map["browser_evidence_required"] = True
        enriched["phase_states"] = phase_state_map
    return enriched


def _annotate_test_summary_browser_artifacts(
    summary: dict[str, Any],
    *,
    artifact_bundle: dict[str, Any],
    artifact_links: list[dict[str, Any]],
) -> dict[str, Any]:
    enriched = dict(summary or {})
    if artifact_bundle:
        enriched["artifact_bundle"] = dict(artifact_bundle)
    if artifact_links:
        enriched["artifact_links"] = [dict(link) for link in artifact_links]
    if bool(enriched.get("browser_evidence_required")):
        artifact_proof_ready = bool(artifact_bundle) and _browser_artifacts_ready(artifact_bundle)
        enriched["artifact_proof_ready"] = artifact_proof_ready
        phase_states = enriched.get("phase_states")
        phase_state_map = dict(phase_states) if isinstance(phase_states, dict) else {}
        phase_state_map["artifact_proof_ready"] = artifact_proof_ready
        phase_state_map["artifacts_missing"] = not artifact_proof_ready
        enriched["phase_states"] = phase_state_map
    return enriched


def _browser_repro_stability(
    *,
    initial: BrowserJourneyResult,
    replay: BrowserJourneyResult,
) -> dict[str, Any]:
    replay_reproduced = not replay.passed and replay.expected_failure_observed
    payload = {
        "checked": True,
        "reproduced_on_first_run": (not initial.passed and initial.expected_failure_observed),
        "reproduced_on_replay": replay_reproduced,
        "initial_phase": initial.phase,
        "replay_phase": replay.phase,
    }
    if replay.failure_step:
        payload["replay_failure_step"] = replay.failure_step
    if replay.error:
        payload["replay_error"] = replay.error
    if replay.screenshot_path:
        payload["replay_screenshot_path"] = replay.screenshot_path
    return payload


def _normalize_app_runtime_profiles(value: Any) -> dict[str, AppRuntimeProfile]:
    normalized: dict[str, AppRuntimeProfile] = {}
    if isinstance(value, dict):
        items = list(value.items())
    elif isinstance(value, list):
        items = [
            (str(item.get("name") or ""), item)
            for item in value
            if isinstance(item, dict)
        ]
    else:
        items = []

    for raw_name, raw_profile in items:
        profile = _coerce_app_runtime_profile(raw_name=raw_name, raw_profile=raw_profile)
        if profile is not None:
            normalized[profile.name] = profile
    return normalized


def _coerce_app_runtime_profile(*, raw_name: str, raw_profile: Any) -> AppRuntimeProfile | None:
    if isinstance(raw_profile, AppRuntimeProfile):
        profile_name = str(raw_profile.name or raw_name).strip()
        if not profile_name:
            return None
        return AppRuntimeProfile(
            name=profile_name,
            command=tuple(raw_profile.command),
            cwd=Path(raw_profile.cwd),
            env=dict(raw_profile.env or {}),
            install_command=tuple(getattr(raw_profile, "install_command", ()) or ()),
            install_marker_path=str(getattr(raw_profile, "install_marker_path", "") or ""),
            fixture_driver_command=tuple(getattr(raw_profile, "fixture_driver_command", ()) or ()),
            readiness_url=raw_profile.readiness_url,
            readiness_log_text=raw_profile.readiness_log_text,
            browser=raw_profile.browser,
            headless=bool(raw_profile.headless),
            viewport=dict(raw_profile.viewport or {}) or None,
            device=raw_profile.device,
            startup_timeout_seconds=float(raw_profile.startup_timeout_seconds),
            shutdown_timeout_seconds=float(raw_profile.shutdown_timeout_seconds),
            poll_interval_seconds=float(raw_profile.poll_interval_seconds),
        )
    if not isinstance(raw_profile, dict):
        return None

    profile_name = str(raw_profile.get("name") or raw_name).strip()
    if not profile_name:
        return None
    command = _normalize_app_runtime_command(
        raw_profile.get("command") or raw_profile.get("start_command") or raw_profile.get("boot_command")
    )
    cwd_value = raw_profile.get("cwd") or raw_profile.get("working_directory") or "."
    readiness_url = str(raw_profile.get("readiness_url") or raw_profile.get("ready_url") or "").strip() or None
    readiness_log_text = (
        str(raw_profile.get("readiness_log_text") or raw_profile.get("ready_log_text") or "").strip() or None
    )
    env_value = raw_profile.get("env") if isinstance(raw_profile.get("env"), dict) else None
    viewport_value = raw_profile.get("viewport") if isinstance(raw_profile.get("viewport"), dict) else None
    return AppRuntimeProfile(
        name=profile_name,
        command=command,
        cwd=Path(str(cwd_value or ".")).expanduser(),
        env={str(key): str(value) for key, value in dict(env_value or {}).items()},
        install_command=_normalize_app_runtime_command(raw_profile.get("install_command")),
        install_marker_path=str(raw_profile.get("install_marker_path") or "").strip(),
        fixture_driver_command=_normalize_app_runtime_command(raw_profile.get("fixture_driver_command")),
        readiness_url=readiness_url,
        readiness_log_text=readiness_log_text,
        browser=str(raw_profile.get("browser") or "").strip(),
        headless=_coerce_bool(raw_profile.get("headless"), default=True),
        viewport=_coerce_viewport(viewport_value),
        device=str(raw_profile.get("device") or "").strip(),
        startup_timeout_seconds=_coerce_float(raw_profile.get("startup_timeout_seconds"), default=30.0),
        shutdown_timeout_seconds=_coerce_float(raw_profile.get("shutdown_timeout_seconds"), default=10.0),
        poll_interval_seconds=_coerce_float(raw_profile.get("poll_interval_seconds"), default=0.1),
    )


def _normalize_app_runtime_command(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part for part in shlex.split(value) if part)
    if isinstance(value, (list, tuple)):
        return tuple(str(part).strip() for part in value if str(part).strip())
    return ()


def _coerce_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in {"1", "true", "yes", "on"}:
            return True
        if candidate in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_viewport(value: dict[str, Any] | None) -> dict[str, int] | None:
    if not value:
        return None
    normalized: dict[str, int] = {}
    for key in ("width", "height"):
        try:
            normalized[key] = int(value[key])
        except (KeyError, TypeError, ValueError):
            continue
    return normalized or None


def _browser_profile_summary(profile: AppRuntimeProfile) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "browser": profile.browser,
        "headless": bool(profile.headless),
    }
    if profile.device:
        summary["device"] = profile.device
    if profile.viewport:
        summary["viewport"] = dict(profile.viewport)
    return summary


def _browser_phase_payload(result: BrowserJourneyResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "phase": result.phase,
        "passed": bool(result.passed),
        "expected_failure_observed": bool(result.expected_failure_observed),
        "final_url": result.final_url,
        "transcript": [dict(entry) for entry in result.transcript],
    }
    if result.failure_step:
        payload["failure_step"] = result.failure_step
    if result.error:
        payload["error"] = result.error
    if result.screenshot_path:
        payload["screenshot_path"] = result.screenshot_path
    if result.video_path:
        payload["video_path"] = result.video_path
    if result.console_log_path:
        payload["console_log_path"] = result.console_log_path
    if result.network_log_path:
        payload["network_log_path"] = result.network_log_path
    return payload


def _browser_artifact_bundle(
    *,
    profile: AppRuntimeProfile,
    entry_url: str,
    session_root: str = "",
    failure_journey: BrowserJourneyResult | None = None,
    resolution_journey: BrowserJourneyResult | None = None,
) -> dict[str, Any]:
    bundle_status = "partial"
    if failure_journey is not None and resolution_journey is not None:
        bundle_status = "captured"
    bundle: dict[str, Any] = {
        "status": bundle_status,
        "browser_profile": _browser_profile_summary(profile),
        "entry_url": entry_url,
    }
    normalized_session_root = str(session_root or "").strip()
    if normalized_session_root:
        bundle["browser_session_root"] = normalized_session_root
    journey_transcript: list[dict[str, Any]] = []
    if failure_journey is not None:
        bundle["failure_artifacts"] = _browser_phase_payload(failure_journey)
        journey_transcript.append(
            {
                "phase": failure_journey.phase,
                "transcript": [dict(entry) for entry in failure_journey.transcript],
            }
        )
    if resolution_journey is not None:
        bundle["resolution_artifacts"] = _browser_phase_payload(resolution_journey)
        journey_transcript.append(
            {
                "phase": resolution_journey.phase,
                "transcript": [dict(entry) for entry in resolution_journey.transcript],
            }
        )
    if journey_transcript:
        bundle["journey_transcript"] = journey_transcript
    artifact_dirs: list[str] = []
    for result in (failure_journey, resolution_journey):
        if result is None:
            continue
        for path_value in (
            result.screenshot_path,
            result.video_path,
            result.console_log_path,
            result.network_log_path,
        ):
            path_text = str(path_value or "").strip()
            if not path_text:
                continue
            artifact_dirs.append(str(Path(path_text).expanduser().resolve().parent))
    if artifact_dirs:
        bundle["artifact_root"] = os.path.commonpath(artifact_dirs)
    if failure_journey is not None and resolution_journey is not None and not _browser_artifacts_ready(bundle):
        bundle["status"] = "artifacts_missing"
    return bundle


def _browser_artifact_links(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for phase_name in ("failure", "resolution"):
        phase_payload = bundle.get(f"{phase_name}_artifacts")
        if not isinstance(phase_payload, dict):
            continue
        for field_name, label_suffix in (
            ("screenshot_path", "screenshot"),
            ("video_path", "video"),
            ("console_log_path", "console_log"),
            ("network_log_path", "network_log"),
        ):
            path = str(phase_payload.get(field_name) or "").strip()
            if not path:
                continue
            if not Path(path).exists():
                continue
            links.append({"label": f"{phase_name}_{label_suffix}", "path": path})
    return links


def _browser_bundle_phase_result(bundle: dict[str, Any], *, phase: str) -> BrowserJourneyResult | None:
    phase_payload = bundle.get(f"{phase}_artifacts")
    if not isinstance(phase_payload, dict):
        return None
    transcript = phase_payload.get("transcript")
    return BrowserJourneyResult(
        phase=str(phase_payload.get("phase") or phase),
        passed=bool(phase_payload.get("passed")),
        expected_failure_observed=bool(phase_payload.get("expected_failure_observed")),
        final_url=str(phase_payload.get("final_url") or ""),
        failure_step=str(phase_payload.get("failure_step") or ""),
        error=str(phase_payload.get("error") or ""),
        screenshot_path=str(phase_payload.get("screenshot_path") or ""),
        video_path=str(phase_payload.get("video_path") or ""),
        console_log_path=str(phase_payload.get("console_log_path") or ""),
        network_log_path=str(phase_payload.get("network_log_path") or ""),
        transcript=tuple(dict(entry) for entry in transcript) if isinstance(transcript, list) else (),
    )


def _browser_artifacts_ready(bundle: dict[str, Any]) -> bool:
    return not _browser_missing_artifacts(bundle)


def _browser_phase_artifacts_ready(bundle: dict[str, Any], *, phase: str) -> bool:
    return not _browser_phase_missing_artifacts(bundle, phase=phase)


def _browser_missing_artifacts(bundle: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for phase_name in ("failure_artifacts", "resolution_artifacts"):
        missing.extend(_browser_phase_missing_artifacts(bundle, phase=phase_name))
    return missing


def _browser_phase_missing_artifacts(bundle: dict[str, Any], *, phase: str) -> list[str]:
    phase_payload = bundle.get(phase)
    if not isinstance(phase_payload, dict):
        phase_prefix = phase.replace("_artifacts", "")
        return [f"{phase_prefix}_screenshot"]

    missing: list[str] = []
    raw_path = str(phase_payload.get("screenshot_path") or "").strip()
    if not raw_path:
        missing.append(f"{phase.replace('_artifacts', '')}_screenshot")
    elif not Path(raw_path).exists():
        missing.append(f"{phase.replace('_artifacts', '')}_screenshot")
    return missing


def _gate_runners_for_mode(mode: str) -> list[tuple[str, Any]]:
    if mode == "local_only":
        return [("local", _run_pytest_locally)]
    if mode == "docker_only":
        return [("docker", _run_pytest_in_docker)]
    return [
        ("local", _run_pytest_locally),
        ("docker", _run_pytest_in_docker),
    ]


def _run_tests_locally_gate(
    workspace: Path,
    command: list[str],
    timeout_seconds: int,
    *,
    strategy: LanguageStrategy | None = None,
    local_gate_policy: str = "auto",
) -> dict[str, Any]:
    return _run_tests_locally(
        workspace,
        command,
        timeout_seconds,
        strategy=strategy or get_strategy("unknown"),
        local_gate_policy=_normalize_local_gate_policy(local_gate_policy),
    )


def _run_tests_in_docker_gate(
    workspace: Path,
    command: list[str],
    timeout_seconds: int,
    *,
    strategy: LanguageStrategy | None = None,
    local_gate_policy: str = "auto",
) -> dict[str, Any]:
    return _run_tests_in_docker(
        workspace,
        command,
        timeout_seconds,
        strategy=strategy or get_strategy("unknown"),
        local_gate_policy=_normalize_local_gate_policy(local_gate_policy),
    )


# Preserve old names as aliases for backward compatibility in tests.
_run_pytest_locally = _run_tests_locally_gate
_run_pytest_in_docker = _run_tests_in_docker_gate
