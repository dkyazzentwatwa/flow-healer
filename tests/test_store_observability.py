from __future__ import annotations

from flow_healer.store import SQLiteStore


def test_store_persists_runtime_events_and_scan_history(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()

    store.update_runtime_status(
        status="running",
        last_error="",
        touch_heartbeat=True,
        touch_tick_started=True,
        touch_tick_finished=True,
    )
    store.create_healer_event(
        event_type="attempt_started",
        message="Attempt started for issue #401.",
        issue_id="401",
        attempt_id="hat_401",
        payload={"prediction_source": "path_level"},
    )
    store.create_scan_run(run_id="scan_1", dry_run=True)
    store.finish_scan_run(
        run_id="scan_1",
        status="completed",
        summary={"findings_total": 2, "findings_over_threshold": 1},
    )
    store.upsert_scan_finding(
        fingerprint="fp_1",
        scan_type="pytest",
        severity="high",
        title="Pytest suite failed",
        status="detected",
        payload={"selector": "tests/test_a.py::test_alpha"},
        issue_number=88,
    )

    runtime = store.get_runtime_status()
    events = store.list_healer_events(limit=5)
    runs = store.list_scan_runs(limit=5)
    findings = store.list_scan_findings(limit=5)

    assert runtime is not None
    assert runtime["status"] == "running"
    assert runtime["heartbeat_at"]
    assert events[0]["event_type"] == "attempt_started"
    assert events[0]["payload"]["prediction_source"] == "path_level"
    assert runs[0]["summary"]["findings_over_threshold"] == 1
    assert findings[0]["issue_number"] == 88
