from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from flow_healer.tui import (
    ActionBar,
    AnalyticsWidget,
    FlowHealerApp,
    StatsBar,
    TuiPrefs,
    _hbar,
    _render_attempt_evidence,
    build_tui_snapshot,
    load_tui_prefs,
    render_tui_text,
    save_tui_prefs,
    tui_detail_lines,
    tui_queue_summary,
)


def test_render_tui_text_includes_core_sections() -> None:
    text = render_tui_text(
        {
            "generated_at": "2026-03-14 12:00:00",
            "status_rows": [
                {
                    "repo_name": "demo",
                    "trust": {"state": "ready", "summary": "Repo is healthy."},
                    "state_counts": {"queued": 2, "running": 1},
                }
            ],
            "queue_rows": [
                {
                    "repo": "demo",
                    "issue_id": "101",
                    "title": "Repair export pipeline",
                    "state": "queued",
                }
            ],
            "attempt_rows": [
                {
                    "issue_id": "101",
                    "attempt_id": "ha_101_1",
                    "state": "failed",
                    "failure_class": "tests_failed",
                }
            ],
            "event_rows": [
                {
                    "created_at": "2026-03-14 11:59:00",
                    "event_type": "swarm_started",
                    "message": "Swarm started",
                }
            ],
            "log_lines": ["[flow-healer.log] info ready"],
        }
    )

    assert "Flow Healer TUI" in text
    assert "Status" in text
    assert "Queue" in text
    assert "Recent Attempts" in text
    assert "Recent Events" in text
    assert "Recent Logs" in text
    assert "Repair export pipeline" in text
    assert "chart=" in text


def test_tui_queue_summary_truncates_long_rows() -> None:
    summary = tui_queue_summary(
        {
            "issue_id": "101",
            "state": "needs_review",
            "title": "Repair export pipeline after a very long regression title that should not fill the entire pane",
        },
        width=48,
    )

    assert summary.startswith("#101")
    assert "needs_review" in summary
    assert len(summary) <= 48
    assert summary.endswith("...")


def test_tui_detail_lines_wrap_long_text() -> None:
    lines = tui_detail_lines(
        {
            "message": "This is a deliberately long event message that should wrap into multiple detail rows instead of blasting across the full terminal width.",
            "event_type": "swarm_started",
            "created_at": "2026-03-14 11:59:00",
        },
        width=32,
    )

    assert len(lines) > 3
    assert all(len(line) <= 32 for line in lines)
    assert any("swarm_started" in line for line in lines)


def test_build_tui_snapshot_returns_expected_keys() -> None:
    fake_config = MagicMock()
    fake_config.state_root_path.return_value = MagicMock(
        __truediv__=lambda self, name: MagicMock(exists=lambda: False)
    )

    fake_service = MagicMock()
    fake_service.config = fake_config

    from flow_healer import telemetry_exports as te

    original = te.collect_telemetry_datasets

    def fake_collect(**kwargs: object) -> dict:
        return {
            "summary_metrics": [],
            "issues": [],
            "attempts": [],
            "events": [],
        }

    te.collect_telemetry_datasets = fake_collect
    try:
        snapshot = build_tui_snapshot(service=fake_service, repo_name=None)
    finally:
        te.collect_telemetry_datasets = original

    assert "generated_at" in snapshot
    assert "queue_rows" in snapshot
    assert "attempt_rows" in snapshot
    assert "event_rows" in snapshot
    assert "status_rows" in snapshot
    assert "log_lines" in snapshot


def test_tui_prefs_load_save_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_config = MagicMock()
        fake_config.state_root_path.return_value = Path(tmpdir)

        prefs = TuiPrefs(theme="nord", refresh_seconds=10, show_sparkline=False)
        save_tui_prefs(fake_config, prefs)

        loaded = load_tui_prefs(fake_config)
        assert loaded.theme == "nord"
        assert loaded.refresh_seconds == 10
        assert loaded.show_sparkline is False

        # Verify the JSON file is valid and atomic (no .tmp leftover)
        json_path = Path(tmpdir) / "tui_prefs.json"
        assert json_path.exists()
        raw = json.loads(json_path.read_text())
        assert raw["theme"] == "nord"
        assert not (Path(tmpdir) / "tui_prefs.tmp").exists()


def test_hbar_helper() -> None:
    assert _hbar(10, 10, width=10) == "██████████"
    assert _hbar(0, 10, width=10) == "░░░░░░░░░░"
    assert _hbar(5, 10, width=10) == "█████░░░░░"
    assert _hbar(0, 0, width=8) == "░░░░░░░░"


def test_analytics_widget_renders_key_metrics() -> None:
    snapshot = {
        "generated_at": "2026-03-14 12:00:00",
        "status_rows": [
            {
                "repo_name": "demo",
                "reliability_canary": {
                    "first_pass_success_rate": 0.87,
                    "mean_time_to_valid_pr_minutes": 4.2,
                    "sample_size": 50,
                    "no_op_rate": 0.05,
                    "retries_per_success": 1.2,
                    "wrong_root_execution_rate": 0.02,
                    "issue_count": 40,
                },
                "reliability_daily_rollups": [
                    {
                        "day": "2026-03-14",
                        "issue_count": 12,
                        "sample_size": 15,
                        "first_pass_success_rate": 0.83,
                        "no_op_rate": 0.0,
                        "retries_per_success": 1.0,
                        "wrong_root_execution_rate": 0.0,
                        "mean_time_to_valid_pr_minutes": 3.5,
                    }
                ],
                "reliability_trends": {
                    "7d": {
                        "current": {"first_pass_success_rate": 0.87},
                        "previous": {"first_pass_success_rate": 0.82},
                    },
                    "30d": {
                        "current": {"first_pass_success_rate": 0.85},
                        "previous": {"first_pass_success_rate": 0.80},
                    },
                },
                "failure_domain_metrics": {
                    "total": 30,
                    "infra": 12,
                    "contract": 5,
                    "code": 8,
                    "unknown": 5,
                },
                "issue_outcomes": {"pr_open": 3, "resolved": 7, "failed": 2, "recent_successes": 4},
                "state_counts": {"queued": 5, "running": 2, "failed": 1},
                "circuit_breaker": {
                    "open": False,
                    "failure_rate": 0.13,
                    "threshold": 0.5,
                    "cooldown_remaining_seconds": 0,
                },
                "worker": {"active": True, "uptime_seconds": 8040, "last_error_message": None},
                "resource_audit": {
                    "worktrees": {"total": 3, "orphaned": 0},
                    "locks": {"total": 2, "expired": 0},
                },
            }
        ],
        "queue_rows": [],
        "attempt_rows": [],
        "event_rows": [],
        "log_lines": [],
    }

    widget = AnalyticsWidget()
    widget.update_from_snapshot(snapshot)
    assert "87" in widget.last_text
    assert "infra" in widget.last_text
    assert "CLOSED" in widget.last_text
    assert "2026-03-14" in widget.last_text


def test_stats_bar_content_reflects_snapshot() -> None:
    snapshot = {
        "generated_at": "2026-03-14 12:00:05",
        "status_rows": [
            {
                "repo_name": "demo",
                "trust": {"state": "ready", "summary": "ok"},
                "state_counts": {"queued": 5, "running": 2, "failed": 1, "merged": 8},
            }
        ],
        "queue_rows": [],
        "attempt_rows": [],
        "event_rows": [],
        "log_lines": [],
    }

    bar = StatsBar()
    bar.update_from_snapshot(snapshot, show_sparkline=True)
    markup = bar.last_markup
    assert "5" in markup    # queued count
    assert "2" in markup    # running count
    assert "1" in markup    # failed count
    assert "8" in markup    # merged count
    assert "12:00:05" in markup


# ---------------------------------------------------------------------------
# Phase 1 interactive TUI tests
# ---------------------------------------------------------------------------


def test_render_attempt_evidence_surfaces_test_summary() -> None:
    attempt = {
        "attempt_id": "ha_42_3",
        "state": "failed",
        "issue_id": "42",
        "failure_class": "tests_failed",
        "failure_reason": "pytest exited 1",
        "test_summary": {"passed": 10, "failed": 2, "errors": 0, "duration_seconds": 8.5},
        "verifier_summary": {"outcome": "rejected", "reason": "test gate failed"},
        "actual_diff_set": ["src/foo/bar.py"],
        "pr_number": 0,
    }
    text = _render_attempt_evidence(attempt)

    assert "ha_42_3" in text
    assert "10" in text       # passed
    assert "2" in text        # failed
    assert "8.5" in text      # duration
    assert "rejected" in text
    assert "src/foo/bar.py" in text
    assert "no PR opened" in text


def test_action_bar_shows_correct_actions() -> None:
    bar = ActionBar()

    # Row with a lock owner — "Clear lock" should be active (no dim tag)
    bar.update_for_row({"issue_id": "1", "lease_owner": "worker-1", "pr_number": 0})
    assert bar.display
    markup = bar.last_markup
    assert "Clear lock" in markup
    # Should NOT be wrapped in [dim]...[/] when lock exists
    assert "[dim][ctrl+x] Clear lock[/]" not in markup

    # Row without a lock owner — "Clear lock" should be dimmed
    bar.update_for_row({"issue_id": "2", "lease_owner": None, "pr_number": 0})
    markup = bar.last_markup
    assert "[dim][ctrl+x] Clear lock[/]" in markup

    # None row → bar hidden
    bar.update_for_row(None)
    assert not bar.display


def test_live_events_poll_only_updates_events() -> None:
    """_poll_events does not modify _snapshot — it only touches the events DataTable."""
    fake_service = MagicMock()
    fake_service.config.select_repos.return_value = []  # causes _get_active_store to return None
    app = FlowHealerApp(service=fake_service, repo_name=None, prefs=TuiPrefs())

    sentinel_queue = [{"issue_id": "99"}]
    sentinel_attempts = [{"attempt_id": "ha_99_1"}]
    app._snapshot = {
        "queue_rows": sentinel_queue,
        "attempt_rows": sentinel_attempts,
        "event_rows": [],
    }

    # Mock query_one to track which selectors are accessed
    queried: list[str] = []
    fake_table = MagicMock()

    def mock_query_one(selector: str, *args: object) -> object:
        queried.append(selector)
        return fake_table

    app.query_one = mock_query_one  # type: ignore[method-assign]

    # With no active store, _poll_events returns early — snapshot untouched
    app._poll_events()

    assert app._snapshot["queue_rows"] is sentinel_queue
    assert app._snapshot["attempt_rows"] is sentinel_attempts
    # Should not have queried queue or attempts tables
    assert not any("queue" in q for q in queried)
    assert not any("attempts" in q for q in queried)


def test_format_attempt_row_for_display_maps_failure_class():
    """_format_attempt_row_for_display must map internal failure_class to operator label."""
    from flow_healer.tui import _format_attempt_row_for_display
    row = {
        "attempt_id": "abc123",
        "issue_id": "42",
        "state": "failed",
        "failure_class": "tests_failed",
        "failure_reason": "3 tests failed in test_cache.py",
    }
    display = _format_attempt_row_for_display(row)
    assert display["operator_failure"] == "validation_failed"
    assert "tests_failed" not in display["operator_failure"]


def test_format_attempt_row_for_display_empty_failure():
    """_format_attempt_row_for_display with no failure_class returns empty string."""
    from flow_healer.tui import _format_attempt_row_for_display
    row = {"attempt_id": "abc", "issue_id": "1", "state": "running", "failure_class": ""}
    display = _format_attempt_row_for_display(row)
    assert display["operator_failure"] == ""


def test_format_attempt_row_for_display_preserves_original_fields():
    """_format_attempt_row_for_display must preserve all original row fields."""
    from flow_healer.tui import _format_attempt_row_for_display
    row = {"attempt_id": "x", "issue_id": "7", "state": "failed", "failure_class": "scope_violation"}
    display = _format_attempt_row_for_display(row)
    assert display["attempt_id"] == "x"
    assert display["issue_id"] == "7"
    assert display["operator_failure"] == "scope_violation"
