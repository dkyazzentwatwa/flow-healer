from __future__ import annotations

import json
import subprocess
from pathlib import Path

from flow_healer.config import AppConfig, RelaySettings, ServiceSettings
from flow_healer.service import FlowHealerService
from flow_healer.store import SQLiteStore


def _make_demo_service(tmp_path: Path) -> FlowHealerService:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "-B", "main"], cwd=repo_path, check=True, capture_output=True, text=True)
    state_root = tmp_path / "state"
    return FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(state_root)),
            repos=[
                RelaySettings(
                    repo_name="demo",
                    healer_repo_path=str(repo_path),
                    healer_repo_slug="owner/repo",
                )
            ],
        )
    )


def test_write_telemetry_exports_writes_csv_and_jsonl(tmp_path: Path) -> None:
    from flow_healer.telemetry_exports import write_telemetry_exports

    service = _make_demo_service(tmp_path)
    store = SQLiteStore(service.config.repo_db_path("demo"))
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="101",
        repo="owner/repo",
        title="Export me",
        body="body",
        author="alice",
        labels=["healer:ready"],
        priority=1,
    )
    store.create_healer_attempt(
        attempt_id="ha_101_1",
        issue_id="101",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="ha_101_1",
        state="failed",
        actual_diff_set=[],
        test_summary={"promotion_state": "failed"},
        verifier_summary={},
        failure_class="tests_failed",
        failure_reason="nope",
    )
    store.create_healer_event(
        event_type="swarm_started",
        message="Swarm started",
        issue_id="101",
        attempt_id="ha_101_1",
        payload={"strategy": "repair"},
    )
    store.create_control_command(
        source="web",
        external_id="cmd-1",
        sender="alice",
        repo_name="demo",
        raw_command="FH: status repo=demo",
        parsed_command="status",
    )
    store.update_runtime_status(status="idle", last_error="", touch_heartbeat=True)
    store.close()

    output_dir = tmp_path / "exports"
    written = write_telemetry_exports(service=service, repo_name="demo", output_dir=output_dir, formats=("csv", "jsonl"))

    assert any(path.name == "issues.csv" for path in written)
    assert any(path.name == "attempts.jsonl" for path in written)

    issues_csv = (output_dir / "csv" / "issues.csv").read_text(encoding="utf-8")
    assert "issue_id" in issues_csv
    assert "101" in issues_csv

    attempts_jsonl = (output_dir / "jsonl" / "attempts.jsonl").read_text(encoding="utf-8").strip().splitlines()
    attempt_payload = json.loads(attempts_jsonl[0])
    assert attempt_payload["issue_id"] == "101"
    assert attempt_payload["failure_class"] == "tests_failed"

    metrics_csv = (output_dir / "csv" / "summary_metrics.csv").read_text(encoding="utf-8")
    assert "repo_name" in metrics_csv
    assert "demo" in metrics_csv
