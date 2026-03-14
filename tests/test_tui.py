from __future__ import annotations

from flow_healer.tui import render_tui_text


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
