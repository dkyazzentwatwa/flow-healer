from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("apple_flow.healer_workspace")


@dataclass(slots=True, frozen=True)
class WorkspaceInfo:
    issue_id: str
    branch: str
    path: Path


@dataclass(slots=True, frozen=True)
class SandboxEnv:
    """Per-run process isolation environment.

    Provides an isolated HOME and XDG_CACHE_HOME so that the provider
    subprocess cannot read or write the operator's real home directory.
    On Linux this also prevents credential leakage between runs.

    Usage::
        sandbox = workspace_manager.create_sandbox_env(issue_id=issue_id)
        try:
            # pass sandbox.to_env_dict() as env overrides to subprocesses
            ...
        finally:
            sandbox.cleanup()
    """

    issue_id: str
    temp_home: Path
    temp_xdg_cache: Path
    network_allowed: bool

    def to_env_dict(self) -> dict[str, str]:
        """Return a dict of env vars to overlay on subprocess environment."""
        return {
            "HOME": str(self.temp_home),
            "XDG_CACHE_HOME": str(self.temp_xdg_cache),
            "XDG_CONFIG_HOME": str(self.temp_home / ".config"),
            "XDG_DATA_HOME": str(self.temp_home / ".local" / "share"),
        }

    def cleanup(self) -> None:
        """Remove all temp directories created for this sandbox."""
        for path in (self.temp_home, self.temp_xdg_cache):
            try:
                if path.exists():
                    shutil.rmtree(path, ignore_errors=True)
            except Exception:
                pass


class HealerWorkspaceManager:
    """Manage deterministic per-issue git worktrees under a safe root."""

    def __init__(self, *, repo_path: Path):
        self.repo_path = Path(repo_path).resolve()
        self.worktrees_root = self.repo_path / ".apple-flow-healer" / "worktrees"

    def ensure_workspace(self, *, issue_id: str, title: str) -> WorkspaceInfo:
        slug = self._slugify(title)
        self.worktrees_root.mkdir(parents=True, exist_ok=True)
        path = self.worktrees_root / f"issue-{issue_id}-{slug}"
        branch = f"healer/issue-{issue_id}-{slug}"
        if path.exists():
            if self._is_git_worktree(path):
                return WorkspaceInfo(issue_id=issue_id, branch=branch, path=path)
            logger.warning("Stale or corrupt worktree at %s; removing and recreating.", path)
            self.remove_workspace(workspace_path=path)

        create_error = self._add_worktree(path=path, branch=branch)
        if create_error:
            raise RuntimeError(f"Failed to create worktree for issue {issue_id}: {create_error}")
        if not self._is_git_worktree(path):
            logger.warning(
                "Worktree add for issue %s returned without a valid workspace at %s; pruning and retrying.",
                issue_id,
                path,
            )
            self._run_git_worktree_prune()
            create_error = self._add_worktree(path=path, branch=branch)
            if create_error:
                raise RuntimeError(f"Failed to create worktree for issue {issue_id}: {create_error}")
            if not self._is_git_worktree(path):
                raise RuntimeError(
                    f"Git reported worktree creation for issue {issue_id}, but workspace {path} is missing or invalid."
                )
        return WorkspaceInfo(issue_id=issue_id, branch=branch, path=path)

    def prepare_workspace(self, *, workspace_path: Path, branch: str, base_branch: str = "main") -> None:
        ws = Path(workspace_path).expanduser().absolute()
        if not self._is_under_root(ws):
            raise ValueError(f"Refusing to prepare workspace outside healer root: {ws}")
        fetch = subprocess.run(
            ["git", "-C", str(self.repo_path), "fetch", "origin", base_branch],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        base_ref = f"origin/{base_branch}"
        if fetch.returncode != 0:
            logger.warning(
                "Failed to fetch %s for workspace preparation in %s: %s",
                base_branch,
                ws,
                (fetch.stderr or fetch.stdout).strip(),
            )
            base_ref = base_branch
        checkout = subprocess.run(
            ["git", "-C", str(ws), "checkout", "-B", branch, base_ref],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if checkout.returncode != 0:
            raise RuntimeError(f"Failed to reset workspace {ws}: {(checkout.stderr or checkout.stdout).strip()}")
        reset = subprocess.run(
            ["git", "-C", str(ws), "reset", "--hard", base_ref],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if reset.returncode != 0:
            raise RuntimeError(f"Failed to hard-reset workspace {ws}: {(reset.stderr or reset.stdout).strip()}")
        clean = subprocess.run(
            ["git", "-C", str(ws), "clean", "-fd"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if clean.returncode != 0:
            raise RuntimeError(f"Failed to clean workspace {ws}: {(clean.stderr or clean.stdout).strip()}")
        ignored_clean = subprocess.run(
            ["git", "-C", str(ws), "clean", "-fdX"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if ignored_clean.returncode != 0:
            raise RuntimeError(
                f"Failed to clean ignored artifacts in workspace {ws}: "
                f"{(ignored_clean.stderr or ignored_clean.stdout).strip()}"
            )

    def rebuild_workspace(
        self,
        *,
        issue_id: str,
        title: str,
        base_branch: str = "main",
        existing_path: Path | None = None,
    ) -> WorkspaceInfo:
        if existing_path is not None:
            existing = Path(existing_path).expanduser().absolute()
            if existing.exists():
                self.remove_workspace(workspace_path=existing)
        workspace = self.ensure_workspace(issue_id=issue_id, title=title)
        self.prepare_workspace(
            workspace_path=workspace.path,
            branch=workspace.branch,
            base_branch=base_branch,
        )
        return workspace

    def remove_workspace(self, *, workspace_path: Path) -> None:
        ws = Path(workspace_path).expanduser().absolute()
        if not self._is_under_root(ws):
            raise ValueError(f"Refusing to remove workspace outside healer root: {ws}")
        if not ws.exists():
            return
        proc = self._run_git_worktree_remove(ws)
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            # Guard against stale lock metadata in .git/worktrees/* that can block clean removal.
            if "locked" in stderr.lower():
                self._run_git_worktree_unlock(ws)
                self._run_git_worktree_prune()
                retry = self._run_git_worktree_remove(ws)
                if retry.returncode == 0:
                    return
                stderr = (retry.stderr or stderr).strip()
            logger.warning("git worktree remove failed for %s: %s", ws, stderr)
            self._run_git_worktree_prune()
            if ws.is_symlink():
                ws.unlink(missing_ok=True)
            elif ws.is_dir():
                shutil.rmtree(ws, ignore_errors=True)
            else:
                ws.unlink(missing_ok=True)

    def _run_git_worktree_remove(self, ws: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo_path), "worktree", "remove", "-f", str(ws)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _run_git_worktree_unlock(self, ws: Path) -> None:
        subprocess.run(
            ["git", "-C", str(self.repo_path), "worktree", "unlock", str(ws)],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def _run_git_worktree_prune(self) -> None:
        subprocess.run(
            ["git", "-C", str(self.repo_path), "worktree", "prune", "--expire", "now"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _add_worktree(self, *, path: Path, branch: str) -> str:
        cmd = [
            "git",
            "-C",
            str(self.repo_path),
            "worktree",
            "add",
            "-f",
            "-b",
            branch,
            str(path),
            "HEAD",
        ]
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=60)
        if proc.returncode == 0:
            return ""
        stderr = (proc.stderr or "").strip()
        retry = [
            "git",
            "-C",
            str(self.repo_path),
            "worktree",
            "add",
            "-f",
            str(path),
            branch,
        ]
        proc_retry = subprocess.run(retry, check=False, capture_output=True, text=True, timeout=60)
        if proc_retry.returncode == 0:
            return ""
        return stderr or (proc_retry.stderr or "").strip() or "unknown error"

    def _is_git_worktree(self, path: Path) -> bool:
        ws = Path(path).expanduser().absolute()
        if ws == self.repo_path or not ws.exists():
            return False
        check = subprocess.run(
            ["git", "-C", str(ws), "rev-parse", "--git-dir"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return check.returncode == 0

    def create_sandbox_env(
        self,
        *,
        issue_id: str,
        network_allowed: bool = True,
    ) -> SandboxEnv:
        """Create per-run isolated HOME and XDG_CACHE directories.

        The caller is responsible for calling ``sandbox.cleanup()`` when the
        attempt finishes (or errors).  The sandbox is intentionally not tied to
        the worktree lifecycle so that the planner and runner phases can share
        the same sandbox across the full attempt.
        """
        slug = re.sub(r"[^a-z0-9]", "-", str(issue_id or "unknown").lower())[:20]
        prefix = f"fh-home-{slug}-"
        temp_home = Path(
            tempfile.mkdtemp(prefix=prefix, dir=os.getenv("TMPDIR") or None)
        ).resolve()
        temp_xdg_cache = Path(
            tempfile.mkdtemp(prefix=f"fh-cache-{slug}-", dir=os.getenv("TMPDIR") or None)
        ).resolve()
        # Pre-create common subdirs to avoid provider startup failures
        for subdir in (".config", ".local/share", ".ssh"):
            (temp_home / subdir).mkdir(parents=True, exist_ok=True)
        return SandboxEnv(
            issue_id=str(issue_id),
            temp_home=temp_home,
            temp_xdg_cache=temp_xdg_cache,
            network_allowed=network_allowed,
        )

    def list_workspaces(self) -> list[Path]:
        if not self.worktrees_root.exists():
            return []
        return sorted([p for p in self.worktrees_root.iterdir() if p.is_dir()])

    def is_safe_workspace_path(self, path: Path) -> bool:
        return self._is_under_root(Path(path).expanduser().absolute())

    def is_valid_workspace(self, path: Path) -> bool:
        return self._is_git_worktree(Path(path).expanduser().absolute())

    def _is_under_root(self, path: Path) -> bool:
        try:
            path.relative_to(self.worktrees_root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _slugify(title: str, max_len: int = 40) -> str:
        if not title.strip():
            return "untitled"
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", title).strip("-").lower()
        if not slug:
            slug = "untitled"
        return slug[:max_len]
