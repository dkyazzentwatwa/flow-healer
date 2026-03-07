from __future__ import annotations

from dataclasses import dataclass
import shlex
from typing import Any, Callable

from .config import AppConfig, RelaySettings
from .service import FlowHealerService
from .store import SQLiteStore


@dataclass(slots=True)
class ParsedCommand:
    raw: str
    command: str
    repo: str
    args: dict[str, str]


class CommandParseError(ValueError):
    pass


def parse_command_subject(raw: str, *, prefix: str = "FH:") -> ParsedCommand | None:
    text = (raw or "").strip()
    if not text:
        return None

    parsed_prefix = (prefix or "").strip()
    if parsed_prefix:
        if not text.lower().startswith(parsed_prefix.lower()):
            return None
        body = text[len(parsed_prefix) :].strip()
    else:
        body = text

    if not body:
        raise CommandParseError("Missing command after prefix.")

    try:
        tokens = shlex.split(body)
    except ValueError as exc:
        raise CommandParseError(f"Failed to parse command: {exc}") from exc

    if not tokens:
        raise CommandParseError("Missing command token.")

    command = tokens[0].strip().lower()
    if not command:
        raise CommandParseError("Missing command token.")

    args: dict[str, str] = {}
    for token in tokens[1:]:
        item = token.strip()
        if not item:
            continue
        if "=" in item:
            key, value = item.split("=", 1)
            key = key.strip().lower()
            if key:
                args[key] = value.strip()
            continue
        args[item.lower()] = "true"

    repo = (args.pop("repo", "") or "").strip()
    return ParsedCommand(raw=text, command=command, repo=repo, args=args)


class ControlRouter:
    def __init__(
        self,
        *,
        config: AppConfig,
        service: FlowHealerService,
        shutdown_hook: Callable[[], None] | None = None,
    ) -> None:
        self.config = config
        self.service = service
        self.shutdown_hook = shutdown_hook

    def execute(
        self,
        *,
        request: ParsedCommand,
        source: str,
        external_id: str,
        sender: str = "",
    ) -> dict[str, Any]:
        source_value = (source or "unknown").strip().lower()[:40] or "unknown"
        external_value = (external_id or "").strip()[:200]
        if not external_value:
            raise ValueError("external_id is required for command dedupe.")

        target_repos = self._target_repos(request)
        if not target_repos:
            raise ValueError("No repositories configured for this command.")

        command_ids: list[tuple[str, str]] = []
        for repo in target_repos:
            with self._repo_store(repo) as store:
                if store.has_control_command(source=source_value, external_id=external_value):
                    return {
                        "ok": True,
                        "duplicate": True,
                        "command": request.command,
                        "repo": repo.repo_name,
                        "message": "Duplicate command ignored.",
                    }
                command_id = store.create_control_command(
                    source=source_value,
                    external_id=external_value,
                    sender=sender,
                    repo_name=repo.repo_name,
                    raw_command=request.raw,
                    parsed_command=request.command,
                    args=request.args,
                    status="received",
                )
                command_ids.append((repo.repo_name, command_id))

        try:
            result = self._dispatch(request)
        except Exception as exc:
            for repo_name, command_id in command_ids:
                with self._repo_store_by_name(repo_name) as store:
                    store.update_control_command(
                        command_id=command_id,
                        status="failed",
                        result={},
                        error_text=str(exc),
                    )
            return {
                "ok": False,
                "duplicate": False,
                "command": request.command,
                "message": str(exc),
            }

        for repo_name, command_id in command_ids:
            with self._repo_store_by_name(repo_name) as store:
                store.update_control_command(
                    command_id=command_id,
                    status="succeeded",
                    result=result,
                )

        return {
            "ok": True,
            "duplicate": False,
            "command": request.command,
            "result": result,
        }

    def _dispatch(self, request: ParsedCommand) -> dict[str, Any]:
        command = request.command
        repo_name = request.repo or None

        if command == "status":
            return {"rows": self.service.status_rows(repo_name)}

        if command == "doctor":
            return {"rows": self.service.doctor_rows(repo_name)}

        if command == "pause":
            self.service.set_paused(True, repo_name)
            return {"message": "Paused."}

        if command == "resume":
            self.service.set_paused(False, repo_name)
            return {"message": "Resumed."}

        if command in {"once", "start"}:
            self.service.start(repo_name, once=True)
            return {"message": "Completed one cycle."}

        if command in {"scan", "scan-dry"}:
            dry_run = _as_bool(request.args.get("dry_run", "false"))
            if command == "scan-dry":
                dry_run = True
            return {"rows": self.service.run_scan(repo_name, dry_run=dry_run)}

        if command == "shutdown":
            if not self.config.control.commands.enable_full_control:
                raise ValueError("Shutdown command is disabled in config.")
            if self.shutdown_hook is None:
                raise ValueError("Shutdown hook is not configured.")
            self.shutdown_hook()
            return {"message": "Shutdown requested."}

        raise ValueError(f"Unsupported command '{command}'.")

    def _target_repos(self, request: ParsedCommand) -> list[RelaySettings]:
        if request.repo:
            repos = self.config.select_repos(request.repo)
            if not repos:
                raise ValueError(f"Unknown repo '{request.repo}'.")
            return repos
        return list(self.config.repos)

    def _repo_store(self, repo: RelaySettings) -> _StoreContext:
        return _StoreContext(self.config.repo_db_path(repo.repo_name))

    def _repo_store_by_name(self, repo_name: str) -> _StoreContext:
        return _StoreContext(self.config.repo_db_path(repo_name))


class _StoreContext:
    def __init__(self, db_path: Any) -> None:
        self._store = SQLiteStore(db_path)

    def __enter__(self) -> SQLiteStore:
        self._store.bootstrap()
        return self._store

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._store.close()


def _as_bool(value: str) -> bool:
    text = (value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "y"}
