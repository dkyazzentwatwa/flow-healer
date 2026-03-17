from __future__ import annotations

import subprocess
from pathlib import Path

from flow_healer.healer_workspace import HealerWorkspaceManager, SandboxEnv


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return proc


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    _git(repo, "config", "user.name", "Flow Healer Tests")
    _git(repo, "config", "user.email", "tests@example.com")
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")


# ---------------------------------------------------------------------------
# SandboxEnv.to_env_dict
# ---------------------------------------------------------------------------


def test_sandbox_env_to_env_dict_contains_home():
    env = SandboxEnv(
        issue_id="42",
        temp_home=Path("/tmp/fh-home-42"),
        temp_xdg_cache=Path("/tmp/fh-cache-42"),
        network_allowed=True,
    )
    d = env.to_env_dict()
    assert d["HOME"] == "/tmp/fh-home-42"
    assert d["XDG_CACHE_HOME"] == "/tmp/fh-cache-42"
    assert "XDG_CONFIG_HOME" in d
    assert "XDG_DATA_HOME" in d


def test_sandbox_env_cleanup_removes_dirs(tmp_path):
    home = tmp_path / "home"
    cache = tmp_path / "cache"
    home.mkdir()
    cache.mkdir()
    (home / "config_file").write_text("data")

    env = SandboxEnv(
        issue_id="42",
        temp_home=home,
        temp_xdg_cache=cache,
        network_allowed=True,
    )
    env.cleanup()

    assert not home.exists()
    assert not cache.exists()


def test_sandbox_env_cleanup_is_idempotent(tmp_path):
    home = tmp_path / "home"
    cache = tmp_path / "cache"
    home.mkdir()
    cache.mkdir()

    env = SandboxEnv(
        issue_id="42",
        temp_home=home,
        temp_xdg_cache=cache,
        network_allowed=True,
    )
    env.cleanup()
    env.cleanup()  # Second call should not raise


# ---------------------------------------------------------------------------
# HealerWorkspaceManager.create_sandbox_env
# ---------------------------------------------------------------------------


def test_create_sandbox_env_creates_isolated_home(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    manager = HealerWorkspaceManager(repo_path=repo)

    sandbox = manager.create_sandbox_env(issue_id="99")

    try:
        assert sandbox.issue_id == "99"
        assert sandbox.temp_home.exists()
        assert sandbox.temp_xdg_cache.exists()
        # Ensure standard subdirs are pre-created
        assert (sandbox.temp_home / ".config").is_dir()
        assert (sandbox.temp_home / ".local" / "share").is_dir()
        # Env dict should point to these dirs
        env = sandbox.to_env_dict()
        assert env["HOME"] == str(sandbox.temp_home)
        assert env["XDG_CACHE_HOME"] == str(sandbox.temp_xdg_cache)
    finally:
        sandbox.cleanup()


def test_create_sandbox_env_uses_issue_id_in_path(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    manager = HealerWorkspaceManager(repo_path=repo)

    sandbox = manager.create_sandbox_env(issue_id="issue-123")

    try:
        # Slug derived from issue_id should appear somewhere in the path name
        assert "123" in sandbox.temp_home.name or "issue" in sandbox.temp_home.name
    finally:
        sandbox.cleanup()


def test_create_sandbox_env_each_run_gets_separate_dirs(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    manager = HealerWorkspaceManager(repo_path=repo)

    sandbox_a = manager.create_sandbox_env(issue_id="1")
    sandbox_b = manager.create_sandbox_env(issue_id="2")

    try:
        assert sandbox_a.temp_home != sandbox_b.temp_home
        assert sandbox_a.temp_xdg_cache != sandbox_b.temp_xdg_cache
    finally:
        sandbox_a.cleanup()
        sandbox_b.cleanup()


def test_create_sandbox_env_network_flag_preserved(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    manager = HealerWorkspaceManager(repo_path=repo)

    sandbox = manager.create_sandbox_env(issue_id="7", network_allowed=False)
    try:
        assert sandbox.network_allowed is False
    finally:
        sandbox.cleanup()
