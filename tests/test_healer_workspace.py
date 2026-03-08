from __future__ import annotations

import subprocess
from pathlib import Path

from flow_healer.healer_workspace import HealerWorkspaceManager


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
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True, text=True, timeout=60)
    _git(repo, "config", "user.name", "Flow Healer Tests")
    _git(repo, "config", "user.email", "tests@example.com")
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")


def test_ensure_workspace_reuses_valid_git_worktree(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    manager = HealerWorkspaceManager(repo_path=repo)

    first = manager.ensure_workspace(issue_id="901", title="Fix parser")
    second = manager.ensure_workspace(issue_id="901", title="Fix parser")

    assert second.path == first.path
    assert second.branch == first.branch
    check = subprocess.run(
        ["git", "-C", str(second.path), "rev-parse", "--git-dir"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert check.returncode == 0


def test_ensure_workspace_recreates_corrupt_worktree(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    manager = HealerWorkspaceManager(repo_path=repo)

    first = manager.ensure_workspace(issue_id="902", title="Fix parser")
    git_pointer = first.path / ".git"
    git_pointer.write_text("broken-worktree\n", encoding="utf-8")

    recreated = manager.ensure_workspace(issue_id="902", title="Fix parser")

    assert recreated.path == first.path
    check = subprocess.run(
        ["git", "-C", str(recreated.path), "rev-parse", "--git-dir"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert check.returncode == 0
