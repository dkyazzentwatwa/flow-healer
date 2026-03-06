from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import AppConfig
from .service import FlowHealerService
from .tui import run_tui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flow-healer", description="Standalone Flow Healer service")
    parser.add_argument("--config", default="~/.flow-healer/config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("start", "status", "pause", "resume", "scan", "doctor", "tui"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--repo")
        if name == "start":
            cmd.add_argument("--once", action="store_true")
        if name == "scan":
            cmd.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = AppConfig.load(Path(args.config).expanduser())
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
    if args.command == "tui":
        run_tui(config, selected_repo=args.repo)
        return


if __name__ == "__main__":
    main()
