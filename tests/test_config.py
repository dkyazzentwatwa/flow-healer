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
    assert config.service.connector_model == "gpt-5.4"
    assert config.service.connector_reasoning_effort == "medium"
    assert config.control.web.enabled is True
    assert config.control.web.auth_mode == "none"
    assert config.control.mail.subject_prefix == "FH:"
    assert config.select_repos("demo")[0].repo_name == "demo"
    assert config_path.parent.joinpath(".env").exists()
    assert os.environ["GITHUB_TOKEN"] == "test-token"
