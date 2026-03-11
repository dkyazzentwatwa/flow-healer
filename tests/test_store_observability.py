from __future__ import annotations

import json
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


def test_store_migrates_legacy_attempt_rows_with_default_observability_fields(tmp_path):
    db_path = tmp_path / "state.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE healer_attempts (
                attempt_id TEXT PRIMARY KEY,
                issue_id TEXT NOT NULL,
                attempt_no INTEGER NOT NULL,
                state TEXT NOT NULL,
                prediction_source TEXT NOT NULL DEFAULT '',
                predicted_lock_set_json TEXT NOT NULL DEFAULT '[]',
                actual_diff_set_json TEXT NOT NULL DEFAULT '[]',
                test_summary_json TEXT NOT NULL DEFAULT '{}',
                verifier_summary_json TEXT NOT NULL DEFAULT '{}',
                failure_class TEXT NOT NULL DEFAULT '',
                failure_reason TEXT NOT NULL DEFAULT '',
                proposer_output_excerpt TEXT NOT NULL DEFAULT '',
                swarm_summary_json TEXT NOT NULL DEFAULT '{}',
                task_kind TEXT NOT NULL DEFAULT '',
                output_targets_json TEXT NOT NULL DEFAULT '[]',
                tool_policy TEXT NOT NULL DEFAULT '',
                validation_profile TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT DEFAULT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO healer_attempts(
                attempt_id, issue_id, attempt_no, state, prediction_source, predicted_lock_set_json
            )
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            ("legacy_attempt", "401", 1, "failed", "path_level", json.dumps(["repo:*"])),
        )
        conn.commit()
    finally:
        conn.close()

    store = SQLiteStore(db_path)
    store.bootstrap()

    attempt = store.list_recent_healer_attempts(limit=1)[0]

    assert attempt["attempt_id"] == "legacy_attempt"
    assert attempt["runtime_summary"] == {}
    assert attempt["artifact_bundle"] == {}
    assert attempt["artifact_links"] == []
    assert attempt["judgment_reason_code"] == ""


def test_store_persists_attempt_observability_fields(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()

    store.create_healer_attempt(
        attempt_id="attempt_obs_1",
        issue_id="501",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="attempt_obs_1",
        state="failed",
        actual_diff_set=["src/example.py"],
        test_summary={"failed_tests": 1},
        verifier_summary={"status": "needs_review"},
        runtime_summary={
            "service": {"status": "degraded", "last_error": "connector timeout"},
            "app_harness": {"artifacts_ready": True, "bundle_status": "captured"},
        },
        artifact_bundle={
            "bundle_id": "bundle-501",
            "artifacts": [{"kind": "patch", "path": "artifacts/501.patch"}],
        },
        artifact_links=[
            {"label": "patch", "href": "artifacts/501.patch"},
            {"label": "logs", "href": "artifacts/501.log"},
        ],
        ci_status_summary={
            "overall_state": "pending",
            "check_runs": {"total": 2, "success": 1, "pending": 1, "failure": 0, "neutral": 0},
        },
        judgment_reason_code="tests_failed",
        failure_class="tests_failed",
        failure_reason="Validation failed in targeted suite.",
    )

    attempt = store.list_recent_healer_attempts(limit=1)[0]

    assert attempt["runtime_summary"]["service"]["status"] == "degraded"
    assert attempt["runtime_summary"]["app_harness"]["artifacts_ready"] is True
    assert attempt["artifact_bundle"]["bundle_id"] == "bundle-501"
    assert attempt["artifact_bundle"]["artifacts"][0]["kind"] == "patch"
    assert attempt["artifact_links"][1]["label"] == "logs"
    assert attempt["ci_status_summary"]["overall_state"] == "pending"
    assert attempt["judgment_reason_code"] == "tests_failed"


def test_store_updates_issue_and_latest_attempt_ci_status_summary(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="502",
        repo="owner/repo",
        title="Issue 502",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.create_healer_attempt(
        attempt_id="attempt_obs_2",
        issue_id="502",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="attempt_obs_2",
        state="pr_open",
        actual_diff_set=[],
        test_summary={"promotion_state": "merge_blocked"},
        verifier_summary={},
    )

    store.update_issue_pr_ci_status(
        issue_id="502",
        ci_status_summary={
            "overall_state": "failure",
            "failing_contexts": ["CI"],
        },
    )

    issue = store.get_healer_issue("502")
    attempt = store.list_recent_healer_attempts(limit=1)[0]

    assert issue is not None
    assert issue["ci_status_summary"]["overall_state"] == "failure"
    assert attempt["ci_status_summary"]["failing_contexts"] == ["CI"]
