#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
CREATE_SANDBOX_ISSUES = REPO_ROOT / "scripts" / "create_sandbox_issues.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the two-wave final mega sandbox issue campaign.")
    parser.add_argument("--ready-label", default="healer:ready")
    parser.add_argument("--sleep-seconds", type=int, default=180)
    parser.add_argument("--extra-label", action="append", dest="extra_labels", default=[])
    return parser.parse_args()


def _wave_command(*, family: str, prefix: str, ready_label: str, extra_labels: Sequence[str], dry_run: bool) -> list[str]:
    cmd = [
        sys.executable,
        str(CREATE_SANDBOX_ISSUES),
        "30",
        prefix,
        "--family",
        family,
        "--ready-label",
        ready_label,
    ]
    for label in extra_labels:
        cmd.extend(["--extra-label", label])
    if dry_run:
        cmd.append("--dry-run")
    return cmd


def run_campaign(
    *,
    ready_label: str = "healer:ready",
    sleep_seconds: int = 180,
    extra_labels: Sequence[str] = (),
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    base_labels = ["campaign:mega-final", *extra_labels]
    steps = (
        ("mega-final-wave-1", "Mega final sandbox wave 1", [*base_labels, "wave:1"], True),
        ("mega-final-wave-2", "Mega final sandbox wave 2", [*base_labels, "wave:2"], True),
        ("mega-final-wave-1", "Mega final sandbox wave 1", [*base_labels, "wave:1"], False),
        ("mega-final-wave-2", "Mega final sandbox wave 2", [*base_labels, "wave:2"], False),
    )

    for index, (family, prefix, labels, dry_run) in enumerate(steps):
        cmd = _wave_command(
            family=family,
            prefix=prefix,
            ready_label=ready_label,
            extra_labels=labels,
            dry_run=dry_run,
        )
        runner(cmd, cwd=str(REPO_ROOT), check=True, text=True)
        if index == 2:
            sleeper(max(0, sleep_seconds))


def main() -> int:
    args = parse_args()
    run_campaign(
        ready_label=args.ready_label,
        sleep_seconds=args.sleep_seconds,
        extra_labels=args.extra_labels,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
