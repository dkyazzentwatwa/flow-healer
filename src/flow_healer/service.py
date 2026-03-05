from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .codex_cli_connector import CodexCliConnector
from .config import AppConfig, RelaySettings
from .healer_loop import AutonomousHealerLoop
from .healer_scan import FlowHealerScanner
from .healer_tracker import GitHubHealerTracker
from .store import SQLiteStore


@dataclass(slots=True)
class RepoRuntime:
    settings: RelaySettings
    store: SQLiteStore
    loop: AutonomousHealerLoop
    tracker: GitHubHealerTracker


class FlowHealerService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def build_runtime(self, repo: RelaySettings) -> RepoRuntime:
        store = SQLiteStore(self.config.repo_db_path(repo.repo_name))
        store.bootstrap()
        connector = CodexCliConnector(
            workspace=repo.healer_repo_path,
            codex_command=self.config.service.connector_command,
            timeout=self.config.service.connector_timeout_seconds,
            model=self.config.service.connector_model,
        )
        loop = AutonomousHealerLoop(settings=repo, store=store, connector=connector)
        if repo.healer_repo_slug and not loop.tracker.repo_slug:
            loop.tracker.repo_slug = repo.healer_repo_slug
        return RepoRuntime(settings=repo, store=store, loop=loop, tracker=loop.tracker)

    def start(self, repo_name: str | None = None, *, once: bool = False) -> None:
        repos = self.config.select_repos(repo_name)
        if once:
            for repo in repos:
                runtime = self.build_runtime(repo)
                runtime.loop._tick_once()
                runtime.store.close()
            return

        async def _run() -> None:
            runtimes = [self.build_runtime(repo) for repo in repos]
            stop = False
            try:
                await asyncio.gather(*(runtime.loop.run_forever(lambda: stop) for runtime in runtimes))
            finally:
                stop = True
                for runtime in runtimes:
                    runtime.store.close()

        asyncio.run(_run())

    def status_rows(self, repo_name: str | None = None) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for repo in self.config.select_repos(repo_name):
            runtime = self.build_runtime(repo)
            issues = runtime.store.list_healer_issues(limit=500)
            counts: dict[str, int] = {}
            for issue in issues:
                state = str(issue.get("state") or "unknown")
                counts[state] = counts.get(state, 0) + 1
            rows.append(
                {
                    "repo": repo.repo_name,
                    "path": repo.healer_repo_path,
                    "paused": runtime.store.get_state("healer_paused") == "true",
                    "issues_total": len(issues),
                    "state_counts": counts,
                    "recent_attempts": runtime.store.list_recent_healer_attempts(limit=5),
                }
            )
            runtime.store.close()
        return rows

    def set_paused(self, paused: bool, repo_name: str | None = None) -> None:
        for repo in self.config.select_repos(repo_name):
            runtime = self.build_runtime(repo)
            runtime.store.set_state("healer_paused", "true" if paused else "false")
            runtime.store.close()

    def run_scan(self, repo_name: str | None = None, *, dry_run: bool) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for repo in self.config.select_repos(repo_name):
            runtime = self.build_runtime(repo)
            scanner = FlowHealerScanner(
                repo_path=Path(repo.healer_repo_path),
                store=runtime.store,
                tracker=runtime.tracker,
                severity_threshold=repo.healer_scan_severity_threshold,
                max_issues_per_run=repo.healer_scan_max_issues_per_run,
                default_labels=repo.healer_scan_default_labels,
                enable_issue_creation=repo.healer_scan_enable_issue_creation,
            )
            results.append({"repo": repo.repo_name, "summary": scanner.run_scan(dry_run=dry_run)})
            runtime.store.close()
        return results

    def doctor_rows(self, repo_name: str | None = None) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        token_name = self.config.service.github_token_env
        token_present = bool(os.getenv(token_name, "").strip())
        docker_present = shutil.which("docker") is not None
        codex_present = shutil.which(self.config.service.connector_command) is not None
        for repo in self.config.select_repos(repo_name):
            repo_path = Path(repo.healer_repo_path).expanduser().resolve()
            git_ok = _check_command(["git", "-C", str(repo_path), "rev-parse", "--is-inside-work-tree"])
            branch_ok = _check_command(["git", "-C", str(repo_path), "rev-parse", "--verify", repo.healer_default_branch])
            rows.append(
                {
                    "repo": repo.repo_name,
                    "repo_path": str(repo_path),
                    "path_exists": repo_path.exists(),
                    "git_repo": git_ok,
                    "default_branch_ok": branch_ok,
                    "docker": docker_present,
                    "codex": codex_present,
                    "github_token_env": token_name,
                    "github_token_present": token_present,
                }
            )
        return rows


def _check_command(cmd: list[str]) -> bool:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=15)
    return proc.returncode == 0
