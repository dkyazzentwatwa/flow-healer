from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class ServiceSettings:
    github_token_env: str = "GITHUB_TOKEN"
    poll_interval_seconds: float = 60.0
    state_root: str = "~/.flow-healer"
    connector_command: str = "codex"
    connector_model: str = ""
    connector_timeout_seconds: int = 300


@dataclass(slots=True)
class RelaySettings:
    repo_name: str
    healer_repo_path: str
    healer_repo_slug: str = ""
    healer_default_branch: str = "main"
    enable_autonomous_healer: bool = True
    healer_mode: str = "guarded_pr"
    healer_poll_interval_seconds: float = 60.0
    healer_max_concurrent_issues: int = 1
    healer_max_wall_clock_seconds_per_issue: int = 300
    healer_issue_required_labels: list[str] = field(default_factory=lambda: ["healer:ready"])
    healer_pr_actions_require_approval: bool = True
    healer_pr_required_label: str = "healer:pr-approved"
    healer_trusted_actors: list[str] = field(default_factory=list)
    healer_retry_budget: int = 2
    healer_backoff_initial_seconds: int = 60
    healer_backoff_max_seconds: int = 3600
    healer_circuit_breaker_window: int = 5
    healer_circuit_breaker_failure_rate: float = 0.5
    healer_learning_enabled: bool = True
    healer_max_diff_files: int = 8
    healer_max_diff_lines: int = 400
    healer_max_failed_tests_allowed: int = 0
    healer_scan_enable_issue_creation: bool = False
    healer_scan_severity_threshold: str = "medium"
    healer_scan_max_issues_per_run: int = 5
    healer_scan_default_labels: list[str] = field(default_factory=lambda: ["kind:scan"])


@dataclass(slots=True)
class AppConfig:
    service: ServiceSettings
    repos: list[RelaySettings]

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        config_path = Path(path or os.path.expanduser("~/.flow-healer/config.yaml")).expanduser()
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        raw = raw if isinstance(raw, dict) else {}

        service_raw = raw.get("service") if isinstance(raw.get("service"), dict) else {}
        service = ServiceSettings(
            github_token_env=str(service_raw.get("github_token_env") or "GITHUB_TOKEN"),
            poll_interval_seconds=float(service_raw.get("poll_interval_seconds") or 60.0),
            state_root=str(service_raw.get("state_root") or "~/.flow-healer"),
            connector_command=str(service_raw.get("connector_command") or "codex"),
            connector_model=str(service_raw.get("connector_model") or ""),
            connector_timeout_seconds=int(service_raw.get("connector_timeout_seconds") or 300),
        )

        repos: list[RelaySettings] = []
        for index, item in enumerate(raw.get("repos") or []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or f"repo-{index+1}").strip()
            path_value = str(item.get("path") or "").strip()
            if not name or not path_value:
                continue
            repos.append(
                RelaySettings(
                    repo_name=name,
                    healer_repo_path=path_value,
                    healer_repo_slug=str(item.get("repo_slug") or ""),
                    healer_default_branch=str(item.get("default_branch") or "main"),
                    enable_autonomous_healer=bool(item.get("enable_autonomous_healer", True)),
                    healer_mode=str(item.get("healer_mode") or "guarded_pr"),
                    healer_poll_interval_seconds=float(
                        item.get("poll_interval_seconds") or service.poll_interval_seconds
                    ),
                    healer_max_concurrent_issues=int(item.get("max_concurrent_issues") or 1),
                    healer_max_wall_clock_seconds_per_issue=int(
                        item.get("max_wall_clock_seconds_per_issue") or service.connector_timeout_seconds
                    ),
                    healer_issue_required_labels=_list_of_str(item.get("issue_required_labels"), ["healer:ready"]),
                    healer_pr_actions_require_approval=bool(item.get("pr_actions_require_approval", True)),
                    healer_pr_required_label=str(item.get("pr_required_label") or "healer:pr-approved"),
                    healer_trusted_actors=_list_of_str(item.get("trusted_actors"), []),
                    healer_retry_budget=int(item.get("retry_budget") or 2),
                    healer_backoff_initial_seconds=int(item.get("backoff_initial_seconds") or 60),
                    healer_backoff_max_seconds=int(item.get("backoff_max_seconds") or 3600),
                    healer_circuit_breaker_window=int(item.get("circuit_breaker_window") or 5),
                    healer_circuit_breaker_failure_rate=float(item.get("circuit_breaker_failure_rate") or 0.5),
                    healer_learning_enabled=bool(item.get("learning_enabled", True)),
                    healer_max_diff_files=int(item.get("max_diff_files") or 8),
                    healer_max_diff_lines=int(item.get("max_diff_lines") or 400),
                    healer_max_failed_tests_allowed=int(item.get("max_failed_tests_allowed") or 0),
                    healer_scan_enable_issue_creation=bool(item.get("scan_enable_issue_creation", False)),
                    healer_scan_severity_threshold=str(item.get("scan_severity_threshold") or "medium"),
                    healer_scan_max_issues_per_run=int(item.get("scan_max_issues_per_run") or 5),
                    healer_scan_default_labels=_list_of_str(item.get("scan_default_labels"), ["kind:scan"]),
                )
            )
        return cls(service=service, repos=repos)

    def state_root_path(self) -> Path:
        return Path(self.service.state_root).expanduser().resolve()

    def repo_db_path(self, repo_name: str) -> Path:
        return self.state_root_path() / "repos" / repo_name / "state.db"

    def select_repos(self, repo_name: str | None = None) -> list[RelaySettings]:
        if not repo_name:
            return list(self.repos)
        wanted = repo_name.strip()
        return [repo for repo in self.repos if repo.repo_name == wanted]


def _list_of_str(value: Any, default: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(default)
    return [str(item).strip() for item in value if str(item).strip()]
