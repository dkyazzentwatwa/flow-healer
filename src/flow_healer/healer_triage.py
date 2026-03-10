from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .skill_contracts import (
    default_action_for_diagnosis,
    next_skill_in_graph,
    previous_skill_in_graph,
    recommended_skill_for_diagnosis,
    skill_playbook,
    skill_stage_position,
)


@dataclass(slots=True, frozen=True)
class DiagnosisRoute:
    diagnosis: str
    failure_family: str
    recommended_skill: str
    default_action: str
    graph_position: int
    previous_skill: str
    next_skill: str
    skill_relative_path: str
    default_command_preview: str
    key_output_fields: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    stop_recommended: bool
    stop_reason: str
    connector_debug_focus: str
    connector_debug_checks: tuple[str, ...]


_CONNECTOR_FAILURE_CLASSES = {
    "connector_unavailable",
    "connector_runtime_error",
    "diff_limit_exceeded",
    "empty_diff",
    "malformed_diff",
    "no_patch",
    "no_code_diff",
    "patch_apply_failed",
    "generated_artifact_contamination",
    "verifier_failed",
}
_FIXTURE_FAILURE_MARKERS = (
    "no module named",
    "error collecting",
    "fixture",
    "importerror",
    "modulenotfounderror",
)
_PROCESS_FAILURE_CLASSES = {
    "lease_expired",
    "lock_conflict",
    "lock_upgrade_conflict",
    "preflight_failed",
    "push_failed",
    "push_non_fast_forward",
    "pr_open_failed",
    "workspace_corrupt",
}
_EXTERNAL_FAILURE_MARKERS = (
    "github",
    "gh auth",
    "api rate limit",
    "rate limit",
    "network",
    "timeout waiting for github",
)
_INFRA_DOMAIN_FAILURE_CLASSES = {
    "connector_runtime_error",
    "connector_unavailable",
    "github_api_error",
    "github_auth_missing",
    "github_network_error",
    "github_rate_limited",
    "infra_pause",
    "lease_expired",
    "lock_conflict",
    "lock_upgrade_conflict",
    "preflight_failed",
    "pr_open_failed",
    "push_failed",
    "push_non_fast_forward",
    "workspace_corrupt",
}
_CONTRACT_DOMAIN_FAILURE_CLASSES = {
    "diff_limit_exceeded",
    "empty_diff",
    "malformed_diff",
    "no_code_diff",
    "no_patch",
    "patch_apply_failed",
}
_INFRA_REASON_MARKERS = (
    "api rate limit",
    "cannot connect to the docker daemon",
    "connectorruntimeerror",
    "connectorunavailable",
    "docker daemon",
    "github",
    "network",
    "permission denied",
    "service unavailable",
    "timed out",
    "unable to resolve",
    "workspace unavailable",
)
_CONTRACT_REASON_MARKERS = (
    "diff fence",
    "did not return a unified diff",
    "empty diff",
    "invalid json",
    "malformed diff",
    "missing hunk header",
    "no workspace change",
    "patch apply",
    "payload",
    "unified diff",
    "verdict",
)


def classify_failure(issue: dict[str, Any] | None, attempt: dict[str, Any] | None) -> str:
    failure_class = str((attempt or {}).get("failure_class") or (issue or {}).get("last_failure_class") or "")
    failure_reason = str((attempt or {}).get("failure_reason") or (issue or {}).get("last_failure_reason") or "").lower()
    state = str((issue or {}).get("state") or "")

    if failure_class == "verifier_failed":
        if any(marker in failure_reason for marker in ("invalid json", "json", "verdict", "payload")):
            return "connector_or_patch_generation"
        return "product_bug"
    if failure_class in _CONNECTOR_FAILURE_CLASSES or _is_no_workspace_change_failure_class(failure_class):
        return "connector_or_patch_generation"
    if failure_class in _PROCESS_FAILURE_CLASSES:
        return "automation_or_process"
    if "connectorunavailable" in failure_reason or "connectorruntimeerror" in failure_reason:
        return "connector_or_patch_generation"
    if failure_class == "tests_failed":
        if any(marker in failure_reason for marker in _FIXTURE_FAILURE_MARKERS):
            return "repo_fixture_or_setup"
        if any(marker in failure_reason for marker in _EXTERNAL_FAILURE_MARKERS):
            return "automation_or_process"
        return "product_bug"
    if state == "queued" and str((issue or {}).get("backoff_until") or ""):
        return "product_bug"
    if any(marker in failure_reason for marker in _EXTERNAL_FAILURE_MARKERS):
        return "external_service_or_github"
    return "product_bug" if failure_class else "operator_or_environment"


def classify_failure_family(issue: dict[str, Any] | None, attempt: dict[str, Any] | None) -> str:
    diagnosis = classify_failure(issue, attempt)
    if diagnosis == "connector_or_patch_generation":
        return "connector_patch"
    if diagnosis == "product_bug":
        return "product"
    return "automation_process"


def classify_failure_domain(*, failure_class: str, failure_reason: str) -> str:
    normalized_class = str(failure_class or "").strip()
    normalized_reason = str(failure_reason or "").strip().lower()
    if normalized_class in _INFRA_DOMAIN_FAILURE_CLASSES:
        return "infra"
    if _is_no_workspace_change_failure_class(normalized_class):
        return "contract"
    if normalized_class in _CONTRACT_DOMAIN_FAILURE_CLASSES:
        return "contract"
    if any(marker in normalized_reason for marker in _INFRA_REASON_MARKERS):
        return "infra"
    if any(marker in normalized_reason for marker in _CONTRACT_REASON_MARKERS):
        return "contract"
    if normalized_class in {"tests_failed", "verifier_failed", "generated_artifact_contamination", "scope_violation"}:
        return "code"
    if not normalized_class:
        return "unknown"
    return "code"


def diagnosis_route(diagnosis: str) -> DiagnosisRoute:
    normalized = str(diagnosis or "").strip().lower()
    recommended = recommended_skill_for_diagnosis(normalized)
    playbook = skill_playbook(recommended)
    return DiagnosisRoute(
        diagnosis=normalized,
        failure_family=_failure_family_for_diagnosis(normalized),
        recommended_skill=recommended,
        default_action=default_action_for_diagnosis(normalized),
        graph_position=skill_stage_position(recommended),
        previous_skill=previous_skill_in_graph(recommended),
        next_skill=next_skill_in_graph(recommended),
        skill_relative_path=str(playbook.get("relative_path") or ""),
        default_command_preview=str(playbook.get("default_command_preview") or ""),
        key_output_fields=tuple(str(item) for item in (playbook.get("key_output_fields") or [])),
        stop_conditions=tuple(str(item) for item in (playbook.get("stop_conditions") or [])),
        stop_recommended=_stop_recommended_for_diagnosis(normalized),
        stop_reason=_stop_reason_for_diagnosis(normalized),
        connector_debug_focus="",
        connector_debug_checks=(),
    )


def classify_issue_route(issue: dict[str, Any] | None, attempt: dict[str, Any] | None) -> DiagnosisRoute:
    diagnosis = classify_failure(issue, attempt)
    route = diagnosis_route(diagnosis)
    if diagnosis != "connector_or_patch_generation":
        return route
    focus = _connector_debug_focus(issue, attempt)
    return DiagnosisRoute(
        diagnosis=route.diagnosis,
        failure_family=route.failure_family,
        recommended_skill=route.recommended_skill,
        default_action=route.default_action,
        graph_position=route.graph_position,
        previous_skill=route.previous_skill,
        next_skill=route.next_skill,
        skill_relative_path=route.skill_relative_path,
        default_command_preview=route.default_command_preview,
        key_output_fields=route.key_output_fields,
        stop_conditions=route.stop_conditions,
        stop_recommended=route.stop_recommended,
        stop_reason=route.stop_reason,
        connector_debug_focus=focus,
        connector_debug_checks=_connector_debug_checks(focus),
    )


def _stop_recommended_for_diagnosis(diagnosis: str) -> bool:
    return diagnosis in {
        "automation_or_process",
        "operator_or_environment",
        "repo_fixture_or_setup",
        "connector_or_patch_generation",
        "product_bug",
        "external_service_or_github",
    }


def _stop_reason_for_diagnosis(diagnosis: str) -> str:
    mapping = {
        "automation_or_process": "Stop before another live run until the automation or process failure is repaired.",
        "operator_or_environment": "Stop before another live run until the local environment is repaired.",
        "repo_fixture_or_setup": "Stop before another live run until the repo or fixture setup is repaired.",
        "connector_or_patch_generation": "Stop before another live run until the connector or patch contract is repaired.",
        "product_bug": "Stop and capture evidence before escalating the product bug.",
        "external_service_or_github": "Stop live mutation until the external dependency recovers or a retry is intentional.",
    }
    return mapping.get(diagnosis, "")


def _failure_family_for_diagnosis(diagnosis: str) -> str:
    normalized = str(diagnosis or "").strip().lower()
    if normalized == "connector_or_patch_generation":
        return "connector_patch"
    if normalized == "product_bug":
        return "product"
    return "automation_process"


def _connector_debug_focus(issue: dict[str, Any] | None, attempt: dict[str, Any] | None) -> str:
    failure_class = str((attempt or {}).get("failure_class") or (issue or {}).get("last_failure_class") or "").strip()
    failure_reason = str((attempt or {}).get("failure_reason") or (issue or {}).get("last_failure_reason") or "").lower()
    if failure_class == "connector_unavailable" or any(
        marker in failure_reason for marker in ("connectorunavailable", "unable to resolve", "not found", "command")
    ):
        return "command_resolution"
    if failure_class == "connector_runtime_error" or any(
        marker in failure_reason for marker in ("connectorruntimeerror", "timed out", "mcp startup", "transport channel closed")
    ):
        return "runtime_crash"
    if failure_class == "no_patch" or any(
        marker in failure_reason for marker in ("no patch", "empty diff", "empty output", "no unified diff")
    ):
        return "empty_diff"
    if failure_class == "empty_diff":
        return "empty_diff"
    if failure_class == "malformed_diff" or any(
        marker in failure_reason for marker in ("malformed diff", "invalid patch syntax", "missing hunk header")
    ):
        return "diff_fence"
    if _is_no_workspace_change_failure_class(failure_class) or any(
        marker in failure_reason for marker in ("no workspace change", "did not edit files", "no file edits")
    ):
        return "empty_diff"
    if failure_class == "patch_apply_failed" or any(
        marker in failure_reason for marker in ("git apply", "patch apply", "corrupt patch", "reject")
    ):
        return "patch_apply"
    if failure_class == "no_code_diff" or any(
        marker in failure_reason for marker in ("docs-only", "artifact-only", "code-change task produced only")
    ):
        return "contract_comparison"
    if failure_class == "verifier_failed" or any(
        marker in failure_reason for marker in ("invalid json", "json", "verdict", "payload")
    ):
        return "verifier_payload"
    if failure_class == "diff_limit_exceeded" or any(
        marker in failure_reason for marker in ("diff fence", "fenced block", "```diff", "malformed diff")
    ):
        return "diff_fence"
    return "contract_comparison"


def _connector_debug_checks(focus: str) -> tuple[str, ...]:
    mapping = {
        "command_resolution": (
            "Validate connector command resolution",
            "Confirm the configured binary or wrapper is executable",
            "Capture the resolved command and invocation path before retrying",
        ),
        "runtime_crash": (
            "Rerun the connector against a fixed prompt fixture",
            "Capture stdout/stderr tails and timeout signals",
            "Confirm whether startup or prompt execution is crashing first",
        ),
        "empty_diff": (
            "Detect empty diff output before any patch-apply step",
            "Confirm the proposer returned real file edits or a unified diff",
            "Compare proposer output against the expected code-change contract",
        ),
        "diff_fence": (
            "Validate diff fence validity",
            "Confirm the fenced block contains a unified diff with real hunk headers",
            "Capture the raw patch text before retrying or applying",
        ),
        "patch_apply": (
            "Reproduce patch application with the raw patch output",
            "Capture the exact patch-apply failure from git apply or downstream parsing",
            "Confirm the diff matches the current workspace paths and context",
        ),
        "verifier_payload": (
            "Validate any verifier payload as JSON",
            "Confirm the expected verdict and summary fields are present",
            "Compare verifier output with the expected strict JSON contract",
        ),
        "contract_comparison": (
            "Compare proposer and verifier contracts",
            "Identify which stage first diverged from the expected format",
            "Hand off to the owning connector stage once the broken contract is isolated",
        ),
    }
    return mapping.get(focus, ())


def _is_no_workspace_change_failure_class(failure_class: str) -> bool:
    normalized = str(failure_class or "").strip()
    return normalized == "no_workspace_change" or normalized.startswith("no_workspace_change:")
