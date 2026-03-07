from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .skill_contracts import default_action_for_diagnosis, recommended_skill_for_diagnosis


@dataclass(slots=True, frozen=True)
class DiagnosisRoute:
    diagnosis: str
    recommended_skill: str
    default_action: str
    stop_recommended: bool
    stop_reason: str
    connector_debug_focus: str


_CONNECTOR_FAILURE_CLASSES = {
    "connector_unavailable",
    "connector_runtime_error",
    "diff_limit_exceeded",
    "no_patch",
    "no_code_diff",
    "no_workspace_change",
    "patch_apply_failed",
    "verifier_failed",
}
_FIXTURE_FAILURE_MARKERS = (
    "no module named",
    "error collecting",
    "fixture",
    "importerror",
    "modulenotfounderror",
)
_EXTERNAL_FAILURE_MARKERS = (
    "github",
    "gh auth",
    "api rate limit",
    "rate limit",
    "network",
    "timeout waiting for github",
)


def classify_failure(issue: dict[str, Any] | None, attempt: dict[str, Any] | None) -> str:
    failure_class = str((attempt or {}).get("failure_class") or (issue or {}).get("last_failure_class") or "")
    failure_reason = str((attempt or {}).get("failure_reason") or (issue or {}).get("last_failure_reason") or "").lower()
    state = str((issue or {}).get("state") or "")

    if failure_class in _CONNECTOR_FAILURE_CLASSES:
        return "connector_or_patch_generation"
    if "connectorunavailable" in failure_reason or "connectorruntimeerror" in failure_reason:
        return "connector_or_patch_generation"
    if failure_class == "tests_failed":
        if any(marker in failure_reason for marker in _FIXTURE_FAILURE_MARKERS):
            return "repo_fixture_or_setup"
        return "operator_or_environment"
    if failure_class in {"push_failed", "pr_open_failed"}:
        return "external_service_or_github"
    if state == "queued" and str((issue or {}).get("backoff_until") or ""):
        return "product_bug"
    if any(marker in failure_reason for marker in _EXTERNAL_FAILURE_MARKERS):
        return "external_service_or_github"
    return "product_bug" if failure_class else "operator_or_environment"


def diagnosis_route(diagnosis: str) -> DiagnosisRoute:
    normalized = str(diagnosis or "").strip().lower()
    return DiagnosisRoute(
        diagnosis=normalized,
        recommended_skill=recommended_skill_for_diagnosis(normalized),
        default_action=default_action_for_diagnosis(normalized),
        stop_recommended=_stop_recommended_for_diagnosis(normalized),
        stop_reason=_stop_reason_for_diagnosis(normalized),
        connector_debug_focus="",
    )


def classify_issue_route(issue: dict[str, Any] | None, attempt: dict[str, Any] | None) -> DiagnosisRoute:
    diagnosis = classify_failure(issue, attempt)
    route = diagnosis_route(diagnosis)
    if diagnosis != "connector_or_patch_generation":
        return route
    return DiagnosisRoute(
        diagnosis=route.diagnosis,
        recommended_skill=route.recommended_skill,
        default_action=route.default_action,
        stop_recommended=route.stop_recommended,
        stop_reason=route.stop_reason,
        connector_debug_focus=_connector_debug_focus(issue, attempt),
    )


def _stop_recommended_for_diagnosis(diagnosis: str) -> bool:
    return diagnosis in {
        "operator_or_environment",
        "repo_fixture_or_setup",
        "connector_or_patch_generation",
        "product_bug",
        "external_service_or_github",
    }


def _stop_reason_for_diagnosis(diagnosis: str) -> str:
    mapping = {
        "operator_or_environment": "Stop before another live run until the local environment is repaired.",
        "repo_fixture_or_setup": "Stop before another live run until the repo or fixture setup is repaired.",
        "connector_or_patch_generation": "Stop before another live run until the connector or patch contract is repaired.",
        "product_bug": "Stop and capture evidence before escalating the product bug.",
        "external_service_or_github": "Stop live mutation until the external dependency recovers or a retry is intentional.",
    }
    return mapping.get(diagnosis, "")


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
    if failure_class == "no_workspace_change" or any(
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
