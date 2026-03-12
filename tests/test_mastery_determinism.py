from __future__ import annotations

from flow_healer.mastery_determinism import (
    compare_issue_pack_snapshots,
    issue_body_fingerprint,
    render_issue_pack_comparison_markdown,
    snapshot_fixed_issue_pack,
)
from flow_healer.store import SQLiteStore


def test_snapshot_fixed_issue_pack_collects_latest_attempt_signals(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="927",
        repo="owner/repo",
        title="Issue 927",
        body="Validation:\n- cd e2e-apps/node-next && npm test -- --passWithNoTests",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.increment_healer_attempt("927")
    store.increment_healer_attempt("927")
    store.increment_healer_attempt("927")
    store.create_healer_attempt(
        attempt_id="hat_927",
        issue_id="927",
        attempt_no=3,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="hat_927",
        state="pr_open",
        actual_diff_set=["e2e-apps/node-next/app/api/auth/session/route.js"],
        test_summary={
            "execution_root": "e2e-apps/node-next",
            "validation_commands": ["npm test -- --passWithNoTests"],
            "failure_family": "none",
        },
        verifier_summary={},
    )
    store.set_healer_issue_state(issue_id="927", state="pr_open", pr_number=933, pr_state="open")

    snapshot = snapshot_fixed_issue_pack(
        store=store,
        issue_ids=("927",),
        captured_at="2026-03-12T10:00:00Z",
    )

    row = snapshot["issues"]["927"]
    assert snapshot["captured_at"] == "2026-03-12T10:00:00Z"
    assert snapshot["missing_issue_ids"] == []
    assert row["execution_root"] == "e2e-apps/node-next"
    assert row["validation_commands"] == ["npm test -- --passWithNoTests"]
    assert row["retry_count"] == 2
    assert row["failure_family"] == "none"
    assert row["body_fingerprint"] == issue_body_fingerprint(
        "Validation:\n- cd e2e-apps/node-next && npm test -- --passWithNoTests"
    )


def test_compare_issue_pack_snapshots_reports_drift_for_tracked_fields():
    previous = {
        "captured_at": "2026-03-12T10:00:00Z",
        "issues": {
            "927": {
                "body_fingerprint": "aaa",
                "execution_root": "e2e-apps/node-next",
                "validation_commands": ["npm test -- --passWithNoTests"],
                "failure_family": "none",
                "retry_count": 1,
            }
        },
    }
    current = {
        "captured_at": "2026-03-13T10:00:00Z",
        "issues": {
            "927": {
                "body_fingerprint": "bbb",
                "execution_root": "e2e-apps/node-next-alt",
                "validation_commands": ["npm run test"],
                "failure_family": "product",
                "retry_count": 3,
            }
        },
    }

    comparison = compare_issue_pack_snapshots(previous=previous, current=current)

    assert comparison["drift_count"] == 5
    assert comparison["unexpected_drift_count"] == 4
    assert comparison["has_unexpected_drift"] is True
    fields = {row["field"] for row in comparison["drift_rows"]}
    assert {
        "body_fingerprint",
        "execution_root",
        "validation_commands",
        "failure_family",
        "retry_count",
    } == fields


def test_compare_issue_pack_snapshots_is_clean_when_values_match():
    snapshot = {
        "captured_at": "2026-03-12T10:00:00Z",
        "issues": {
            "930": {
                "body_fingerprint": "stable",
                "execution_root": "e2e-smoke/python",
                "validation_commands": ["pytest -q"],
                "failure_family": "",
                "retry_count": 0,
            }
        },
    }

    comparison = compare_issue_pack_snapshots(previous=snapshot, current=snapshot)

    assert comparison["drift_rows"] == []
    assert comparison["unexpected_drift_rows"] == []
    assert comparison["has_unexpected_drift"] is False


def test_render_issue_pack_comparison_markdown_preserves_numeric_zero_values() -> None:
    comparison = {
        "previous_captured_at": "2026-03-12T08:31:15Z",
        "current_captured_at": "2026-03-12T10:56:47Z",
        "unexpected_drift_count": 1,
        "drift_rows": [
            {
                "issue_id": "928",
                "field": "retry_count",
                "previous": 1,
                "current": 0,
            }
        ],
    }

    markdown = render_issue_pack_comparison_markdown(comparison)

    assert "| `#928` | `retry_count` | `1` | `0` |" in markdown
