from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from typing import Any, Iterable

from .store import SQLiteStore

FIXED_MASTERY_ISSUE_PACK: tuple[str, ...] = (
    "926",
    "927",
    "928",
    "929",
    "930",
    "931",
)

_DRIFT_FIELDS: tuple[str, ...] = (
    "body_fingerprint",
    "execution_root",
    "validation_commands",
    "failure_family",
    "retry_count",
)


def snapshot_fixed_issue_pack(
    *,
    store: SQLiteStore,
    issue_ids: Iterable[str] | None = None,
    captured_at: str = "",
) -> dict[str, Any]:
    normalized_issue_ids = _normalize_issue_ids(issue_ids)
    issues: dict[str, dict[str, Any]] = {}
    missing_issue_ids: list[str] = []
    for issue_id in normalized_issue_ids:
        issue = store.get_healer_issue(issue_id)
        if not isinstance(issue, dict):
            missing_issue_ids.append(issue_id)
            continue
        latest_attempt = _latest_attempt(store=store, issue_id=issue_id)
        issues[issue_id] = {
            "issue_id": issue_id,
            "title": str(issue.get("title") or "").strip(),
            "state": str(issue.get("state") or "").strip(),
            "attempt_count": int(issue.get("attempt_count") or 0),
            "retry_count": max(0, int(issue.get("attempt_count") or 0) - 1),
            "pr_number": int(issue.get("pr_number") or 0),
            "body_fingerprint": issue_body_fingerprint(str(issue.get("body") or "")),
            "attempt_state": str(latest_attempt.get("state") or "").strip(),
            "execution_root": str(_test_summary_value(latest_attempt, "execution_root") or "").strip(),
            "validation_commands": _validation_commands(latest_attempt),
            "failure_family": _failure_family(issue=issue, latest_attempt=latest_attempt),
            "failure_class": str(latest_attempt.get("failure_class") or issue.get("last_failure_class") or "").strip(),
        }
    return {
        "captured_at": str(captured_at or _timestamp_now_utc()),
        "issue_ids": list(normalized_issue_ids),
        "missing_issue_ids": missing_issue_ids,
        "issues": issues,
    }


def compare_issue_pack_snapshots(
    *,
    previous: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    previous_issues = _snapshot_issues(previous)
    current_issues = _snapshot_issues(current)
    issue_ids = sorted(set(previous_issues.keys()) | set(current_issues.keys()), key=_issue_id_sort_key)
    drift_rows: list[dict[str, Any]] = []
    for issue_id in issue_ids:
        previous_row = previous_issues.get(issue_id)
        current_row = current_issues.get(issue_id)
        if previous_row is None:
            drift_rows.append(
                {
                    "issue_id": issue_id,
                    "field": "snapshot_presence",
                    "previous": "missing",
                    "current": "present",
                }
            )
            continue
        if current_row is None:
            drift_rows.append(
                {
                    "issue_id": issue_id,
                    "field": "snapshot_presence",
                    "previous": "present",
                    "current": "missing",
                }
            )
            continue
        for field in _DRIFT_FIELDS:
            previous_value = _normalized_field_value(previous_row.get(field), field=field)
            current_value = _normalized_field_value(current_row.get(field), field=field)
            if previous_value == current_value:
                continue
            drift_rows.append(
                {
                    "issue_id": issue_id,
                    "field": field,
                    "previous": previous_value,
                    "current": current_value,
                }
            )
    unexpected_drift_rows = [
        row
        for row in drift_rows
        if row["field"] not in {"body_fingerprint", "snapshot_presence"}
    ]
    return {
        "previous_captured_at": str(previous.get("captured_at") or ""),
        "current_captured_at": str(current.get("captured_at") or ""),
        "issue_ids": issue_ids,
        "drift_rows": drift_rows,
        "unexpected_drift_rows": unexpected_drift_rows,
        "drift_count": len(drift_rows),
        "unexpected_drift_count": len(unexpected_drift_rows),
        "has_unexpected_drift": bool(unexpected_drift_rows),
    }


def render_issue_pack_comparison_markdown(comparison: dict[str, Any]) -> str:
    previous_captured_at = str(comparison.get("previous_captured_at") or "")
    current_captured_at = str(comparison.get("current_captured_at") or "")
    drift_rows = comparison.get("drift_rows")
    if not isinstance(drift_rows, list):
        drift_rows = []
    lines = [
        "# Mastery Fixed-Issue-Pack Drift",
        "",
        f"- Previous snapshot: `{previous_captured_at or '-'}`",
        f"- Current snapshot: `{current_captured_at or '-'}`",
        f"- Drift rows: `{len(drift_rows)}`",
        f"- Unexpected drift rows: `{int(comparison.get('unexpected_drift_count') or 0)}`",
    ]
    if not drift_rows:
        lines.extend(
            [
                "",
                "No drift detected for tracked fields (`execution_root`, `validation_commands`, `failure_family`, `retry_count`).",
            ]
        )
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "",
            "| Issue | Field | Previous | Current |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in drift_rows:
        issue_id = str(row.get("issue_id") or "")
        field = str(row.get("field") or "")
        previous_value = _stringify_markdown_value(row.get("previous"))
        current_value = _stringify_markdown_value(row.get("current"))
        lines.append(f"| `#{issue_id}` | `{field}` | `{previous_value}` | `{current_value}` |")
    return "\n".join(lines) + "\n"


def issue_body_fingerprint(body: str) -> str:
    normalized_body = str(body or "").strip()
    if not normalized_body:
        return ""
    return hashlib.sha256(normalized_body.encode("utf-8")).hexdigest()


def _timestamp_now_utc() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_issue_ids(issue_ids: Iterable[str] | None) -> tuple[str, ...]:
    if issue_ids is None:
        return FIXED_MASTERY_ISSUE_PACK
    normalized = tuple(str(issue_id).strip() for issue_id in issue_ids if str(issue_id).strip())
    return normalized or FIXED_MASTERY_ISSUE_PACK


def _latest_attempt(*, store: SQLiteStore, issue_id: str) -> dict[str, Any]:
    attempts = store.list_healer_attempts(issue_id=issue_id, limit=1)
    if not attempts:
        return {}
    latest = attempts[0]
    return dict(latest) if isinstance(latest, dict) else {}


def _validation_commands(latest_attempt: dict[str, Any]) -> list[str]:
    value = _test_summary_value(latest_attempt, "validation_commands")
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _failure_family(*, issue: dict[str, Any], latest_attempt: dict[str, Any]) -> str:
    summary_family = str(_test_summary_value(latest_attempt, "failure_family") or "").strip()
    if summary_family:
        return summary_family
    return str(latest_attempt.get("failure_class") or issue.get("last_failure_class") or "").strip()


def _test_summary_value(latest_attempt: dict[str, Any], key: str) -> Any:
    summary = latest_attempt.get("test_summary")
    if not isinstance(summary, dict):
        return None
    return summary.get(key)


def _snapshot_issues(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    issues = snapshot.get("issues")
    if not isinstance(issues, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for issue_id, value in issues.items():
        if not isinstance(value, dict):
            continue
        normalized[str(issue_id)] = dict(value)
    return normalized


def _normalized_field_value(value: Any, *, field: str) -> Any:
    if field == "validation_commands":
        if isinstance(value, str):
            normalized = value.strip()
            return [normalized] if normalized else []
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []
    if field == "retry_count":
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
    return str(value or "").strip()


def _stringify_markdown_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        normalized = [str(item).strip() for item in value if str(item).strip()]
        return "; ".join(normalized)
    if value is None:
        return "-"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return str(value).replace("|", "\\|").strip() or "-"


def _issue_id_sort_key(raw_issue_id: str) -> tuple[int, str]:
    normalized = str(raw_issue_id or "").strip()
    try:
        return (0, f"{int(normalized):08d}")
    except ValueError:
        return (1, normalized)
