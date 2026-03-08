from pathlib import Path

from flow_healer.codex_app_server_connector import CodexAppServerConnector
from flow_healer.codex_cli_connector import CodexCliConnector
from flow_healer.config import AppConfig, RelaySettings, ServiceSettings
from flow_healer.healer_preflight import preflight_cache_key
from flow_healer.service import FlowHealerService


def test_status_rows_report_circuit_breaker_state(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    state_root = tmp_path / "state"
    service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(state_root)),
            repos=[
                RelaySettings(
                    repo_name="demo",
                    healer_repo_path=str(repo_path),
                    healer_repo_slug="owner/repo",
                    healer_circuit_breaker_window=5,
                    healer_circuit_breaker_failure_rate=0.5,
                    healer_circuit_breaker_cooldown_seconds=300,
                )
            ],
        )
    )
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.upsert_healer_issue(
        issue_id="1",
        repo="owner/repo",
        title="Issue 1",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    for idx, state in enumerate(["failed", "failed", "pr_open", "failed", "failed"]):
        runtime.store.create_healer_attempt(
            attempt_id=f"ha_{idx}",
            issue_id="1",
            attempt_no=idx + 1,
            state="running",
            prediction_source="path_level",
            predicted_lock_set=["repo:*"],
        )
        runtime.store.finish_healer_attempt(
            attempt_id=f"ha_{idx}",
            state=state,
            actual_diff_set=[],
            test_summary={},
            verifier_summary={},
            failure_class="tests_failed" if state == "failed" else "",
            failure_reason="Targeted sandbox validation failed." if state == "failed" else "",
        )
    runtime.store.close()

    rows = service.status_rows("demo")

    breaker = rows[0]["circuit_breaker"]
    assert breaker["open"] is True
    assert breaker["attempts_considered"] == 5
    assert breaker["failures"] == 4
    assert breaker["failure_rate"] == 0.8
    assert breaker["threshold"] == 0.5
    assert 0 < breaker["cooldown_remaining_seconds"] <= 300
    assert breaker["last_failure_at"]
    connector = rows[0]["connector"]
    assert "available" in connector
    assert "configured_command" in connector
    assert "resolved_command" in connector
    assert "last_error_class" in connector
    assert "last_runtime_error_kind" in connector
    assert "last_runtime_stdout_tail" in connector
    assert "last_runtime_stderr_tail" in connector
    recent_attempt = rows[0]["recent_attempts"][0]
    assert recent_attempt["diagnosis"] == "product_bug"
    assert recent_attempt["failure_family"] == "product"
    assert recent_attempt["recommended_skill"] == "flow-healer-live-smoke"
    assert recent_attempt["default_action"]
    assert recent_attempt["graph_position"] == 3
    assert recent_attempt["previous_skill"] == "flow-healer-preflight"
    assert recent_attempt["next_skill"] == "flow-healer-triage"
    assert recent_attempt["skill_relative_path"].endswith("skills/flow-healer-live-smoke/SKILL.md")
    assert recent_attempt["default_command_preview"]
    assert "issue_id" in recent_attempt["key_output_fields"]
    assert "attempt_state" in recent_attempt["key_output_fields"]
    assert recent_attempt["stop_conditions"] == []
    assert recent_attempt["stop_recommended"] is True
    assert recent_attempt["stop_reason"]
    assert recent_attempt["connector_debug_focus"] == ""
    assert recent_attempt["connector_debug_checks"] == []
    preflight = rows[0]["preflight"]
    assert preflight["gate_mode"] == "local_then_docker"
    assert len(preflight["reports"]) == 3
    app_server_metrics = rows[0]["app_server_metrics"]
    assert app_server_metrics["app_server_attempts"] == 0
    assert app_server_metrics["app_server_attempts_with_material_diff"] == 0
    assert app_server_metrics["app_server_attempts_with_zero_diff"] == 0
    assert app_server_metrics["zero_diff_rate_by_task_kind"] == {}


def test_status_rows_include_cached_preflight_reports(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    state_root = tmp_path / "state"
    service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(state_root)),
            repos=[
                RelaySettings(
                    repo_name="demo",
                    healer_repo_path=str(repo_path),
                    healer_repo_slug="owner/repo",
                    healer_test_gate_mode="docker_only",
                )
            ],
        )
    )
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.set_state(
        preflight_cache_key(gate_mode="docker_only", language="node"),
        (
            '{"checked_at":"2026-03-06 20:00:00","execution_root":"e2e-smoke/node",'
            '"failure_class":"","gate_mode":"docker_only","language":"node","output_tail":"",'
            '"status":"ready","summary":"Preflight passed","test_summary":{"failed_tests":0}}'
        ),
    )
    runtime.store.close()

    rows = service.status_rows("demo")

    node_report = next(report for report in rows[0]["preflight"]["reports"] if report["language"] == "node")
    assert node_report["status"] == "ready"
    assert node_report["summary"] == "Preflight passed"


def test_doctor_rows_report_circuit_breaker_state(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    state_root = tmp_path / "state"
    service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(state_root)),
            repos=[RelaySettings(repo_name="demo", healer_repo_path=str(repo_path), healer_repo_slug="owner/repo")],
        )
    )

    rows = service.doctor_rows("demo")

    assert rows[0]["circuit_breaker_open"] is False
    assert rows[0]["circuit_breaker_cooldown_remaining_seconds"] == 0
    assert "connector_command" in rows[0]
    assert "launchd_path_has_connector" in rows[0]
    assert "connector_last_health_error" in rows[0]
    assert "connector_last_runtime_error_kind" in rows[0]
    assert "connector_last_runtime_stdout_tail" in rows[0]
    assert "connector_last_runtime_stderr_tail" in rows[0]
    assert rows[0]["skill_contracts_ok"] is True
    assert rows[0]["skill_contracts"]["recommended_skill_by_diagnosis"]["connector_or_patch_generation"] == (
        "flow-healer-connector-debug"
    )
    connector_playbook = rows[0]["skill_contracts"]["diagnosis_playbooks"]["connector_or_patch_generation"]
    assert connector_playbook["skill"] == "flow-healer-connector-debug"
    assert connector_playbook["next_step_preview"]
    assert connector_playbook["graph_position"] == 6
    assert rows[0]["skill_contracts"]["default_action_by_diagnosis"]["repo_fixture_or_setup"].startswith("Repair")
    connector_route = rows[0]["skill_contracts"]["diagnosis_routes"]["connector_or_patch_generation"]
    assert connector_route["recommended_skill"] == "flow-healer-connector-debug"
    assert connector_route["graph_position"] == 6
    triage = next(skill for skill in rows[0]["skill_contracts"]["skills"] if skill["skill"] == "flow-healer-triage")
    preflight = next(skill for skill in rows[0]["skill_contracts"]["skills"] if skill["skill"] == "flow-healer-preflight")
    assert triage["has_default_command"] is True
    assert triage["next_skill"] == "flow-healer-pr-followup"
    assert triage["has_stop_conditions"] is False
    assert preflight["has_stop_conditions"] is True
    assert rows[0]["preflight_gate_mode"] == "local_then_docker"
    assert len(rows[0]["preflight_reports"]) == 3


def test_build_runtime_uses_configured_connector_backend(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    state_root = tmp_path / "state"
    repo = RelaySettings(repo_name="demo", healer_repo_path=str(repo_path), healer_repo_slug="owner/repo")

    exec_service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(state_root / "exec"), connector_backend="exec"),
            repos=[repo],
        )
    )
    exec_runtime = exec_service.build_runtime(repo)
    assert isinstance(exec_runtime.connector, CodexCliConnector)
    exec_service._close_runtime(exec_runtime)

    app_server_service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(state_root / "app"), connector_backend="app_server"),
            repos=[repo],
        )
    )
    app_runtime = app_server_service.build_runtime(repo)
    assert isinstance(app_runtime.connector, CodexAppServerConnector)
    app_server_service._close_runtime(app_runtime)


def test_build_runtime_defaults_to_app_server_backend(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    state_root = tmp_path / "state"
    repo = RelaySettings(repo_name="demo", healer_repo_path=str(repo_path), healer_repo_slug="owner/repo")

    service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(state_root)),
            repos=[repo],
        )
    )

    runtime = service.build_runtime(repo)
    assert isinstance(runtime.connector, CodexAppServerConnector)
    service._close_runtime(runtime)
