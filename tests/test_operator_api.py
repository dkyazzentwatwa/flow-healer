from __future__ import annotations

from flow_healer.config import AppConfig, RelaySettings, ServiceSettings
from flow_healer.operator_api import FlowHealerOperatorAPI
from flow_healer.store import SQLiteStore


def _make_config(tmp_path):
    return AppConfig(
        service=ServiceSettings(state_root=str(tmp_path)),
        repos=[
            RelaySettings(
                repo_name="demo",
                healer_repo_path=str(tmp_path / "repo"),
                healer_repo_slug="owner/demo",
                healer_poll_interval_seconds=60,
            )
        ],
    )


def test_operator_api_builds_fleet_and_issue_detail(tmp_path):
    config = _make_config(tmp_path)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    store = SQLiteStore(config.repo_db_path("demo"))
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="401",
        repo="owner/demo",
        title="Fix flaky test",
        body="Body text",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="401",
        state="running",
        workspace_path=str(repo_dir / ".worktrees" / "401"),
        branch_name="healer/401-fix",
        last_failure_class="",
        feedback_context="Please keep the patch small.",
    )
    store.create_healer_attempt(
        attempt_id="hat_401",
        issue_id="401",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["tests/test_a.py"],
    )
    store.finish_healer_attempt(
        attempt_id="hat_401",
        state="failed",
        actual_diff_set=["tests/test_a.py"],
        test_summary={"failed": 1},
        verifier_summary={"passed": False},
        failure_class="tests_failed",
        failure_reason="pytest failed",
    )
    store.create_healer_lesson(
        lesson_id="lesson_1",
        issue_id="401",
        attempt_id="hat_401",
        lesson_kind="test_hint",
        scope_key="tests:*",
        fingerprint="fp_1",
        problem_summary="Flaky assertion",
        lesson_text="Run the targeted selector first.",
        test_hint="pytest tests/test_a.py::test_alpha",
        guardrail={},
        confidence=80,
        outcome="failed",
    )
    store.acquire_healer_lock(
        lock_key="tests/test_a.py",
        granularity="file",
        issue_id="401",
        lease_owner="worker_1",
        lease_seconds=120,
    )
    store.create_healer_event(
        event_type="attempt_finished",
        message="Attempt finished.",
        issue_id="401",
        attempt_id="hat_401",
        payload={"state": "failed"},
    )
    store.create_scan_run(run_id="scan_1", dry_run=False)
    store.finish_scan_run(run_id="scan_1", status="completed", summary={"findings_over_threshold": 1})
    store.upsert_scan_finding(
        fingerprint="scan_fp",
        scan_type="pytest",
        severity="high",
        title="Pytest suite failed",
        status="detected",
        payload={"selector": "tests/test_a.py::test_alpha"},
    )
    store.update_runtime_status(status="running", touch_heartbeat=True)
    store.close()

    api = FlowHealerOperatorAPI(config)
    fleet = api.fleet_rows()
    detail = api.issue_detail("demo", "401")
    snapshot = api.repo_snapshot("demo")

    assert fleet[0].repo == "demo"
    assert fleet[0].issues_total == 1
    assert fleet[0].runtime.status == "running"
    assert detail is not None
    assert detail.issue.branch_name == "healer/401-fix"
    assert detail.attempts[0].failure_class == "tests_failed"
    assert detail.lessons[0]["lesson_kind"] == "test_hint"
    assert detail.locks[0]["lock_key"] == "tests/test_a.py"
    assert snapshot.recent_findings[0].title == "Pytest suite failed"
