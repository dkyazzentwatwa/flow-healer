from __future__ import annotations

import sqlite3

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


def test_claim_next_healer_issue_skips_same_scope_when_active(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="9001",
        repo="owner/repo",
        title="Active issue",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=1,
        scope_key="path:e2e-smoke/node",
    )
    store.upsert_healer_issue(
        issue_id="9002",
        repo="owner/repo",
        title="Queued same scope",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=2,
        scope_key="path:e2e-smoke/node",
    )
    store.upsert_healer_issue(
        issue_id="9003",
        repo="owner/repo",
        title="Queued different scope",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=3,
        scope_key="path:e2e-smoke/swift",
    )
    store.set_healer_issue_state(issue_id="9001", state="pr_open", pr_number=101, pr_state="open")

    claimed = store.claim_next_healer_issue(
        worker_id="worker-a",
        lease_seconds=120,
        max_active_issues=1,
        enforce_scope_queue=True,
    )
    assert claimed is not None
    assert claimed["issue_id"] == "9003"


def test_claim_next_healer_issue_can_ignore_scope_queue(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="9011",
        repo="owner/repo",
        title="Active issue",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=1,
        scope_key="path:e2e-smoke/node",
    )
    store.upsert_healer_issue(
        issue_id="9012",
        repo="owner/repo",
        title="Queued same scope",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=2,
        scope_key="path:e2e-smoke/node",
    )
    store.set_healer_issue_state(issue_id="9011", state="pr_open", pr_number=111, pr_state="open")

    claimed = store.claim_next_healer_issue(
        worker_id="worker-a",
        lease_seconds=120,
        max_active_issues=1,
        enforce_scope_queue=False,
    )
    assert claimed is not None
    assert claimed["issue_id"] == "9012"


def test_claim_next_healer_issue_ignores_expired_leases_for_active_budget(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="9101",
        repo="owner/repo",
        title="Expired claim",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=1,
    )
    store.upsert_healer_issue(
        issue_id="9102",
        repo="owner/repo",
        title="Queued issue",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=2,
    )
    store.set_healer_issue_state(
        issue_id="9101",
        state="claimed",
        expected_state="queued",
    )

    conn = store._connect()
    conn.execute(
        "UPDATE healer_issues SET lease_owner = ?, lease_expires_at = datetime('now', '-10 minutes') WHERE issue_id = ?",
        ("worker-stale", "9101"),
    )
    conn.commit()

    claimed = store.claim_next_healer_issue(
        worker_id="worker-a",
        lease_seconds=120,
        max_active_issues=1,
        enforce_scope_queue=True,
    )

    assert claimed is not None
    assert claimed["issue_id"] == "9102"


def test_claim_next_healer_issue_ignores_expired_scope_conflicts(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="9111",
        repo="owner/repo",
        title="Expired running issue",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=1,
        scope_key="path:e2e-smoke/node",
    )
    store.upsert_healer_issue(
        issue_id="9112",
        repo="owner/repo",
        title="Queued same scope",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=2,
        scope_key="path:e2e-smoke/node",
    )
    store.set_healer_issue_state(
        issue_id="9111",
        state="running",
        expected_state="queued",
    )

    conn = store._connect()
    conn.execute(
        "UPDATE healer_issues SET lease_owner = ?, lease_expires_at = datetime('now', '-10 minutes') WHERE issue_id = ?",
        ("worker-stale", "9111"),
    )
    conn.commit()

    claimed = store.claim_next_healer_issue(
        worker_id="worker-a",
        lease_seconds=120,
        max_active_issues=2,
        enforce_scope_queue=True,
    )

    assert claimed is not None
    assert claimed["issue_id"] == "9112"


def test_set_states_batches_multiple_kv_updates(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()

    store.set_states(
        {
            "healer_paused": "true",
            "healer_helper_recycle_status": "requested",
            "healer_active_worker_id": "worker-1",
        }
    )

    assert store.get_state("healer_paused") == "true"
    assert store.get_state("healer_helper_recycle_status") == "requested"
    assert store.get_state("healer_active_worker_id") == "worker-1"


def test_store_bootstrap_adds_hot_path_indexes(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()

    conn = sqlite3.connect(store.db_path)
    try:
        index_names = {
            row[1]
            for row in conn.execute("PRAGMA index_list('healer_issues')").fetchall()
        }
        attempt_index_names = {
            row[1]
            for row in conn.execute("PRAGMA index_list('healer_attempts')").fetchall()
        }
    finally:
        conn.close()

    assert "idx_healer_issues_state_priority_updated" in index_names
    assert "idx_healer_issues_state_scope_priority_updated" in index_names
    assert "idx_healer_issues_state_lease" in index_names
    assert "idx_healer_attempts_issue_started" in attempt_index_names
    assert "idx_healer_attempts_state_finished_issue" in attempt_index_names
    assert "idx_healer_attempts_issue_attempt_no" in attempt_index_names
