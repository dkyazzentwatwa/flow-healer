from __future__ import annotations

import os
from pathlib import Path

import pytest

from flow_healer.config import AppConfig


def test_load_reads_github_token_from_env_file(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("GITHUB_TOKEN=test-token\n", encoding="utf-8")

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "service:",
                "  github_token_env: GITHUB_TOKEN",
                "  env_file: .env",
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
                "    repo_slug: owner/repo",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    config = AppConfig.load(config_path)

    assert config.service.env_file == str(Path(env_path).resolve())
    assert config.service.github_token_env == "GITHUB_TOKEN"
    assert config.service.poll_interval_seconds == 30.0
    assert config.service.connector_backend == "app_server"
    assert config.service.connector_routing_mode == "single_backend"
    assert config.service.code_connector_backend == "app_server"
    assert config.service.non_code_connector_backend == "app_server"
    assert config.service.connector_model == "gpt-5.4"
    assert config.service.connector_reasoning_effort == "medium"
    assert config.control.web.enabled is True
    assert config.control.web.auth_mode == "token"
    assert config.control.web.auth_token_env == "FLOW_HEALER_WEB_TOKEN"
    assert config.control.mail.subject_prefix == "FH:"
    assert config.select_repos("demo")[0].repo_name == "demo"
    relay = config.select_repos("demo")[0]
    assert relay.healer_max_concurrent_issues == 3
    assert relay.healer_pr_actions_require_approval is False
    assert relay.healer_pr_auto_approve_clean is False
    assert relay.healer_pr_auto_merge_clean is False
    assert relay.healer_pr_merge_method == "squash"
    assert relay.healer_verifier_policy == "required"
    assert relay.healer_local_gate_policy == "auto"
    assert relay.healer_issue_contract_mode == "lenient"
    assert relay.healer_parse_confidence_threshold == 0.3
    assert relay.healer_status_cache_ttl_seconds == 5
    assert relay.healer_housekeeping_interval_seconds == 300
    assert relay.healer_blocked_label_repair_interval_seconds == 600
    assert relay.healer_language == ""
    assert relay.healer_docker_image == ""
    assert relay.healer_test_command == ""
    assert relay.healer_install_command == ""
    assert config_path.parent.joinpath(".env").exists()
    assert os.environ["GITHUB_TOKEN"] == "test-token"


def test_load_reads_language_strategy_overrides(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
                "    repo_slug: owner/repo",
                "    local_gate_policy: force",
                "    language: node",
                "    docker_image: node:22",
                "    test_command: npm run test:ci -- --watch=false",
                "    install_command: npm ci",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)
    relay = config.select_repos("demo")[0]

    assert relay.healer_local_gate_policy == "force"
    assert relay.healer_language == "node"
    assert relay.healer_docker_image == "node:22"
    assert relay.healer_test_command == "npm run test:ci -- --watch=false"
    assert relay.healer_install_command == "npm ci"


def test_load_reads_runtime_optimization_overrides(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
                "    status_cache_ttl_seconds: 9",
                "    housekeeping_interval_seconds: 120",
                "    blocked_label_repair_interval_seconds: 240",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)
    relay = config.select_repos("demo")[0]

    assert relay.healer_status_cache_ttl_seconds == 9
    assert relay.healer_housekeeping_interval_seconds == 120
    assert relay.healer_blocked_label_repair_interval_seconds == 240


def test_load_reads_issue_contract_mode_and_parse_threshold(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
                "    issue_contract_mode: strict",
                "    parse_confidence_threshold: 0.55",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)
    relay = config.select_repos("demo")[0]

    assert relay.healer_issue_contract_mode == "strict"
    assert relay.healer_parse_confidence_threshold == 0.55


def test_load_normalizes_invalid_issue_contract_mode_and_threshold(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
                "    issue_contract_mode: relaxed",
                "    parse_confidence_threshold: 4.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)
    relay = config.select_repos("demo")[0]

    assert relay.healer_issue_contract_mode == "lenient"
    assert relay.healer_parse_confidence_threshold == 1.0


def test_load_rejects_removed_language_override(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
                "    language: ruby",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="supports only python and node"):
        AppConfig.load(config_path)


def test_load_normalizes_connector_backend(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "service:",
                "  connector_backend: app-server",
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)

    assert config.service.connector_backend == "app_server"


def test_load_normalizes_invalid_connector_backend_to_app_server(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "service:",
                "  connector_backend: strange-backend",
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)

    assert config.service.connector_backend == "app_server"


def test_load_normalizes_new_connector_backends(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "service:",
                "  connector_backend: claude-cli",
                "  connector_routing_mode: exec_for_code",
                "  code_connector_backend: cline",
                "  non_code_connector_backend: kilo-cli",
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)

    assert config.service.connector_backend == "claude_cli"
    assert config.service.code_connector_backend == "cline"
    assert config.service.non_code_connector_backend == "kilo_cli"


def test_load_reads_new_connector_service_settings(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "service:",
                "  claude_cli_command: /usr/local/bin/claude",
                "  claude_cli_model: claude-sonnet-4-6",
                "  claude_cli_dangerously_skip_permissions: false",
                "  cline_command: /usr/local/bin/cline",
                "  cline_model: gpt-4o",
                "  cline_use_json: false",
                "  cline_act_mode: false",
                "  kilo_cli_command: /usr/local/bin/kilo",
                "  kilo_cli_model: google/gemini-3-flash-preview",
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)

    assert config.service.claude_cli_command == "/usr/local/bin/claude"
    assert config.service.claude_cli_model == "claude-sonnet-4-6"
    assert config.service.claude_cli_dangerously_skip_permissions is False
    assert config.service.cline_command == "/usr/local/bin/cline"
    assert config.service.cline_model == "gpt-4o"
    assert config.service.cline_use_json is False
    assert config.service.cline_act_mode is False
    assert config.service.kilo_cli_command == "/usr/local/bin/kilo"
    assert config.service.kilo_cli_model == "google/gemini-3-flash-preview"


def test_load_supports_exec_for_code_routing_mode(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "service:",
                "  connector_routing_mode: exec_for_code",
                "  code_connector_backend: exec",
                "  non_code_connector_backend: app-server",
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)

    assert config.service.connector_routing_mode == "exec_for_code"
    assert config.service.code_connector_backend == "exec"
    assert config.service.non_code_connector_backend == "app_server"


def test_load_invalid_connector_routing_mode_defaults_to_single_backend(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "service:",
                "  connector_backend: exec",
                "  connector_routing_mode: strange",
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)

    assert config.service.connector_routing_mode == "single_backend"
    assert config.service.code_connector_backend == "exec"
    assert config.service.non_code_connector_backend == "exec"


def test_load_normalizes_verifier_policy(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
                "    verifier_policy: required",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)

    relay = config.select_repos("demo")[0]
    assert relay.healer_verifier_policy == "required"


def test_load_normalizes_unknown_verifier_policy_to_required(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
                "    verifier_policy: sometimes",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)

    relay = config.select_repos("demo")[0]
    assert relay.healer_verifier_policy == "required"


def test_load_reads_web_auth_overrides(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "control:",
                "  web:",
                "    auth_mode: none",
                "    auth_token_env: CUSTOM_WEB_TOKEN",
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)

    assert config.control.web.auth_mode == "none"
    assert config.control.web.auth_token_env == "CUSTOM_WEB_TOKEN"


def test_relay_settings_stuck_pr_timeout_defaults_to_60(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)

    relay = config.select_repos("demo")[0]
    assert relay.healer_stuck_pr_timeout_minutes == 60


def test_relay_settings_stuck_pr_timeout_configurable(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
                "    stuck_pr_timeout_minutes: 30",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)

    relay = config.select_repos("demo")[0]
    assert relay.healer_stuck_pr_timeout_minutes == 30


def test_relay_settings_conflict_requeue_and_dedupe_defaults(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)
    relay = config.select_repos("demo")[0]

    assert relay.healer_conflict_auto_requeue_enabled is True
    assert relay.healer_conflict_auto_requeue_max_attempts == 3
    assert relay.healer_overlap_scope_queue_enabled is True
    assert relay.healer_dedupe_enabled is True
    assert relay.healer_dedupe_close_duplicates is True


def test_relay_settings_conflict_requeue_and_dedupe_configurable(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  - name: demo",
                f"    path: {tmp_path}",
                "    conflict_auto_requeue_enabled: false",
                "    conflict_auto_requeue_max_attempts: 5",
                "    overlap_scope_queue_enabled: false",
                "    dedupe_enabled: false",
                "    dedupe_close_duplicates: false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)
    relay = config.select_repos("demo")[0]

    assert relay.healer_conflict_auto_requeue_enabled is False
    assert relay.healer_conflict_auto_requeue_max_attempts == 5
    assert relay.healer_overlap_scope_queue_enabled is False
    assert relay.healer_dedupe_enabled is False
    assert relay.healer_dedupe_close_duplicates is False


def test_app_config_loads_swarm_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    config_path.write_text(
        (
            "service:\n"
            "  state_root: ~/.flow-healer\n"
            "repos:\n"
            "  - name: demo\n"
            f"    path: {repo_path}\n"
            "    repo_slug: owner/repo\n"
            "    swarm_enabled: true\n"
            "    swarm_mode: failure_repair\n"
            "    swarm_max_parallel_agents: 6\n"
            "    swarm_max_repair_cycles_per_attempt: 2\n"
            "    swarm_analysis_timeout_seconds: 150\n"
            "    swarm_recovery_timeout_seconds: 330\n"
            "    swarm_orphan_subagent_ttl_seconds: 1200\n"
            "    swarm_backend_strategy: match_selected_backend\n"
            "    swarm_trigger_failure_classes:\n"
            "      - tests_failed\n"
            "      - verifier_failed\n"
        ),
        encoding="utf-8",
    )

    config = AppConfig.load(config_path)

    repo = config.repos[0]
    assert repo.healer_swarm_enabled is True
    assert repo.healer_swarm_mode == "failure_repair"
    assert repo.healer_swarm_max_parallel_agents == 6
    assert repo.healer_swarm_max_repair_cycles_per_attempt == 2
    assert repo.healer_swarm_analysis_timeout_seconds == 150
    assert repo.healer_swarm_recovery_timeout_seconds == 330
    assert repo.healer_swarm_orphan_subagent_ttl_seconds == 1200
    assert repo.healer_swarm_backend_strategy == "match_selected_backend"
    assert repo.healer_swarm_trigger_failure_classes == ["tests_failed", "verifier_failed"]
