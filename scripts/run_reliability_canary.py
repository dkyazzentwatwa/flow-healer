#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flow_healer.reliability_canary import DEFAULT_CANARY_GROUPS, run_canary_suite


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic Flow Healer reliability canary suite.")
    parser.add_argument(
        "--output",
        default="reliability-canary-report.json",
        help="Path for canary report JSON output.",
    )
    parser.add_argument(
        "--pytest-bin",
        default="pytest",
        help="Pytest executable to invoke.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=900,
        help="Timeout for each canary group.",
    )
    parser.add_argument(
        "--groups",
        default="",
        help="Comma-separated canary groups to run (docs,code,mixed). Defaults to all.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    selected = DEFAULT_CANARY_GROUPS
    if str(args.groups or "").strip():
        wanted = [token.strip() for token in str(args.groups).split(",") if token.strip()]
        selected = {name: selectors for name, selectors in DEFAULT_CANARY_GROUPS.items() if name in wanted}
        if not selected:
            parser.error("No matching canary groups selected.")
    report = run_canary_suite(
        groups=selected,
        pytest_bin=str(args.pytest_bin),
        timeout_seconds=max(30, int(args.timeout_seconds)),
    )
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report.get("summary") or {}, indent=2, sort_keys=True))
    print(f"Canary report written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
