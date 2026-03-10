#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from flow_healer.reliability_canary import evaluate_canary_report, load_policy, render_markdown_summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate Flow Healer reliability canary report against gate policy.")
    parser.add_argument("--report", required=True, help="Path to reliability canary report JSON.")
    parser.add_argument("--policy", required=True, help="Path to reliability canary policy JSON.")
    parser.add_argument(
        "--mode",
        choices=("report", "enforce"),
        default="report",
        help="report=never fail process, enforce=exit non-zero on gate failures.",
    )
    parser.add_argument(
        "--summary-output",
        default="",
        help="Optional path for markdown summary output.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise SystemExit("Canary report must be a JSON object.")
    policy = load_policy(args.policy)
    evaluation = evaluate_canary_report(report=report, policy=policy)
    markdown = render_markdown_summary(report=report, evaluation=evaluation)
    print(markdown)
    summary_output = str(args.summary_output or "").strip()
    if summary_output:
        Path(summary_output).write_text(markdown, encoding="utf-8")
    github_step_summary = str(os.getenv("GITHUB_STEP_SUMMARY") or "").strip()
    if github_step_summary:
        with Path(github_step_summary).open("a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")
    if str(args.mode) == "enforce" and not evaluation.passed:
        print("Reliability canary gate failed in enforce mode.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
