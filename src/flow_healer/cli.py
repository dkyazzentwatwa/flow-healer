from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import AppConfig
from .serve_runtime import run_serve
from .service import FlowHealerService
from .telemetry_exports import default_export_dir, write_telemetry_exports
from .tui import run_tui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flow-healer", description="Standalone Flow Healer service")
    parser.add_argument("--config", default="~/.flow-healer/config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("start", "status", "pause", "resume", "scan", "doctor", "serve", "recycle-helpers", "export", "tui"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--repo")
        if name == "start":
            cmd.add_argument("--once", action="store_true")
        if name == "scan":
            cmd.add_argument("--dry-run", action="store_true")
        if name == "doctor":
            cmd.add_argument("--preflight", action="store_true")
            cmd.add_argument(
                "--plain",
                action="store_true",
                default=True,
                help="Show human-readable output (default). Use --no-plain for JSON.",
            )
            cmd.add_argument("--no-plain", dest="plain", action="store_false")
        if name == "serve":
            cmd.add_argument("--host")
            cmd.add_argument("--port", type=int)
        if name == "recycle-helpers":
            cmd.add_argument("--idle-only", action="store_true")
        if name == "export":
            cmd.add_argument("--formats", default="csv,jsonl")
            cmd.add_argument("--output-dir")
        if name == "tui":
            cmd.add_argument("--once", action="store_true")
            cmd.add_argument("--refresh-seconds", type=int, default=5)
    return parser


def format_doctor_rows_plain(rows: list[dict]) -> str:
    """Format doctor_rows as human-readable plain text with remediation hints."""
    if not rows:
        return "(no repos configured)"

    lines: list[str] = []
    for row in rows:
        repo = str(row.get("repo") or row.get("repo_name") or "unknown")
        lines.append(f"\n=== {repo} ===")

        checks = [
            (
                "GITHUB_TOKEN present",
                row.get("token_present"),
                "Set the GITHUB_TOKEN env var: export GITHUB_TOKEN=ghp_...",
            ),
            (
                "Git repo accessible",
                row.get("git_ok"),
                "Check the 'path:' field in your config.yaml points to a valid git repo",
            ),
            (
                "Connector found",
                row.get("connector_found"),
                "Install the connector (default: npm install -g @openai/codex) or set connector_backend in config",
            ),
            (
                "State database accessible",
                row.get("db_ok"),
                "Check disk space and permissions under ~/.flow-healer",
            ),
        ]
        for label, ok, hint in checks:
            if ok:
                lines.append(f"  ✓  {label}")
            elif ok is False:
                lines.append(f"  ✗  {label}")
                lines.append(f"     → {hint}")
            # ok is None means the check didn't run — skip silently

        preflight = row.get("preflight_summary") or {}
        issues = preflight.get("issues") or []
        if preflight.get("ready"):
            lines.append("  ✓  Preflight checks passed")
        elif issues:
            lines.append("  ✗  Preflight issues detected:")
            for issue in issues[:5]:
                lines.append(f"     → {issue}")

    return "\n".join(lines)


def _configure_logging(config: AppConfig) -> None:
    log_root = config.state_root_path()
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / "flow-healer.log"
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(log_path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[stream_handler, file_handler], force=True)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = AppConfig.load(Path(args.config).expanduser())
    _configure_logging(config)
    service = FlowHealerService(config)

    if args.command == "start":
        if args.once:
            service.start(args.repo, once=True)
        else:
            run_serve(
                config=config,
                service=service,
                repo_name=args.repo,
                host=None,
                port=None,
            )
        return
    if args.command == "status":
        for row in service.status_rows(args.repo):
            print(json.dumps(row, indent=2, default=str))
        return
    if args.command == "pause":
        service.set_paused(True, args.repo)
        return
    if args.command == "resume":
        service.set_paused(False, args.repo)
        return
    if args.command == "scan":
        for row in service.run_scan(args.repo, dry_run=bool(args.dry_run)):
            print(json.dumps(row, indent=2, default=str))
        return
    if args.command == "doctor":
        rows = service.doctor_rows(args.repo, preflight=bool(args.preflight))
        if getattr(args, "plain", True):
            print(format_doctor_rows_plain(rows))
        else:
            for row in rows:
                print(json.dumps(row, indent=2, default=str))
        return
    if args.command == "serve":
        run_serve(
            config=config,
            service=service,
            repo_name=args.repo,
            host=args.host,
            port=args.port,
        )
        return
    if args.command == "recycle-helpers":
        for row in service.request_helper_recycle(args.repo, idle_only=bool(args.idle_only)):
            print(json.dumps(row, indent=2, default=str))
        return
    if args.command == "export":
        output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else default_export_dir(config)
        written = write_telemetry_exports(
            service=service,
            repo_name=args.repo,
            output_dir=output_dir,
            formats=tuple(str(args.formats or "").split(",")),
        )
        print(
            json.dumps(
                {
                    "output_dir": str(output_dir),
                    "files": [str(path) for path in written],
                },
                indent=2,
            )
        )
        return
    if args.command == "tui":
        run_tui(
            config=config,
            service=service,
            repo_name=args.repo,
            refresh_seconds=int(args.refresh_seconds),
            once=bool(args.once),
        )
        return


if __name__ == "__main__":
    main()
