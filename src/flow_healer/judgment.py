from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .healer_task_spec import HealerTaskSpec

_VALID_REASON_CODES = {
    "product_ambiguity",
    "unsafe_data_migration",
    "non_deterministic_visual_result",
    "conflicting_feedback",
    "security_or_privacy_risk",
    "repro_not_stable",
}


@dataclass(slots=True, frozen=True)
class JudgmentAssessment:
    requires_human: bool
    reason_code: str = ""
    summary: str = ""
    packet: dict[str, Any] = field(default_factory=dict)


def build_judgment_assessment(
    *,
    task_spec: HealerTaskSpec,
    feedback_context: str,
    test_summary: dict[str, Any] | None,
    verifier_summary: dict[str, Any] | None,
    workspace_status: dict[str, Any] | None,
    pr_number: int,
    failure_reason: str = "",
) -> JudgmentAssessment:
    summary_map = dict(test_summary or {})
    workspace_map = dict(workspace_status or {})
    verifier_map = dict(verifier_summary or {})

    explicit_reason = _normalize_reason_code(
        summary_map.get("judgment_reason_code") or workspace_map.get("judgment_reason_code") or ""
    )
    explicit_packet = _normalize_packet(
        summary_map.get("escalation_packet") or workspace_map.get("escalation_packet"),
        reason_code=explicit_reason,
        summary_value=summary_map.get("judgment_summary") or workspace_map.get("judgment_summary"),
        pr_number=pr_number,
        feedback_context=feedback_context,
        failure_reason=failure_reason,
    )
    if explicit_reason and explicit_packet:
        return JudgmentAssessment(
            requires_human=True,
            reason_code=explicit_reason,
            summary=str(explicit_packet.get("summary") or "").strip(),
            packet=explicit_packet,
        )

    if _has_conflicting_review_states(feedback_context):
        packet = _build_default_packet(
            reason_code="conflicting_feedback",
            summary="Conflicting human review states require a single decision before automation proceeds.",
            decision_needed="Confirm which review direction should win before the next automated pass.",
            pr_number=pr_number,
            feedback_context=feedback_context,
            failure_reason=failure_reason,
        )
        return JudgmentAssessment(
            requires_human=True,
            reason_code="conflicting_feedback",
            summary=str(packet["summary"]),
            packet=packet,
        )

    matched_condition = _match_condition(
        task_spec=task_spec,
        feedback_context=feedback_context,
        verifier_summary=verifier_map,
        failure_reason=failure_reason,
    )
    if matched_condition:
        reason_code = _map_condition_to_reason_code(matched_condition)
        packet = _build_default_packet(
            reason_code=reason_code,
            summary=matched_condition,
            decision_needed=_default_decision_needed(reason_code),
            pr_number=pr_number,
            feedback_context=feedback_context,
            failure_reason=failure_reason,
        )
        return JudgmentAssessment(
            requires_human=True,
            reason_code=reason_code,
            summary=matched_condition,
            packet=packet,
        )

    return JudgmentAssessment(requires_human=False)


def normalize_reason_code(value: object) -> str:
    return _normalize_reason_code(value)


def _normalize_reason_code(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _VALID_REASON_CODES:
        return normalized
    return ""


def _normalize_packet(
    packet_value: object,
    *,
    reason_code: str,
    summary_value: object,
    pr_number: int,
    feedback_context: str,
    failure_reason: str,
) -> dict[str, Any]:
    packet = dict(packet_value) if isinstance(packet_value, dict) else {}
    if not packet and not reason_code:
        return {}
    normalized_reason = _normalize_reason_code(packet.get("reason_code") or reason_code)
    if not normalized_reason:
        return {}
    summary_text = _clean_text(
        packet.get("summary")
        or _summary_value_text(summary_value)
        or failure_reason
        or _default_summary(normalized_reason)
    )
    decision_needed = _clean_text(packet.get("decision_needed") or _default_decision_needed(normalized_reason))
    attempted_actions = _normalized_string_list(packet.get("attempted_actions"))
    evidence_links = _normalized_evidence_links(packet.get("evidence_links") or packet.get("artifact_links"))
    feedback_excerpt = _clean_text(packet.get("feedback_excerpt") or feedback_context, max_chars=500)
    normalized = {
        "reason_code": normalized_reason,
        "summary": summary_text,
        "decision_needed": decision_needed,
        "attempted_actions": attempted_actions,
        "evidence_links": evidence_links,
        "feedback_excerpt": feedback_excerpt,
        "resume_hint": _clean_text(packet.get("resume_hint") or _default_resume_hint(pr_number), max_chars=240),
        "pr_number": int(packet.get("pr_number") or pr_number or 0),
    }
    artifact_labels = _normalized_string_list(packet.get("artifact_labels"))
    if artifact_labels:
        normalized["artifact_labels"] = artifact_labels
    verifier_summary = packet.get("verifier_summary")
    if isinstance(verifier_summary, dict):
        normalized["verifier_summary"] = dict(verifier_summary)
    return normalized


def _build_default_packet(
    *,
    reason_code: str,
    summary: str,
    decision_needed: str,
    pr_number: int,
    feedback_context: str,
    failure_reason: str,
) -> dict[str, Any]:
    return {
        "reason_code": reason_code,
        "summary": _clean_text(summary or _default_summary(reason_code)),
        "decision_needed": _clean_text(decision_needed or _default_decision_needed(reason_code)),
        "attempted_actions": [],
        "evidence_links": [],
        "feedback_excerpt": _clean_text(feedback_context or failure_reason, max_chars=500),
        "resume_hint": _default_resume_hint(pr_number),
        "pr_number": int(pr_number or 0),
    }


def _match_condition(
    *,
    task_spec: HealerTaskSpec,
    feedback_context: str,
    verifier_summary: dict[str, Any],
    failure_reason: str,
) -> str:
    evidence = " ".join(
        part
        for part in [
            feedback_context.strip().lower(),
            str(verifier_summary.get("summary") or "").strip().lower(),
            str(failure_reason or "").strip().lower(),
        ]
        if part
    )
    if not evidence:
        return ""
    for condition in task_spec.judgment_required_conditions:
        normalized = str(condition or "").strip().lower()
        if normalized and normalized in evidence:
            return str(condition or "").strip()
    return ""


def _map_condition_to_reason_code(condition: str) -> str:
    normalized = str(condition or "").strip().lower()
    if any(token in normalized for token in ("privacy", "security", "secret", "auth")):
        return "security_or_privacy_risk"
    if any(token in normalized for token in ("migration", "schema", "backfill", "drop column", "data loss")):
        return "unsafe_data_migration"
    if any(token in normalized for token in ("visual", "layout", "baseline", "screenshot")):
        return "non_deterministic_visual_result"
    if any(token in normalized for token in ("repro", "stable", "flaky")):
        return "repro_not_stable"
    if any(token in normalized for token in ("feedback", "review conflict", "conflict")):
        return "conflicting_feedback"
    return "product_ambiguity"


def _has_conflicting_review_states(feedback_context: str) -> bool:
    latest_state_by_author: dict[str, str] = {}
    for line in str(feedback_context or "").strip().splitlines():
        lowered = line.strip().lower()
        if "pr review (approved)" in lowered and "from @" in lowered:
            author = lowered.rsplit("from @", 1)[-1].split(":", 1)[0].strip()
            if author:
                latest_state_by_author[author] = "approved"
        if "pr review (changes_requested)" in lowered and "from @" in lowered:
            author = lowered.rsplit("from @", 1)[-1].split(":", 1)[0].strip()
            if author:
                latest_state_by_author[author] = "changes_requested"
    states = set(latest_state_by_author.values())
    return "approved" in states and "changes_requested" in states


def _default_summary(reason_code: str) -> str:
    if reason_code == "conflicting_feedback":
        return "Conflicting human review states require a single decision before automation proceeds."
    if reason_code == "unsafe_data_migration":
        return "The requested change may alter persisted data in a way that needs human approval."
    if reason_code == "non_deterministic_visual_result":
        return "Visual validation is not deterministic enough to choose a safe automated fix."
    if reason_code == "security_or_privacy_risk":
        return "The requested change touches a security or privacy boundary that needs human approval."
    if reason_code == "repro_not_stable":
        return "The reported reproduction path is not stable enough for a safe automated change."
    return "The issue still needs a human product decision before automation can proceed safely."


def _default_decision_needed(reason_code: str) -> str:
    if reason_code == "conflicting_feedback":
        return "Confirm which human review direction should control the next attempt."
    if reason_code == "unsafe_data_migration":
        return "Confirm the approved migration strategy and any acceptable data-loss tradeoffs."
    if reason_code == "non_deterministic_visual_result":
        return "Confirm the expected visual outcome or baseline before retrying."
    if reason_code == "security_or_privacy_risk":
        return "Confirm the approved security or privacy behavior before retrying."
    if reason_code == "repro_not_stable":
        return "Confirm the stable reproduction steps or expected failure signal before retrying."
    return "Confirm the intended product behavior before automation retries this issue."


def _default_resume_hint(pr_number: int) -> str:
    if int(pr_number or 0) > 0:
        return "Reply on the issue with the chosen direction, then rerun the issue so the existing PR can continue."
    return "Update the issue with the missing decision, then rerun it for another pass."


def _clean_text(value: object, *, max_chars: int = 320) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3].rstrip()}..."


def _summary_value_text(value: object) -> str:
    if isinstance(value, dict):
        return _clean_text(value.get("summary") or "", max_chars=320)
    return _clean_text(value, max_chars=320)


def _normalized_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean_text(item, max_chars=180) for item in value if _clean_text(item, max_chars=180)]


def _normalized_evidence_links(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        label = _clean_text(item.get("label") or "", max_chars=80)
        href = _clean_text(item.get("href") or item.get("url") or item.get("path") or "", max_chars=240)
        if not label and not href:
            continue
        normalized.append({"label": label, "href": href})
    return normalized
