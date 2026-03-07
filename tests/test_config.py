from __future__ import annotations

import os
from pathlib import Path

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
    assert config.service.connector_backend == "exec"
    assert config.service.connector_model == "gpt-5.4"
    assert config.service.connector_reasoning_effort == "medium"
    assert config.control.web.enabled is True
    assert config.control.web.auth_mode == "none"
    assert config.control.mail.subject_prefix == "FH:"
    assert config.select_repos("demo")[0].repo_name == "demo"
    relay = config.select_repos("demo")[0]
    assert relay.healer_max_concurrent_issues == 3
    assert relay.healer_pr_actions_require_approval is False
    assert relay.healer_pr_auto_approve_clean is True
    assert relay.healer_pr_auto_merge_clean is True
    assert relay.healer_pr_merge_method == "squash"
    assert relay.healer_local_gate_policy == "auto"
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
