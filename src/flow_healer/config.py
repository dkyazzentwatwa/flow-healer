from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .language_strategies import ensure_supported_language


@dataclass(slots=True)
class ServiceSettings:
    github_token_env: str = "GITHUB_TOKEN"
    env_file: str = ""
    github_api_base_url: str = "https://api.github.com"
    poll_interval_seconds: float = 30.0
    state_root: str = "~/.flow-healer"
    connector_backend: str = "app_server"
    connector_command: str = "codex"
    connector_model: str = "gpt-5.4"
    connector_reasoning_effort: str = "medium"
    connector_timeout_seconds: int = 300


@dataclass(slots=True)
class WebControlSettings:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8787
    auth_mode: str = "none"


@dataclass(slots=True)
class MailControlSettings:
    enabled: bool = False
    account: str = ""
    mailbox: str = "INBOX"
    trusted_senders: list[str] = field(default_factory=list)
    poll_interval_seconds: float = 30.0
    subject_prefix: str = "FH:"
    send_replies: bool = True


@dataclass(slots=True)
class CalendarControlSettings:
    enabled: bool = False
    calendar_name: str = "healer-cal"
    poll_interval_seconds: float = 30.0
    subject_prefix: str = "FH:"
    lookback_minutes: int = 5
    lookahead_minutes: int = 2


@dataclass(slots=True)
class CommandControlSettings:
    enable_full_control: bool = False


@dataclass(slots=True)
class ControlSettings:
    web: WebControlSettings = field(default_factory=WebControlSettings)
    mail: MailControlSettings = field(default_factory=MailControlSettings)
    calendar: CalendarControlSettings = field(default_factory=CalendarControlSettings)
    commands: CommandControlSettings = field(default_factory=CommandControlSettings)


@dataclass(slots=True)
class RelaySettings:
    repo_name: str
    healer_repo_path: str
    healer_repo_slug: str = ""
    healer_default_branch: str = "main"
    enable_autonomous_healer: bool = True
    healer_mode: str = "guarded_pr"
    healer_poll_interval_seconds: float = 30.0
    healer_max_concurrent_issues: int = 3
    healer_max_wall_clock_seconds_per_issue: int = 300
    healer_issue_required_labels: list[str] = field(default_factory=lambda: ["healer:ready"])
    healer_pr_actions_require_approval: bool = False
    healer_pr_required_label: str = "healer:pr-approved"
    healer_pr_auto_approve_clean: bool = True
    healer_pr_auto_merge_clean: bool = True
    healer_pr_merge_method: str = "squash"
    healer_trusted_actors: list[str] = field(default_factory=list)
    healer_retry_budget: int = 2
    healer_backoff_initial_seconds: int = 60
    healer_backoff_max_seconds: int = 3600
    healer_circuit_breaker_window: int = 5
    healer_circuit_breaker_failure_rate: float = 0.5
    healer_circuit_breaker_cooldown_seconds: int = 900
    healer_learning_enabled: bool = True
    healer_enable_review: bool = True
    healer_verifier_policy: str = "advisory"
    healer_test_gate_mode: str = "local_then_docker"
    healer_local_gate_policy: str = "auto"
    healer_completion_artifact_mode: str = "fallback_only"
    healer_language: str = ""
    healer_docker_image: str = ""
    healer_test_command: str = ""
    healer_install_command: str = ""
    healer_auto_clean_generated_artifacts: bool = True
    healer_failure_fingerprint_quarantine_threshold: int = 2
    healer_max_diff_files: int = 8
    healer_max_diff_lines: int = 400
    healer_max_failed_tests_allowed: int = 0
    healer_scan_enable_issue_creation: bool = False
    healer_scan_poll_interval_seconds: float = 180.0
    healer_scan_severity_threshold: str = "medium"
    healer_scan_max_issues_per_run: int = 5
    healer_scan_default_labels: list[str] = field(default_factory=lambda: ["kind:scan"])
    healer_stuck_pr_timeout_minutes: int = 60
    healer_conflict_auto_requeue_enabled: bool = True
    healer_conflict_auto_requeue_max_attempts: int = 3
    healer_overlap_scope_queue_enabled: bool = True
    healer_dedupe_enabled: bool = True
    healer_dedupe_close_duplicates: bool = True
    healer_github_mutation_min_interval_ms: int = 1000
    healer_github_max_parallel_mutations: int = 1
    healer_retry_respect_retry_after: bool = True
    healer_retry_jitter_mode: str = "full_jitter"
    healer_retry_max_backoff_seconds: int = 300
    healer_poll_use_conditional_requests: bool = True
    healer_poll_etag_ttl_seconds: int = 300
    healer_infra_dlq_threshold: int = 8
    healer_infra_dlq_cooldown_seconds: int = 3600
    healer_sqlite_busy_timeout_ms: int = 5000
    healer_subprocess_kill_grace_seconds: int = 5
    healer_mergeability_recheck_delay_seconds: int = 2


@dataclass(slots=True)
class AppConfig:
    service: ServiceSettings
    repos: list[RelaySettings]
    control: ControlSettings = field(default_factory=ControlSettings)

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        config_path = Path(path or os.path.expanduser("~/.flow-healer/config.yaml")).expanduser()
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        raw = raw if isinstance(raw, dict) else {}

        service_raw = raw.get("service") if isinstance(raw.get("service"), dict) else {}
        env_file = _resolve_env_file(config_path, service_raw.get("env_file"))
        _load_env_file(env_file)
        service = ServiceSettings(
            github_token_env=str(service_raw.get("github_token_env") or "GITHUB_TOKEN"),
            env_file=str(env_file) if env_file else "",
            github_api_base_url=str(service_raw.get("github_api_base_url") or "https://api.github.com"),
            poll_interval_seconds=float(service_raw.get("poll_interval_seconds") or 30.0),
            state_root=str(service_raw.get("state_root") or "~/.flow-healer"),
            connector_backend=_normalize_connector_backend(service_raw.get("connector_backend")),
            connector_command=str(service_raw.get("connector_command") or "codex"),
            connector_model=str(service_raw.get("connector_model") or "gpt-5.4"),
            connector_reasoning_effort=str(service_raw.get("connector_reasoning_effort") or "medium"),
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
                    healer_max_concurrent_issues=int(item.get("max_concurrent_issues") or 3),
                    healer_max_wall_clock_seconds_per_issue=int(
                        item.get("max_wall_clock_seconds_per_issue") or service.connector_timeout_seconds
                    ),
                    healer_issue_required_labels=_list_of_str(item.get("issue_required_labels"), ["healer:ready"]),
                    healer_pr_actions_require_approval=bool(item.get("pr_actions_require_approval", False)),
                    healer_pr_required_label=str(item.get("pr_required_label") or "healer:pr-approved"),
                    healer_pr_auto_approve_clean=bool(item.get("pr_auto_approve_clean", True)),
                    healer_pr_auto_merge_clean=bool(item.get("pr_auto_merge_clean", True)),
                    healer_pr_merge_method=str(item.get("pr_merge_method") or "squash"),
                    healer_trusted_actors=_list_of_str(item.get("trusted_actors"), []),
                    healer_retry_budget=int(item.get("retry_budget") or 2),
                    healer_backoff_initial_seconds=int(item.get("backoff_initial_seconds") or 60),
                    healer_backoff_max_seconds=int(item.get("backoff_max_seconds") or 3600),
                    healer_circuit_breaker_window=int(item.get("circuit_breaker_window") or 5),
                    healer_circuit_breaker_failure_rate=float(item.get("circuit_breaker_failure_rate") or 0.5),
                    healer_circuit_breaker_cooldown_seconds=int(
                        item.get("circuit_breaker_cooldown_seconds") or 900
                    ),
                    healer_learning_enabled=bool(item.get("learning_enabled", True)),
                    healer_enable_review=bool(item.get("enable_review", True)),
                    healer_verifier_policy=_normalize_verifier_policy(item.get("verifier_policy")),
                    healer_test_gate_mode=str(item.get("test_gate_mode") or "local_then_docker"),
                    healer_local_gate_policy=str(item.get("local_gate_policy") or "auto"),
                    healer_completion_artifact_mode=str(item.get("completion_artifact_mode") or "fallback_only"),
                    healer_language=_validate_healer_language(
                        item.get("language"),
                        repo_name=name,
                    ),
                    healer_docker_image=str(item.get("docker_image") or ""),
                    healer_test_command=str(item.get("test_command") or ""),
                    healer_install_command=str(item.get("install_command") or ""),
                    healer_auto_clean_generated_artifacts=bool(item.get("auto_clean_generated_artifacts", True)),
                    healer_failure_fingerprint_quarantine_threshold=int(
                        item.get("failure_fingerprint_quarantine_threshold") or 2
                    ),
                    healer_max_diff_files=int(item.get("max_diff_files") or 8),
                    healer_max_diff_lines=int(item.get("max_diff_lines") or 400),
                    healer_max_failed_tests_allowed=int(item.get("max_failed_tests_allowed") or 0),
                    healer_scan_enable_issue_creation=bool(item.get("scan_enable_issue_creation", False)),
                    healer_scan_poll_interval_seconds=float(
                        item.get("scan_poll_interval_seconds") or 180.0
                    ),
                    healer_scan_severity_threshold=str(item.get("scan_severity_threshold") or "medium"),
                    healer_scan_max_issues_per_run=int(item.get("scan_max_issues_per_run") or 5),
                    healer_scan_default_labels=_list_of_str(item.get("scan_default_labels"), ["kind:scan"]),
                    healer_stuck_pr_timeout_minutes=int(item.get("stuck_pr_timeout_minutes") or 60),
                    healer_conflict_auto_requeue_enabled=bool(item.get("conflict_auto_requeue_enabled", True)),
                    healer_conflict_auto_requeue_max_attempts=int(item.get("conflict_auto_requeue_max_attempts") or 3),
                    healer_overlap_scope_queue_enabled=bool(item.get("overlap_scope_queue_enabled", True)),
                    healer_dedupe_enabled=bool(item.get("dedupe_enabled", True)),
                    healer_dedupe_close_duplicates=bool(item.get("dedupe_close_duplicates", True)),
                    healer_github_mutation_min_interval_ms=int(item.get("github_mutation_min_interval_ms") or 1000),
                    healer_github_max_parallel_mutations=int(item.get("github_max_parallel_mutations") or 1),
                    healer_retry_respect_retry_after=bool(item.get("retry_respect_retry_after", True)),
                    healer_retry_jitter_mode=str(item.get("retry_jitter_mode") or "full_jitter"),
                    healer_retry_max_backoff_seconds=int(item.get("retry_max_backoff_seconds") or 300),
                    healer_poll_use_conditional_requests=bool(item.get("poll_use_conditional_requests", True)),
                    healer_poll_etag_ttl_seconds=int(item.get("poll_etag_ttl_seconds") or 300),
                    healer_infra_dlq_threshold=int(item.get("infra_dlq_threshold") or 8),
                    healer_infra_dlq_cooldown_seconds=int(item.get("infra_dlq_cooldown_seconds") or 3600),
                    healer_sqlite_busy_timeout_ms=int(item.get("sqlite_busy_timeout_ms") or 5000),
                    healer_subprocess_kill_grace_seconds=int(item.get("subprocess_kill_grace_seconds") or 5),
                    healer_mergeability_recheck_delay_seconds=int(item.get("mergeability_recheck_delay_seconds") or 2),
                )
            )
        control_raw = raw.get("control") if isinstance(raw.get("control"), dict) else {}
        web_raw = control_raw.get("web") if isinstance(control_raw.get("web"), dict) else {}
        mail_raw = control_raw.get("mail") if isinstance(control_raw.get("mail"), dict) else {}
        calendar_raw = control_raw.get("calendar") if isinstance(control_raw.get("calendar"), dict) else {}
        commands_raw = control_raw.get("commands") if isinstance(control_raw.get("commands"), dict) else {}

        control = ControlSettings(
            web=WebControlSettings(
                enabled=bool(web_raw.get("enabled", True)),
                host=str(web_raw.get("host") or "0.0.0.0"),
                port=int(web_raw.get("port") or 8787),
                auth_mode=str(web_raw.get("auth_mode") or "none"),
            ),
            mail=MailControlSettings(
                enabled=bool(mail_raw.get("enabled", False)),
                account=str(mail_raw.get("account") or ""),
                mailbox=str(mail_raw.get("mailbox") or "INBOX"),
                trusted_senders=_list_of_str(mail_raw.get("trusted_senders"), []),
                poll_interval_seconds=float(mail_raw.get("poll_interval_seconds") or 30.0),
                subject_prefix=str(mail_raw.get("subject_prefix") or "FH:"),
                send_replies=bool(mail_raw.get("send_replies", True)),
            ),
            calendar=CalendarControlSettings(
                enabled=bool(calendar_raw.get("enabled", False)),
                calendar_name=str(calendar_raw.get("calendar_name") or "healer-cal"),
                poll_interval_seconds=float(calendar_raw.get("poll_interval_seconds") or 30.0),
                subject_prefix=str(calendar_raw.get("subject_prefix") or "FH:"),
                lookback_minutes=int(calendar_raw.get("lookback_minutes") or 5),
                lookahead_minutes=int(calendar_raw.get("lookahead_minutes") or 2),
            ),
            commands=CommandControlSettings(
                enable_full_control=bool(commands_raw.get("enable_full_control", False)),
            ),
        )

        return cls(service=service, repos=repos, control=control)

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


def _normalize_connector_backend(value: Any) -> str:
    raw = str(value or "app_server").strip().lower().replace("-", "_")
    if raw in {"exec", "app_server"}:
        return raw
    if raw == "appserver":
        return "app_server"
    return "app_server"


def _normalize_verifier_policy(value: Any) -> str:
    raw = str(value or "advisory").strip().lower().replace("-", "_")
    if raw in {"advisory", "required"}:
        return raw
    return "advisory"


def _resolve_env_file(config_path: Path, value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate
    return (config_path.parent / candidate).resolve()


def _load_env_file(path: Path | None) -> None:
    if path is None or not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        name = key.strip()
        if not name:
            continue
        cleaned = value.strip().strip("\"'")
        os.environ.setdefault(name, cleaned)


def _validate_healer_language(value: Any, *, repo_name: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return ensure_supported_language(raw, source=f"repo '{repo_name}' config")
