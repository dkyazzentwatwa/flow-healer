#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flow_healer.config import AppConfig
from flow_healer.mastery_determinism import FIXED_MASTERY_ISSUE_PACK, snapshot_fixed_issue_pack
from flow_healer.store import SQLiteStore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export fixed mastery issue-pack snapshot for drift checks.")
    parser.add_argument(
        "--config",
        default="~/.flow-healer/config.yaml",
        help="Path to Flow Healer config.",
    )
    parser.add_argument(
        "--repo",
        default="flow-healer-self",
        help="Repo name from Flow Healer config.",
    )
    parser.add_argument(
        "--issue-ids",
        default=",".join(FIXED_MASTERY_ISSUE_PACK),
        help="Comma-separated issue IDs for the fixed pack.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for snapshot JSON output.",
    )
    return parser


def _parse_issue_ids(raw: str) -> tuple[str, ...]:
    parsed = tuple(token.strip() for token in str(raw or "").split(",") if token.strip())
    return parsed or FIXED_MASTERY_ISSUE_PACK


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    config = AppConfig.load(Path(str(args.config)).expanduser())
    db_path = config.repo_db_path(str(args.repo))
    store = SQLiteStore(db_path)
    store.bootstrap()
    snapshot = snapshot_fixed_issue_pack(
        store=store,
        issue_ids=_parse_issue_ids(str(args.issue_ids)),
    )
    output_path = Path(str(args.output)).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    print(f"Snapshot written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
