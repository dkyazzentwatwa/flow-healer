import json
import subprocess
from pathlib import Path

from flow_healer.claude_cli_connector import ClaudeCliConnector
from flow_healer.cline_connector import ClineConnector
from flow_healer.codex_app_server_connector import CodexAppServerConnector
from flow_healer.codex_cli_connector import CodexCliConnector
from flow_healer.config import AppConfig, RelaySettings, ServiceSettings
from flow_healer.fallback_connector import FailoverConnector
from flow_healer.healer_preflight import preflight_cache_key
from flow_healer.healer_tracker import GitHubHealerTracker
from flow_healer.kilo_cli_connector import KiloCliConnector
from flow_healer.local_healer_tracker import LocalHealerTracker
from flow_healer.service import FlowHealerService
from flow_healer.store import SQLiteStore


def _make_demo_service(tmp_path, **repo_overrides) -> FlowHealerService:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    _init_git_repo(repo_path)
    state_root = tmp_path / "state"
    repo_settings = {
        "repo_name": "demo",
        "healer_repo_path": str(repo_path),
        "healer_repo_slug": "owner/repo",
    }
    repo_settings.update(repo_overrides)
    return FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(state_root)),
            repos=[RelaySettings(**repo_settings)],
        )
    )


def _cache_preflight_report(
    runtime,
    *,
    gate_mode: str = "local_then_docker",
    language: str = "node",
    execution_root: str = "e2e-smoke/node",
    status: str = "ready",
    failure_class: str = "",
    summary: str = "Preflight passed",
) -> None:
    runtime.store.set_state(
        preflight_cache_key(gate_mode=gate_mode, language=language, execution_root=execution_root),
        json.dumps(
            {
                "checked_at": "2026-03-06 20:00:00",
                "execution_root": execution_root,
                "failure_class": failure_class,
                "gate_mode": gate_mode,
                "language": language,
                "output_tail": "",
                "status": status,
                "summary": summary,
                "test_summary": {"failed_tests": 0},
            },
            sort_keys=True,
        ),
    )


def _init_git_repo(repo_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "-B", "main"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "flow-healer-tests@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Flow Healer Tests"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    (repo_path / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_path, check=True, capture_output=True, text=True)


def _set_github_token(monkeypatch, service: FlowHealerService) -> None:
    monkeypatch.setenv(service.config.service.github_token_env, "test-token")


def _assert_trust_contract(trust: dict[str, object]) -> None:
    assert set(trust.keys()) == {
        "state",
        "score",
        "summary",
        "why_runnable",
        "why_blocked",
        "recommended_operator_action",
        "dominant_failure_domain",
        "policy_outcome",
        "policy_recommendation",
        "evidence",
    }
    assert isinstance(trust["score"], int)
    assert isinstance(trust["summary"], str)
    assert isinstance(trust["why_runnable"], str)
    assert isinstance(trust["why_blocked"], str)
    assert isinstance(trust["recommended_operator_action"], str)
    assert isinstance(trust["dominant_failure_domain"], str)
    assert isinstance(trust["policy_outcome"], str)
    assert isinstance(trust["policy_recommendation"], str)
    assert isinstance(trust["evidence"], dict)


def _assert_policy_contract(policy: dict[str, object]) -> None:
    assert set(policy.keys()) == {
        "outcome",
        "recommendation",
        "reason_code",
        "summary",
        "evidence",
    }
    assert isinstance(policy["outcome"], str)
    assert isinstance(policy["recommendation"], str)
    assert isinstance(policy["reason_code"], str)
    assert isinstance(policy["summary"], str)
    assert isinstance(policy["evidence"], dict)


def test_status_rows_report_ready_trust_payload(tmp_path, monkeypatch) -> None:
    service = _make_demo_service(tmp_path)
    _set_github_token(monkeypatch, service)

    rows = service.status_rows("demo")

    trust = rows[0]["trust"]
    _assert_trust_contract(trust)
    assert trust["state"] == "ready"
    assert trust["score"] == 100
    assert trust["why_runnable"]
    assert trust["why_blocked"] == ""
    assert trust["recommended_operator_action"] == "continue_autonomous_healing"
    assert trust["dominant_failure_domain"] == ""
    assert trust["policy_outcome"] == "retry"
    assert trust["policy_recommendation"] == "continue_autonomous_healing"


def test_status_rows_report_paused_trust_payload(tmp_path, monkeypatch) -> None:
    service = _make_demo_service(tmp_path)
    _set_github_token(monkeypatch, service)
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.set_state("healer_paused", "true")
    runtime.store.close()

    rows = service.status_rows("demo")

    trust = rows[0]["trust"]
    _assert_trust_contract(trust)
    assert trust["state"] == "paused"
    assert trust["why_blocked"]
    assert trust["recommended_operator_action"] == "resume_repo"
    assert trust["policy_outcome"] == "pause"
    assert trust["policy_recommendation"] == "resume_repo"


def test_status_rows_report_quarantined_trust_payload_when_breaker_open(tmp_path, monkeypatch) -> None:
    service = _make_demo_service(
        tmp_path,
        healer_circuit_breaker_window=5,
        healer_circuit_breaker_failure_rate=0.5,
        healer_circuit_breaker_cooldown_seconds=300,
    )
    _set_github_token(monkeypatch, service)
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
    for idx in range(5):
        runtime.store.create_healer_attempt(
            attempt_id=f"ha_breaker_{idx}",
            issue_id="1",
            attempt_no=idx + 1,
            state="running",
            prediction_source="path_level",
            predicted_lock_set=["repo:*"],
        )
        runtime.store.finish_healer_attempt(
            attempt_id=f"ha_breaker_{idx}",
            state="failed",
            actual_diff_set=[],
            test_summary={},
            verifier_summary={},
            failure_class="tests_failed",
            failure_reason="Targeted sandbox validation failed.",
        )
    runtime.store.close()

    rows = service.status_rows("demo")

    trust = rows[0]["trust"]
    _assert_trust_contract(trust)
    assert trust["state"] == "quarantined"
    assert trust["score"] == 0
    assert trust["why_blocked"]
    assert trust["recommended_operator_action"] == "inspect_circuit_breaker"
    assert trust["policy_outcome"] == "quarantine"
    assert trust["policy_recommendation"] == "inspect_circuit_breaker"


def test_status_rows_report_environment_fix_trust_payload_for_blocked_preflight(tmp_path, monkeypatch) -> None:
    service = _make_demo_service(tmp_path, healer_test_gate_mode="docker_only")
    _set_github_token(monkeypatch, service)
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    _cache_preflight_report(
        runtime,
        gate_mode="docker_only",
        status="failed",
        failure_class="tool_missing",
        summary="Preflight requires `pnpm` but it is not available in PATH.",
    )
    runtime.store.close()

    rows = service.status_rows("demo")

    trust = rows[0]["trust"]
    _assert_trust_contract(trust)
    assert trust["state"] == "needs_environment_fix"
    assert trust["why_blocked"]
    assert trust["recommended_operator_action"] == "repair_environment"
    assert trust["policy_outcome"] == "pause"
    assert trust["policy_recommendation"] == "repair_environment"


def test_status_rows_report_contract_fix_trust_payload_for_needs_clarification(tmp_path, monkeypatch) -> None:
    service = _make_demo_service(tmp_path)
    _set_github_token(monkeypatch, service)
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.upsert_healer_issue(
        issue_id="7",
        repo="owner/repo",
        title="Issue 7",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    runtime.store.set_healer_issue_state(issue_id="7", state="needs_clarification")
    runtime.store.close()

    rows = service.status_rows("demo")

    trust = rows[0]["trust"]
    _assert_trust_contract(trust)
    assert trust["state"] == "needs_contract_fix"
    assert trust["why_blocked"]
    assert trust["recommended_operator_action"] == "tighten_issue_contract"
    assert trust["policy_outcome"] == "require_human_fix"
    assert trust["policy_recommendation"] == "tighten_issue_contract"


def test_status_rows_include_why_for_queued_issue_ready_to_run(tmp_path, monkeypatch) -> None:
    service = _make_demo_service(tmp_path)
    _set_github_token(monkeypatch, service)
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.upsert_healer_issue(
        issue_id="11",
        repo="owner/repo",
        title="Issue 11",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    runtime.store.set_healer_issue_state(issue_id="11", state="queued")
    runtime.store.close()

    rows = service.status_rows("demo")

    issue_reason = rows[0]["issue_explanations"][0]
    assert issue_reason["issue_id"] == "11"
    assert issue_reason["reason_code"] == "eligible"
    assert issue_reason["blocking"] is False
    assert issue_reason["recommended_action"] == "continue_autonomous_healing"
    assert "queued" in issue_reason["summary"].lower()


def test_status_rows_include_why_for_needs_clarification_issue(tmp_path, monkeypatch) -> None:
    service = _make_demo_service(tmp_path)
    _set_github_token(monkeypatch, service)
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.upsert_healer_issue(
        issue_id="12",
        repo="owner/repo",
        title="Issue 12",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    runtime.store.set_healer_issue_state(issue_id="12", state="needs_clarification")
    runtime.store.close()

    rows = service.status_rows("demo")

    issue_reason = rows[0]["issue_explanations"][0]
    assert issue_reason["issue_id"] == "12"
    assert issue_reason["reason_code"] == "needs_clarification"
    assert issue_reason["blocking"] is True
    assert issue_reason["recommended_action"] == "tighten_issue_contract"
    assert "structured" in issue_reason["summary"].lower()


def test_status_rows_surface_pause_policy_for_infra_heavy_repo(tmp_path, monkeypatch) -> None:
    service = _make_demo_service(tmp_path)
    _set_github_token(monkeypatch, service)
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.set_states(
        {
            "healer_failure_domain_total": "8",
            "healer_failure_domain_infra": "6",
            "healer_failure_domain_contract": "1",
            "healer_failure_domain_code": "1",
            "healer_retry_playbook_total": "8",
            "healer_retry_playbook_domain_infra": "6",
            "healer_retry_playbook_domain_contract": "1",
            "healer_retry_playbook_domain_code": "1",
            "healer_retry_playbook_last_strategy": "always_requeue_infra",
            "healer_infra_pause_until": "2099-01-01 00:00:00",
            "healer_infra_pause_reason": "infra_pause: docker daemon unavailable",
        }
    )
    runtime.store.close()

    rows = service.status_rows("demo")

    policy = rows[0]["policy"]
    _assert_policy_contract(policy)
    assert policy["outcome"] == "pause"
    assert policy["recommendation"] == "repair_environment"
    assert policy["reason_code"] == "infra_pause_active"
    assert rows[0]["trust"]["policy_outcome"] == "pause"


def test_status_rows_surface_require_human_fix_for_contract_heavy_repo(tmp_path, monkeypatch) -> None:
    service = _make_demo_service(tmp_path)
    _set_github_token(monkeypatch, service)
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.set_states(
        {
            "healer_failure_domain_total": "10",
            "healer_failure_domain_contract": "7",
            "healer_failure_domain_code": "2",
            "healer_failure_domain_unknown": "1",
            "healer_retry_playbook_total": "10",
            "healer_retry_playbook_domain_contract": "7",
            "healer_retry_playbook_domain_code": "2",
            "healer_retry_playbook_domain_unknown": "1",
            "healer_retry_playbook_class_no_patch": "4",
            "healer_retry_playbook_class_scope_violation": "3",
            "healer_retry_playbook_last_failure_domain": "contract",
            "healer_retry_playbook_last_strategy": "adaptive_failure_strategy",
        }
    )
    runtime.store.close()

    rows = service.status_rows("demo")

    policy = rows[0]["policy"]
    _assert_policy_contract(policy)
    assert policy["outcome"] == "require_human_fix"
    assert policy["recommendation"] == "tighten_issue_contract"
    assert policy["reason_code"] == "contract_failures_dominate"
    assert rows[0]["trust"]["policy_recommendation"] == "tighten_issue_contract"


def test_status_rows_surface_require_human_fix_for_repeated_no_op_failures(tmp_path, monkeypatch) -> None:
    service = _make_demo_service(tmp_path)
    _set_github_token(monkeypatch, service)
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.upsert_healer_issue(
        issue_id="91",
        repo="owner/repo",
        title="Issue 91",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    for idx, failure_class in enumerate(["no_patch", "no_workspace_change", "empty_diff", "tests_failed"], start=1):
        attempt_id = f"ha_noop_{idx}"
        runtime.store.create_healer_attempt(
            attempt_id=attempt_id,
            issue_id="91",
            attempt_no=idx,
            state="running",
            prediction_source="path_level",
            predicted_lock_set=["repo:*"],
        )
        runtime.store.finish_healer_attempt(
            attempt_id=attempt_id,
            state="failed",
            actual_diff_set=[],
            test_summary={},
            verifier_summary={},
            failure_class=failure_class,
            failure_reason=f"{failure_class} failed",
        )
    runtime.store.set_states(
        {
            "healer_retry_playbook_total": "4",
            "healer_retry_playbook_domain_contract": "3",
            "healer_retry_playbook_domain_code": "1",
            "healer_retry_playbook_class_no_patch": "2",
            "healer_retry_playbook_class_empty_diff": "1",
        }
    )
    runtime.store.close()

    rows = service.status_rows("demo")

    policy = rows[0]["policy"]
    _assert_policy_contract(policy)
    assert policy["outcome"] == "require_human_fix"
    assert policy["recommendation"] == "tighten_issue_contract"
    assert policy["reason_code"] == "no_op_rate_high"


def test_status_rows_surface_require_human_fix_for_wrong_root_failures(tmp_path, monkeypatch) -> None:
    service = _make_demo_service(tmp_path)
    _set_github_token(monkeypatch, service)
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.upsert_healer_issue(
        issue_id="92",
        repo="owner/repo",
        title="Issue 92",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    for idx, source in enumerate(["fallback", "unknown", "language_default", "workspace_hint"], start=1):
        attempt_id = f"ha_root_{idx}"
        runtime.store.create_healer_attempt(
            attempt_id=attempt_id,
            issue_id="92",
            attempt_no=idx,
            state="running",
            prediction_source="path_level",
            predicted_lock_set=["repo:*"],
        )
        runtime.store.finish_healer_attempt(
            attempt_id=attempt_id,
            state="failed",
            actual_diff_set=[],
            test_summary={"execution_root_source": source},
            verifier_summary={},
            failure_class="language_unresolved" if source == "unknown" else "tests_failed",
            failure_reason=f"{source} execution root failed",
        )
    runtime.store.close()

    rows = service.status_rows("demo")

    policy = rows[0]["policy"]
    _assert_policy_contract(policy)
    assert policy["outcome"] == "require_human_fix"
    assert policy["recommendation"] == "strengthen_execution_root_hints"
    assert policy["reason_code"] == "wrong_root_rate_high"


def test_doctor_rows_report_trust_payload(tmp_path, monkeypatch) -> None:
    service = _make_demo_service(tmp_path, healer_test_gate_mode="docker_only")
    _set_github_token(monkeypatch, service)
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    _cache_preflight_report(
        runtime,
        gate_mode="docker_only",
        status="failed",
        failure_class="tool_missing",
        summary="Preflight requires `pnpm` but it is not available in PATH.",
    )
    runtime.store.close()

    rows = service.doctor_rows("demo")

    trust = rows[0]["trust"]
    _assert_trust_contract(trust)
    assert trust["state"] == "needs_environment_fix"
    assert trust["recommended_operator_action"] == "repair_environment"


def test_status_rows_do_not_report_ready_when_repo_path_or_token_is_missing(tmp_path, monkeypatch) -> None:
    missing_repo_path = tmp_path / "missing-repo"
    service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(tmp_path / "state")),
            repos=[
                RelaySettings(
                    repo_name="demo",
                    healer_repo_path=str(missing_repo_path),
                    healer_repo_slug="owner/repo",
                )
            ],
        )
    )
    monkeypatch.delenv(service.config.service.github_token_env, raising=False)

    rows = service.status_rows("demo")

    trust = rows[0]["trust"]
    _assert_trust_contract(trust)
    assert trust["state"] == "needs_environment_fix"
    assert trust["why_blocked"]
    assert trust["recommended_operator_action"] == "repair_environment"


def test_doctor_rows_do_not_report_ready_when_repo_path_or_token_is_missing(tmp_path, monkeypatch) -> None:
    missing_repo_path = tmp_path / "missing-repo"
    service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(tmp_path / "state")),
            repos=[
                RelaySettings(
                    repo_name="demo",
                    healer_repo_path=str(missing_repo_path),
                    healer_repo_slug="owner/repo",
                )
            ],
        )
    )
    monkeypatch.delenv(service.config.service.github_token_env, raising=False)

    rows = service.doctor_rows("demo")

    trust = rows[0]["trust"]
    _assert_trust_contract(trust)
    assert trust["state"] == "needs_environment_fix"
    assert trust["why_blocked"]
    assert trust["recommended_operator_action"] == "repair_environment"


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
    runtime.store.update_runtime_status(status="swarm_repairing", last_error="", touch_heartbeat=True)
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
    assert connector["routing_mode"] == "single_backend"
    assert connector["code_backend"] == "app_server"
    assert connector["non_code_backend"] == "app_server"
    assert "available" in connector
    assert "configured_command" in connector
    assert "resolved_command" in connector
    assert "last_error_class" in connector
    assert "last_runtime_error_kind" in connector
    assert "last_runtime_stdout_tail" in connector
    assert "last_runtime_stderr_tail" in connector
    assert "app_server" in connector["backends"]
    tracker = rows[0]["tracker"]
    assert "available" in tracker
    assert "last_error_class" in tracker
    assert "last_error_reason" in tracker
    assert "last_error_at" in tracker
    assert "request_metrics" in tracker
    worker = rows[0]["worker"]
    assert "active_worker_id" in worker
    assert "last_heartbeat_at" in worker
    assert "last_pulse_at" in worker
    assert "last_reconcile_at" in worker
    assert "runtime_status" in worker
    assert worker["runtime_status"] == "swarm_repairing"
    assert "last_tick_started_at" in worker
    assert "last_tick_finished_at" in worker
    assert "recovered_stale_active_issues" in worker
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
    assert len(preflight["reports"]) >= 3
    app_server_metrics = rows[0]["app_server_metrics"]
    assert app_server_metrics["app_server_attempts"] == 0
    assert app_server_metrics["app_server_attempts_with_material_diff"] == 0
    assert app_server_metrics["app_server_attempts_with_zero_diff"] == 0
    assert app_server_metrics["app_server_forced_serialized_recovery_attempts"] == 0
    assert app_server_metrics["app_server_forced_serialized_recovery_success"] == 0
    assert app_server_metrics["app_server_exec_failover_attempts"] == 0
    assert app_server_metrics["app_server_exec_failover_success"] == 0
    assert app_server_metrics["zero_diff_rate_by_task_kind"] == {}
    swarm_metrics = rows[0]["swarm_metrics"]
    assert swarm_metrics["runs"] == 0
    assert swarm_metrics["recovered"] == 0
    assert swarm_metrics["unrecovered"] == 0
    assert swarm_metrics["backend_exec"] == 0
    assert swarm_metrics["backend_app_server"] == 0
    assert swarm_metrics["strategy_counts"]["repair"] == 0
    assert swarm_metrics["skipped_domain"] == 0
    assert swarm_metrics["skipped_by_domain"]["infra"] == 0
    assert swarm_metrics["skipped_by_domain"]["contract"] == 0
    assert swarm_metrics["skipped_by_domain"]["unknown"] == 0
    failure_domains = rows[0]["failure_domain_metrics"]
    assert failure_domains == {"total": 0, "infra": 0, "contract": 0, "code": 0, "unknown": 0}
    retry_playbook = rows[0]["retry_playbook_metrics"]
    assert retry_playbook["total"] == 0
    assert retry_playbook["class_counts"] == {}
    assert retry_playbook["domain_counts"] == {}
    assert retry_playbook["strategy_counts"] == {}
    assert retry_playbook["recommendation"]
    assert retry_playbook["last_selection"]["failure_class"] == ""
    canary = rows[0]["reliability_canary"]
    assert canary["sample_size"] >= 1
    assert 0.0 <= canary["first_pass_success_rate"] <= 1.0
    assert canary["retries_per_success"] >= 0.0
    assert 0.0 <= canary["wrong_root_execution_rate"] <= 1.0
    assert 0.0 <= canary["no_op_rate"] <= 1.0
    trends = rows[0]["reliability_trends"]
    assert set(trends.keys()) == {"7d", "30d"}
    assert "changes" in trends["7d"]
    assert "improvements" in trends["30d"]
    assert isinstance(rows[0]["reliability_daily_rollups"], list)
    resource_audit = rows[0]["resource_audit"]
    assert resource_audit["worktrees"]["count"] == 0
    assert resource_audit["leases"]["total"] == 0
    assert resource_audit["locks"]["active"] == 0
    assert resource_audit["docker"]["prune_enabled"] is False


def test_status_rows_report_swarm_domain_skip_counters(tmp_path) -> None:
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
                )
            ],
        )
    )
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.set_state("healer_swarm_skipped_domain", "4")
    runtime.store.set_state("healer_swarm_skipped_domain_infra", "2")
    runtime.store.set_state("healer_swarm_skipped_domain_contract", "1")
    runtime.store.set_state("healer_swarm_skipped_domain_unknown", "1")
    runtime.store.close()

    rows = service.status_rows("demo")

    swarm_metrics = rows[0]["swarm_metrics"]
    assert swarm_metrics["skipped_domain"] == 4
    assert swarm_metrics["skipped_by_domain"] == {"infra": 2, "contract": 1, "unknown": 1}


def test_status_rows_report_codex_native_multi_agent_counters(tmp_path) -> None:
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
                )
            ],
        )
    )
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.set_state("healer_codex_native_multi_agent_attempts", "3")
    runtime.store.set_state("healer_codex_native_multi_agent_success", "1")
    runtime.store.set_state("healer_codex_native_multi_agent_recovery_attempts", "2")
    runtime.store.set_state("healer_codex_native_multi_agent_recovery_success", "1")
    runtime.store.set_state("healer_codex_native_multi_agent_fallback_to_swarm", "1")
    runtime.store.set_state("healer_codex_native_multi_agent_skipped_backend", "4")
    runtime.store.set_state("healer_codex_native_multi_agent_skipped_task_kind", "2")
    runtime.store.close()

    rows = service.status_rows("demo")

    assert rows[0]["codex_native_multi_agent_metrics"] == {
        "attempts": 3,
        "success": 1,
        "recovery_attempts": 2,
        "recovery_success": 1,
        "fallback_to_swarm": 1,
        "skipped_backend": 4,
        "skipped_task_kind": 2,
    }


def test_status_rows_report_failure_domain_counters(tmp_path) -> None:
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
                )
            ],
        )
    )
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.set_state("healer_failure_domain_total", "7")
    runtime.store.set_state("healer_failure_domain_infra", "2")
    runtime.store.set_state("healer_failure_domain_contract", "3")
    runtime.store.set_state("healer_failure_domain_code", "1")
    runtime.store.set_state("healer_failure_domain_unknown", "1")
    runtime.store.close()

    rows = service.status_rows("demo")

    assert rows[0]["failure_domain_metrics"] == {
        "total": 7,
        "infra": 2,
        "contract": 3,
        "code": 1,
        "unknown": 1,
    }


def test_status_rows_report_retry_playbook_metrics(tmp_path) -> None:
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
                )
            ],
        )
    )
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.set_states(
        {
            "healer_retry_playbook_total": "9",
            "healer_retry_playbook_class_tests_failed": "4",
            "healer_retry_playbook_class_no_patch": "3",
            "healer_retry_playbook_class_push_failed": "2",
            "healer_retry_playbook_domain_code": "4",
            "healer_retry_playbook_domain_contract": "3",
            "healer_retry_playbook_domain_infra": "2",
            "healer_retry_playbook_strategy_adaptive_failure_strategy": "4",
            "healer_retry_playbook_strategy_always_requeue_failure_class": "3",
            "healer_retry_playbook_strategy_always_requeue_infra": "2",
            "healer_retry_playbook_last_issue_id": "777",
            "healer_retry_playbook_last_failure_class": "tests_failed",
            "healer_retry_playbook_last_failure_domain": "code",
            "healer_retry_playbook_last_strategy": "adaptive_failure_strategy",
            "healer_retry_playbook_last_backoff_seconds": "30",
            "healer_retry_playbook_last_feedback_hint": "Focus on failing test output.",
            "healer_retry_playbook_last_selected_at": "2026-03-10 10:15:00",
        }
    )
    runtime.store.close()

    rows = service.status_rows("demo")
    metrics = rows[0]["retry_playbook_metrics"]

    assert metrics["total"] == 9
    assert metrics["class_counts"]["tests_failed"] == 4
    assert metrics["domain_counts"]["code"] == 4
    assert metrics["strategy_counts"]["adaptive_failure_strategy"] == 4
    assert metrics["top_failure_classes"][0] == {"failure_class": "tests_failed", "count": 4}
    assert metrics["dominant_domain"] == "code"
    assert metrics["last_selection"]["issue_id"] == "777"
    assert metrics["last_selection"]["backoff_seconds"] == 30


def test_status_rows_report_reliability_canary_metrics(tmp_path) -> None:
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
                )
            ],
        )
    )
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.upsert_healer_issue(
        issue_id="9001",
        repo="owner/repo",
        title="Issue 9001",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    runtime.store.upsert_healer_issue(
        issue_id="9002",
        repo="owner/repo",
        title="Issue 9002",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )

    runtime.store.create_healer_attempt(
        attempt_id="ha_9001_1",
        issue_id="9001",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    runtime.store.finish_healer_attempt(
        attempt_id="ha_9001_1",
        state="pr_open",
        actual_diff_set=[],
        test_summary={"execution_root_source": "issue"},
        verifier_summary={},
        failure_class="",
        failure_reason="",
    )
    runtime.store.create_healer_attempt(
        attempt_id="ha_9002_1",
        issue_id="9002",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    runtime.store.finish_healer_attempt(
        attempt_id="ha_9002_1",
        state="failed",
        actual_diff_set=[],
        test_summary={"execution_root_source": "fallback"},
        verifier_summary={},
        failure_class="no_patch",
        failure_reason="no patch",
    )
    runtime.store.create_healer_attempt(
        attempt_id="ha_9002_2",
        issue_id="9002",
        attempt_no=2,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    runtime.store.finish_healer_attempt(
        attempt_id="ha_9002_2",
        state="pr_open",
        actual_diff_set=[],
        test_summary={"execution_root_source": "issue"},
        verifier_summary={},
        failure_class="",
        failure_reason="",
    )
    runtime.store.close()

    rows = service.status_rows("demo")

    canary = rows[0]["reliability_canary"]
    assert canary["sample_size"] == 3
    assert canary["issue_count"] == 2
    assert canary["first_pass_success_rate"] == 0.5
    assert canary["retries_per_success"] == 0.5
    assert canary["wrong_root_execution_rate"] == 0.3333
    assert canary["no_op_rate"] == 0.3333


def test_status_rows_report_reliability_trend_deltas(tmp_path) -> None:
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
                )
            ],
        )
    )
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    for issue_id in ("9101", "9102", "9103", "9104"):
        runtime.store.upsert_healer_issue(
            issue_id=issue_id,
            repo="owner/repo",
            title=f"Issue {issue_id}",
            body="",
            author="alice",
            labels=["healer:ready"],
            priority=5,
        )

    runtime.store.create_healer_attempt(
        attempt_id="ha_curr_success",
        issue_id="9101",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    runtime.store.finish_healer_attempt(
        attempt_id="ha_curr_success",
        state="pr_open",
        actual_diff_set=[],
        test_summary={"execution_root_source": "issue"},
        verifier_summary={},
    )
    runtime.store.create_healer_attempt(
        attempt_id="ha_curr_noop",
        issue_id="9102",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    runtime.store.finish_healer_attempt(
        attempt_id="ha_curr_noop",
        state="failed",
        actual_diff_set=[],
        test_summary={"execution_root_source": "fallback"},
        verifier_summary={},
        failure_class="no_patch",
        failure_reason="no patch",
    )
    runtime.store.create_healer_attempt(
        attempt_id="ha_prev_fail_1",
        issue_id="9103",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    runtime.store.finish_healer_attempt(
        attempt_id="ha_prev_fail_1",
        state="failed",
        actual_diff_set=[],
        test_summary={"execution_root_source": "fallback"},
        verifier_summary={},
        failure_class="no_patch",
        failure_reason="no patch",
    )
    runtime.store.create_healer_attempt(
        attempt_id="ha_prev_fail_2",
        issue_id="9104",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    runtime.store.finish_healer_attempt(
        attempt_id="ha_prev_fail_2",
        state="failed",
        actual_diff_set=[],
        test_summary={"execution_root_source": "fallback"},
        verifier_summary={},
        failure_class="no_patch",
        failure_reason="no patch",
    )

    conn = runtime.store._connect()
    with runtime.store._lock:
        conn.execute(
            """
            UPDATE healer_attempts
            SET started_at = datetime('now', '-10 days'),
                finished_at = datetime('now', '-10 days', '+2 minutes')
            WHERE attempt_id IN ('ha_prev_fail_1', 'ha_prev_fail_2')
            """
        )
        conn.commit()
    runtime.store.close()

    rows = service.status_rows("demo")
    trends_7d = rows[0]["reliability_trends"]["7d"]
    daily_rollups = rows[0]["reliability_daily_rollups"]

    assert trends_7d["current"]["sample_size"] == 2
    assert trends_7d["previous"]["sample_size"] == 2
    assert trends_7d["changes"]["first_pass_success_rate"] == 0.5
    assert trends_7d["changes"]["no_op_rate"] == -0.5
    assert trends_7d["improvements"]["no_op_rate_down"] == 0.5
    assert len(daily_rollups) >= 2
    assert "day" in daily_rollups[0]


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
        preflight_cache_key(gate_mode="docker_only", language="node", execution_root="e2e-smoke/node"),
        (
            '{"checked_at":"2026-03-06 20:00:00","execution_root":"e2e-smoke/node",'
            '"failure_class":"","gate_mode":"docker_only","language":"node","output_tail":"",'
            '"status":"ready","summary":"Preflight passed","test_summary":{"failed_tests":0}}'
        ),
    )
    runtime.store.close()

    rows = service.status_rows("demo")

    node_report = next(
        report
        for report in rows[0]["preflight"]["reports"]
        if report["language"] == "node" and report["execution_root"] == "e2e-smoke/node"
    )
    assert node_report["status"] == "ready"
    assert node_report["summary"] == "Preflight passed"
    assert node_report["readiness_score"] == 100
    assert node_report["readiness_class"] == "ready"
    assert node_report["blocking"] is False
    preflight_summary = rows[0]["preflight"]["summary"]
    assert preflight_summary["total"] >= 1
    assert preflight_summary["overall_class"] in {"ready", "degraded", "blocked"}


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
    assert "tracker_available" in rows[0]
    assert "tracker_last_error_class" in rows[0]
    assert "tracker_last_error_reason" in rows[0]
    assert "tracker_last_error_at" in rows[0]
    assert "worker" in rows[0]
    assert "active_worker_id" in rows[0]["worker"]
    assert "recovered_stale_active_issues" in rows[0]["worker"]
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
    assert len(rows[0]["preflight_reports"]) >= 3


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


def test_build_runtime_supports_new_cli_connector_backends(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    state_root = tmp_path / "state"
    repo = RelaySettings(repo_name="demo", healer_repo_path=str(repo_path), healer_repo_slug="owner/repo")

    claude_service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(state_root / "claude"), connector_backend="claude_cli"),
            repos=[repo],
        )
    )
    claude_runtime = claude_service.build_runtime(repo)
    assert isinstance(claude_runtime.connector, FailoverConnector)
    assert isinstance(claude_runtime.connector.primary, ClaudeCliConnector)
    assert isinstance(claude_runtime.connector.fallback, CodexCliConnector)
    claude_service._close_runtime(claude_runtime)

    cline_service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(state_root / "cline"), connector_backend="cline"),
            repos=[repo],
        )
    )
    cline_runtime = cline_service.build_runtime(repo)
    assert isinstance(cline_runtime.connector, FailoverConnector)
    assert isinstance(cline_runtime.connector.primary, ClineConnector)
    assert isinstance(cline_runtime.connector.fallback, CodexCliConnector)
    cline_service._close_runtime(cline_runtime)

    kilo_service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(state_root / "kilo"), connector_backend="kilo_cli"),
            repos=[repo],
        )
    )
    kilo_runtime = kilo_service.build_runtime(repo)
    assert isinstance(kilo_runtime.connector, FailoverConnector)
    assert isinstance(kilo_runtime.connector.primary, KiloCliConnector)
    assert isinstance(kilo_runtime.connector.fallback, CodexCliConnector)
    kilo_service._close_runtime(kilo_runtime)


def test_build_runtime_uses_exec_for_code_routing_mode(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    state_root = tmp_path / "state"
    repo = RelaySettings(repo_name="demo", healer_repo_path=str(repo_path), healer_repo_slug="owner/repo")

    routing_service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(
                state_root=str(state_root),
                connector_routing_mode="exec_for_code",
                code_connector_backend="exec",
                non_code_connector_backend="app_server",
            ),
            repos=[repo],
        )
    )
    runtime = routing_service.build_runtime(repo)
    assert isinstance(runtime.connector, CodexCliConnector)
    assert "exec" in runtime.connectors_by_backend
    assert "app_server" in runtime.connectors_by_backend
    assert isinstance(runtime.connectors_by_backend["exec"], CodexCliConnector)
    assert isinstance(runtime.connectors_by_backend["app_server"], CodexAppServerConnector)
    routing_service._close_runtime(runtime)


def test_build_runtime_uses_non_codex_backends_with_exec_failover_in_exec_for_code_mode(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    state_root = tmp_path / "state"
    repo = RelaySettings(repo_name="demo", healer_repo_path=str(repo_path), healer_repo_slug="owner/repo")

    routing_service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(
                state_root=str(state_root),
                connector_routing_mode="exec_for_code",
                code_connector_backend="cline",
                non_code_connector_backend="kilo_cli",
            ),
            repos=[repo],
        )
    )
    runtime = routing_service.build_runtime(repo)
    assert isinstance(runtime.connector, FailoverConnector)
    assert isinstance(runtime.connectors_by_backend["cline"], FailoverConnector)
    assert isinstance(runtime.connectors_by_backend["kilo_cli"], FailoverConnector)
    assert isinstance(runtime.connectors_by_backend["cline"].fallback, CodexCliConnector)  # type: ignore[attr-defined]
    assert isinstance(runtime.connectors_by_backend["kilo_cli"].fallback, CodexCliConnector)  # type: ignore[attr-defined]
    routing_service._close_runtime(runtime)


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
    assert isinstance(runtime.tracker, GitHubHealerTracker)
    service._close_runtime(runtime)


def test_build_runtime_uses_local_tracker_backend(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    state_root = tmp_path / "state"
    repo = RelaySettings(repo_name="demo", healer_repo_path=str(repo_path), healer_repo_slug="owner/repo")

    service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(state_root), tracker_backend="local_fs"),
            repos=[repo],
        )
    )

    runtime = service.build_runtime(repo)
    assert isinstance(runtime.tracker, LocalHealerTracker)
    assert runtime.tracker.enabled is True
    service._close_runtime(runtime)


def test_status_rows_include_new_app_server_recovery_metric_keys(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    state_root = tmp_path / "state"
    service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(state_root)),
            repos=[RelaySettings(repo_name="demo", healer_repo_path=str(repo_path), healer_repo_slug="owner/repo")],
        )
    )

    rows = service.status_rows("demo")
    metrics = rows[0]["app_server_metrics"]

    assert metrics["app_server_forced_serialized_recovery_attempts"] == 0
    assert metrics["app_server_forced_serialized_recovery_success"] == 0
    assert metrics["app_server_exec_failover_attempts"] == 0
    assert metrics["app_server_exec_failover_success"] == 0


def test_request_helper_recycle_sets_live_daemon_request_state(tmp_path) -> None:
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

    rows = service.request_helper_recycle("demo", idle_only=True)

    assert rows[0]["repo"] == "demo"
    assert rows[0]["requested"] is True
    assert rows[0]["idle_only"] is True
    store = SQLiteStore(service.config.repo_db_path("demo"))
    store.bootstrap()
    assert store.get_state("healer_helper_recycle_requested_at")
    assert store.get_state("healer_helper_recycle_idle_only") == "true"
    assert store.get_state("healer_helper_recycle_status") == "requested"
    store.close()


def test_status_rows_reuses_cached_snapshot_within_ttl(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    state_root = tmp_path / "state"
    repo = RelaySettings(
        repo_name="demo",
        healer_repo_path=str(repo_path),
        healer_repo_slug="owner/repo",
        healer_status_cache_ttl_seconds=60,
    )
    service = FlowHealerService(
        AppConfig(
            service=ServiceSettings(state_root=str(state_root)),
            repos=[repo],
        )
    )

    build_calls = 0
    original_build_runtime = service.build_runtime

    def counted_build_runtime(selected_repo):
        nonlocal build_calls
        build_calls += 1
        return original_build_runtime(selected_repo)

    service.build_runtime = counted_build_runtime  # type: ignore[method-assign]

    first = service.status_rows("demo")
    second = service.status_rows("demo")

    assert len(first) == 1
    assert len(second) == 1
    assert build_calls == 1


def test_status_rows_report_issue_outcome_metrics(tmp_path) -> None:
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
                )
            ],
        )
    )
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    for issue_id in ("9201", "9202", "9203", "9204"):
        runtime.store.upsert_healer_issue(
            issue_id=issue_id,
            repo="owner/repo",
            title=f"Issue {issue_id}",
            body="",
            author="alice",
            labels=["healer:ready"],
            priority=5,
        )

    runtime.store.set_healer_issue_state(issue_id="9201", state="pr_open")
    runtime.store.set_healer_issue_state(issue_id="9202", state="resolved")
    runtime.store.set_healer_issue_state(issue_id="9203", state="failed")
    runtime.store.set_healer_issue_state(issue_id="9204", state="queued")

    conn = runtime.store._connect()
    conn.execute("UPDATE healer_issues SET updated_at = ? WHERE issue_id = ?", ("2026-03-10 09:00:00", "9201"))
    conn.execute("UPDATE healer_issues SET updated_at = ? WHERE issue_id = ?", ("2026-03-10 08:00:00", "9202"))
    conn.execute("UPDATE healer_issues SET updated_at = ? WHERE issue_id = ?", ("2026-03-10 07:00:00", "9203"))
    conn.execute("UPDATE healer_issues SET updated_at = ? WHERE issue_id = ?", ("2026-03-10 06:00:00", "9204"))
    conn.commit()
    runtime.store.close()

    rows = service.status_rows("demo")

    outcome_metrics = rows[0]["issue_outcomes"]
    assert outcome_metrics["success"] == 2
    assert outcome_metrics["failure"] == 1
    assert outcome_metrics["active"] == 1
    assert outcome_metrics["terminal_total"] == 3
    assert outcome_metrics["current_success_streak"] == 2
    assert [item["outcome"] for item in outcome_metrics["recent_terminal_outcomes"]] == [
        "success",
        "success",
        "failure",
    ]


def test_status_rows_surface_phased_validation_state_from_recent_attempts(tmp_path, monkeypatch) -> None:
    service = _make_demo_service(tmp_path)
    _set_github_token(monkeypatch, service)
    runtime = service.build_runtime(service.config.select_repos("demo")[0])
    runtime.store.upsert_healer_issue(
        issue_id="301",
        repo="owner/repo",
        title="Issue 301",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    runtime.store.create_healer_attempt(
        attempt_id="ha_301_1",
        issue_id="301",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    runtime.store.finish_healer_attempt(
        attempt_id="ha_301_1",
        state="pr_open",
        actual_diff_set=[],
        test_summary={
            "validation_lane": "fast_then_full",
            "promotion_state": "promotion_ready",
            "phase_states": {
                "fast_pass": True,
                "full_pass": True,
                "promotion_ready": True,
                "merge_blocked": False,
            },
        },
        verifier_summary={},
    )
    runtime.store.close()

    rows = service.status_rows("demo")

    attempt = rows[0]["recent_attempts"][0]
    assert attempt["validation_lane"] == "fast_then_full"
    assert attempt["promotion_state"] == "promotion_ready"
    assert attempt["phase_states"]["promotion_ready"] is True
