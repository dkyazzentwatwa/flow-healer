#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flow_healer.healer_triage import classify_issue_route


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify a Flow Healer failure into a deterministic bucket")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--issue-id", required=True)
    args = parser.parse_args()

    conn = sqlite3.connect(str(Path(args.db_path).expanduser().resolve()))
    conn.row_factory = sqlite3.Row
    try:
        issue = _row_to_dict(
            conn.execute("select * from healer_issues where issue_id = ?", (args.issue_id,)).fetchone()
        )
        attempt = _row_to_dict(
            conn.execute(
                """
                select attempt_no, state, failure_class, failure_reason, started_at, finished_at
                from healer_attempts
                where issue_id = ?
                order by attempt_no desc
                limit 1
                """,
                (args.issue_id,),
            ).fetchone()
        )
    finally:
        conn.close()
    route = classify_issue_route(issue, attempt)

    report = {
        "issue": issue,
        "latest_attempt": attempt,
        "diagnosis": route.diagnosis,
        "recommended_skill": route.recommended_skill,
        "default_action": route.default_action,
        "graph_position": route.graph_position,
        "previous_skill": route.previous_skill,
        "next_skill": route.next_skill,
        "skill_relative_path": route.skill_relative_path,
        "default_command_preview": route.default_command_preview,
        "key_output_fields": list(route.key_output_fields),
        "stop_conditions": list(route.stop_conditions),
        "stop_recommended": route.stop_recommended,
        "stop_reason": route.stop_reason,
        "connector_debug_focus": route.connector_debug_focus,
        "connector_debug_checks": list(route.connector_debug_checks),
    }
    print(json.dumps(report, indent=2, default=str))
    return 0 if issue is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
