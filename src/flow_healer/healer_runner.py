from __future__ import annotations

import json
import inspect
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

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
        self.auto_clean_generated_artifacts = bool(auto_clean_generated_artifacts)
        self.max_proposer_retries = 1
        self.max_code_proposer_retries = 3
        self.max_artifact_proposer_retries = 2
        self.code_change_turn_timeout_seconds = max(900, self.timeout_seconds)
        # Allow one cleanup before validation and one more after validation if tests regenerate artifacts.
        self.max_generated_artifact_cleanup_cycles = 2

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
        cleanup_cycles_used = 0
        sender = f"healer:{issue_id}"
        thread_id = self.connector.get_or_create_thread(sender)
        workspace_edit_mode = _prefers_workspace_edits(connector=self.connector, task_spec=task_spec)
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
            if _stage_workspace_changes(
                workspace,
                issue_title=issue_title,
                issue_body=issue_body,
                task_spec=task_spec,
                language=resolved_execution.language_effective,
            ):
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
                if path_fence_result.wrote_any and _stage_workspace_changes(
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
                ) and _stage_workspace_changes(
                    workspace,
                    issue_title=issue_title,
                    issue_body=issue_body,
                    task_spec=task_spec,
                    language=resolved_execution.language_effective,
                ):
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
                failure_class, failure_reason = _classify_non_patch_failure(proposer_output)
                failure_reason = _augment_failure_reason_with_connector_health(
                    connector=self.connector,
                    failure_class=failure_class,
                    failure_reason=failure_reason,
                )
                if failure_class not in _NON_RETRYABLE_FAILURES:
                    failure_class = "no_workspace_change"
                    failure_reason = _workspace_edit_failure_reason(
                        proposer_output=proposer_output,
                        turn_result=turn_result,
                        path_fence_rejection_reason=path_fence_result.rejection_reason,
                    )
                    if no_workspace_change_retries_used >= 1:
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
                same_thread_retry = failure_class == "no_workspace_change"
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
                    )
                    continue
                patch_path = workspace / ".apple-flow-healer.patch"
                patch_path.write_text(patch, encoding="utf-8")
                try:
                    apply_proc = subprocess.run(
                        ["git", "-C", str(workspace), "apply", "--index", "--reject", str(patch_path)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout_seconds,
                    )
                finally:
                    if patch_path.exists():
                        patch_path.unlink(missing_ok=True)
                if apply_proc.returncode == 0 and _stage_workspace_changes(
                    workspace,
                    issue_title=issue_title,
                    issue_body=issue_body,
                    task_spec=task_spec,
                    language=resolved_execution.language_effective,
                ):
                    break
                failure_class = "patch_apply_failed"
                failure_reason = (apply_proc.stderr or apply_proc.stdout or "git apply failed").strip()[:500]
                _reset_workspace_after_failed_apply(workspace)
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
                failure_class="no_workspace_change",
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
            _annotate_completion_artifact_parser(
                workspace_status,
                mode=completion_parser_mode,
                confidence=completion_parser_confidence,
                source=completion_parser_source,
                reason=completion_parser_reason,
            )
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
            diff_paths = _changed_paths(workspace)
            diff_files, diff_lines = _diff_stats(workspace)
            if not diff_paths:
                return HealerRunResult(
                    success=False,
                    failure_class="no_workspace_change",
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
            test_summary = _with_workspace_status(
                test_summary,
                workspace_status=workspace_status,
                failure_fingerprint="",
            )
        _annotate_completion_artifact_parser(
            workspace_status,
            mode=completion_parser_mode,
            confidence=completion_parser_confidence,
            source=completion_parser_source,
            reason=completion_parser_reason,
        )
        failed_tests = int(test_summary.get("failed_tests", 0))
        if failed_tests > max_failed_tests_allowed:
            return HealerRunResult(
                success=False,
                failure_class="tests_failed",
                failure_reason=f"Failed tests={failed_tests} exceeds cap={max_failed_tests_allowed}",
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
        effective_language = (
            issue_language
            or (self._language if config_override_allowed else "")
            or execution_detection.language
            or repo_detection.language
        )
        if is_removed_language(effective_language):
            raise UnsupportedLanguageError(
                f"Unsupported language '{effective_language}'. "
                "Flow Healer supports only python, node, and swift."
            )
        if effective_language == "unknown":
            effective_language = ""
        strategy = get_strategy(
            effective_language,
            docker_image=self._docker_image if config_override_allowed else "",
            test_command=self._test_command if config_override_allowed else "",
            install_command=self._install_command if config_override_allowed else "",
        )
        detected_language = execution_detection.language
        if detected_language == "unknown":
            detected_language = repo_detection.language
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
            local_gate_policy=local_gate_policy or self.local_gate_policy,
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
    return summary


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
    if _is_pytest_style_command(local_cmd):
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(workspace) if not existing else f"{workspace}{os.pathsep}{existing}"

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

    status = "passed" if int(proc.returncode) == 0 else "failed"
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return {
        "exit_code": int(proc.returncode),
        "output_tail": output[-2000:],
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
    return _starts_with_any(command, ["pytest"], ["py.test"]) or (
        _starts_with_any(command, ["python"]) and "pytest" in command
    )


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
    bash_script = _build_docker_test_script(command, strategy)
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{workspace}:/workspace",
        "-w",
        "/workspace",
        strategy.docker_image,
        "sh",
        "-c",
        bash_script,
    ]
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
        return {
            "exit_code": 124,
            "output_tail": "(docker gate unavailable: timed out while waiting for docker)",
            "gate_status": "failed",
            "gate_reason": "infra_unavailable",
        }
    status = "passed" if int(proc.returncode) == 0 else "failed"
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    gate_reason = ""
    if status == "failed" and _looks_like_docker_infra_failure(output):
        gate_reason = "infra_unavailable"
    return {
        "exit_code": int(proc.returncode),
        "output_tail": output[-2000:],
        "gate_status": status,
        "gate_reason": gate_reason,
    }


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
) -> str:
    tailored_lines: list[str] = []
    sandbox_scoped = _is_issue_scoped_sandbox(task_spec)
    if failure_class in {"no_patch", "no_workspace_change"}:
        if prefer_workspace_edits:
            tailored_lines.append(
                "You must edit files directly in the managed workspace now. Do not return a diff, plan, or status-only reply."
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
        else:
            tailored_lines.append(
                "You must produce concrete file edits now. Do not return explanations, plans, or summaries."
            )
            tailored_lines.append(
                "If direct edits are unavailable, return exactly one valid unified diff fenced block (```diff ... ```)."
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
) -> str:
    sections = [
        "### Role And Trusted Inputs\n"
        "You are the proposer agent for autonomous code healing.\n"
        "Treat the issue title/body, task contract, and loaded input-context files as trusted run instructions.\n"
        + (
            "Operate directly in the checked-out workspace, edit files in place, run the requested validation, and end with a brief operator summary."
            if prefer_workspace_edits
            else "Operate directly in the checked-out workspace and optimize for a valid finished patch, not commentary."
        ),
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
            _output_rules(task_spec, prefer_workspace_edits=prefer_workspace_edits),
            _completion_criteria(task_spec, prefer_workspace_edits=prefer_workspace_edits),
        ]
    )
    return "\n\n".join(section.strip() for section in sections if section.strip())


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
    if failure_class not in {
        "empty_diff",
        "malformed_diff",
        "no_patch",
        "no_workspace_change",
        "patch_apply_failed",
    }:
        return ""
    mode = "workspace_edit" if _prefers_workspace_edits(connector=connector, task_spec=task_spec) else "serialized_patch"
    return f"execution_contract|{mode}|{failure_class}"


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
    for rel_path in diff_paths:
        if not _is_markdown_artifact_path(rel_path):
            continue
        file_path = workspace / rel_path
        if not file_path.exists() or not file_path.is_file():
            continue
        checked_files.append(rel_path)
        broken_links.extend(_find_broken_markdown_links(file_path=file_path, rel_path=rel_path))
    passed = not broken_links
    summary = "Artifact validation passed." if passed else f"Artifact validation failed with {len(broken_links)} broken relative link(s)."
    return {
        "mode": "artifact_validation",
        "passed": passed,
        "failed_tests": 0 if passed else 1,
        "checked_files": checked_files,
        "broken_links": broken_links,
        "summary": summary,
    }


def _is_markdown_artifact_path(path: str) -> bool:
    return Path(path).suffix.lower() in {".md", ".mdx", ".rst", ".txt"}


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
    "swift": {".build", ".swiftpm"},
}
_LOCKFILE_GROUPS = {
    "package-lock.json": {"package.json", "dependency", "dependencies", "lockfile"},
    "pnpm-lock.yaml": {"package.json", "dependency", "dependencies", "lockfile"},
    "yarn.lock": {"package.json", "dependency", "dependencies", "lockfile"},
}


def _stage_workspace_changes(
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
    return bool(result.kept_paths)


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
        # npm can regenerate package-lock.json during validation even when lockfile edits
        # are not part of the requested patch. Treat it as tolerated runtime noise.
        return effective_language == "node" and lockfile_name == "package-lock.json"

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
    return enriched


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


def _is_explicit_output_target(path: str, task_spec: HealerTaskSpec | None) -> bool:
    if task_spec is None:
        return False
    normalized = str(path or "").strip().lstrip("./").lower()
    if not normalized:
        return False
    for target in task_spec.output_targets:
        normalized_target = str(target or "").strip().lstrip("./").lower().rstrip("/")
        if not normalized_target:
            continue
        if normalized == normalized_target or normalized.startswith(f"{normalized_target}/"):
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
    if "i did not run tests" in lowered or "artifact_only" in lowered:
        if lowered.startswith(("updated ", "created ", "added ", "wrote ")):
            return True
        if lowered.startswith(("updated [", "created [", "added [", "wrote [")):
            return True
    if lowered.startswith(("updated [", "created [", "added [", "wrote [")) and " with " in lowered:
        return True
    return False


def _workspace_edit_failure_reason(
    *,
    proposer_output: str,
    turn_result: ConnectorTurnResult,
    path_fence_rejection_reason: str,
) -> str:
    if path_fence_rejection_reason:
        return f"Agent returned exact-target fallback output, but it was rejected: {path_fence_rejection_reason}."
    text = (proposer_output or "").strip()
    if _looks_like_status_update_summary(text):
        return "Agent returned a status summary without leaving workspace edits or exact target file bodies."
    if turn_result.final_answer_present and text:
        return "Agent returned a final answer, but it did not leave workspace edits or exact target file bodies."
    if turn_result.commentary_tail:
        return "Agent stayed in commentary mode and did not leave workspace edits or exact target file bodies."
    return "Agent finished without editing files directly in the managed workspace."


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
