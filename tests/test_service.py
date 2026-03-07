from pathlib import Path

from flow_healer.config import AppConfig, RelaySettings, ServiceSettings
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
    assert recent_attempt["diagnosis"] == "operator_or_environment"
    assert recent_attempt["recommended_skill"] == "flow-healer-local-validation"
    assert recent_attempt["default_action"]
    assert recent_attempt["stop_recommended"] is True
    assert recent_attempt["stop_reason"]
    assert recent_attempt["connector_debug_focus"] == ""


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
    assert rows[0]["skill_contracts"]["default_action_by_diagnosis"]["repo_fixture_or_setup"].startswith("Repair")
    triage = next(skill for skill in rows[0]["skill_contracts"]["skills"] if skill["skill"] == "flow-healer-triage")
    preflight = next(skill for skill in rows[0]["skill_contracts"]["skills"] if skill["skill"] == "flow-healer-preflight")
    assert triage["has_default_command"] is True
    assert triage["has_stop_conditions"] is False
    assert preflight["has_stop_conditions"] is True
