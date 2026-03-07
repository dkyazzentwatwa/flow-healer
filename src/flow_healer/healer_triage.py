from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .skill_contracts import default_action_for_diagnosis, recommended_skill_for_diagnosis


@dataclass(slots=True, frozen=True)
class DiagnosisRoute:
    diagnosis: str
    recommended_skill: str
    default_action: str


_CONNECTOR_FAILURE_CLASSES = {
    "connector_unavailable",
    "diff_limit_exceeded",
    "no_patch",
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
    )


def classify_issue_route(issue: dict[str, Any] | None, attempt: dict[str, Any] | None) -> DiagnosisRoute:
    return diagnosis_route(classify_failure(issue, attempt))
