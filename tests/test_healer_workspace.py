from __future__ import annotations

import subprocess
from types import SimpleNamespace
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


def test_prepare_workspace_resets_issue_branch_to_latest_base(tmp_path):
    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True, timeout=60)
    _init_repo(repo)
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")

    manager = HealerWorkspaceManager(repo_path=repo)
    workspace = manager.ensure_workspace(issue_id="903", title="Fix parser")

    _git(workspace.path, "checkout", "-B", workspace.branch)
    (workspace.path / "feature.txt").write_text("stale branch work\n", encoding="utf-8")
    _git(workspace.path, "add", "feature.txt")
    _git(workspace.path, "commit", "-m", "stale branch commit")

    (repo / "README.md").write_text("# Demo\n\nlatest main\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "advance main")
    _git(repo, "push", "origin", "main")

    manager.prepare_workspace(workspace_path=workspace.path, branch=workspace.branch, base_branch="main")

    head = _git(workspace.path, "rev-parse", "HEAD").stdout.strip()
    main_head = _git(repo, "rev-parse", "origin/main").stdout.strip()
    status = _git(workspace.path, "status", "--short").stdout.strip()

    assert head == main_head
    assert status == ""
    assert not (workspace.path / "feature.txt").exists()


def test_prepare_workspace_cleans_ignored_artifacts(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-m", "ignore node modules")

    manager = HealerWorkspaceManager(repo_path=repo)
    workspace = manager.ensure_workspace(issue_id="9031", title="Fix parser")

    stale_dir = workspace.path / "node_modules" / ".bin"
    stale_dir.mkdir(parents=True)
    (stale_dir / "vitest").write_text("broken\n", encoding="utf-8")

    manager.prepare_workspace(workspace_path=workspace.path, branch=workspace.branch, base_branch="main")

    assert not (workspace.path / "node_modules").exists()


def test_remove_workspace_unlocks_and_retries_when_locked(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    _init_repo(repo)
    manager = HealerWorkspaceManager(repo_path=repo)
    workspace = manager.ensure_workspace(issue_id="904", title="Locked worktree")

    calls: list[list[str]] = []

    def fake_run(cmd, check=False, capture_output=True, text=True, timeout=30):  # noqa: ANN001
        cmd_list = [str(part) for part in cmd]
        calls.append(cmd_list)
        if cmd_list[-3:] == ["worktree", "remove", str(workspace.path)]:
            return SimpleNamespace(returncode=1, stderr="fatal: cannot remove: is locked")
        if cmd_list[-4:] == ["worktree", "remove", "-f", str(workspace.path)]:
            # First remove fails, second succeeds after unlock+prune.
            remove_calls = [row for row in calls if row[-4:] == ["worktree", "remove", "-f", str(workspace.path)]]
            if len(remove_calls) == 1:
                return SimpleNamespace(returncode=1, stderr="fatal: cannot remove: is locked")
            return SimpleNamespace(returncode=0, stderr="")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    manager.remove_workspace(workspace_path=workspace.path)

    assert any(row[-3:] == ["worktree", "unlock", str(workspace.path)] for row in calls)
    assert any(row[-4:] == ["worktree", "prune", "--expire", "now"] for row in calls)
    remove_attempts = [row for row in calls if row[-4:] == ["worktree", "remove", "-f", str(workspace.path)]]
    assert len(remove_attempts) == 2
