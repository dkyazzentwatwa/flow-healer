from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import AppConfig
from .serve_runtime import run_serve
from .service import FlowHealerService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flow-healer", description="Standalone Flow Healer service")
    parser.add_argument("--config", default="~/.flow-healer/config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("start", "status", "pause", "resume", "scan", "doctor", "serve"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--repo")
        if name == "start":
            cmd.add_argument("--once", action="store_true")
        if name == "scan":
            cmd.add_argument("--dry-run", action="store_true")
        if name == "serve":
            cmd.add_argument("--host")
            cmd.add_argument("--port", type=int)
    return parser


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
        service.start(args.repo, once=bool(args.once))
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
        for row in service.doctor_rows(args.repo):
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


if __name__ == "__main__":
    main()
