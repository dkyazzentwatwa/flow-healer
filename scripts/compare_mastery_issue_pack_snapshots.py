#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flow_healer.mastery_determinism import compare_issue_pack_snapshots, render_issue_pack_comparison_markdown


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare fixed mastery issue-pack snapshots and emit drift report.")
    parser.add_argument("--previous", required=True, help="Previous snapshot JSON path.")
    parser.add_argument("--current", required=True, help="Current snapshot JSON path.")
    parser.add_argument(
        "--json-output",
        default="",
        help="Optional comparison JSON output path.",
    )
    parser.add_argument(
        "--markdown-output",
        default="",
        help="Optional markdown summary output path.",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit with status 1 when unexpected drift is detected.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    previous = json.loads(Path(str(args.previous)).expanduser().read_text(encoding="utf-8"))
    current = json.loads(Path(str(args.current)).expanduser().read_text(encoding="utf-8"))
    if not isinstance(previous, dict) or not isinstance(current, dict):
        raise SystemExit("Both snapshots must be JSON objects.")
    comparison = compare_issue_pack_snapshots(previous=previous, current=current)
    markdown = render_issue_pack_comparison_markdown(comparison)
    print(markdown)

    json_output = str(args.json_output or "").strip()
    if json_output:
        json_output_path = Path(json_output).expanduser().resolve()
        json_output_path.parent.mkdir(parents=True, exist_ok=True)
        json_output_path.write_text(json.dumps(comparison, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Comparison JSON written to {json_output_path}")

    markdown_output = str(args.markdown_output or "").strip()
    if markdown_output:
        markdown_output_path = Path(markdown_output).expanduser().resolve()
        markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_output_path.write_text(markdown, encoding="utf-8")
        print(f"Comparison markdown written to {markdown_output_path}")

    if bool(args.enforce) and bool(comparison.get("has_unexpected_drift")):
        print("Unexpected fixed-pack drift detected.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
