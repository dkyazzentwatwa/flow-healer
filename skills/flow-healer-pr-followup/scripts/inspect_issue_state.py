#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Flow Healer issue/attempt state for PR follow-up")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--issue-id", required=True)
    args = parser.parse_args()

    conn = sqlite3.connect(str(Path(args.db_path).expanduser().resolve()))
    conn.row_factory = sqlite3.Row
    try:
        issue = _row_to_dict(
            conn.execute("select * from healer_issues where issue_id = ?", (args.issue_id,)).fetchone()
        )
        attempts = [
            _row_to_dict(row)
            for row in conn.execute(
                """
                select attempt_no, state, failure_class, failure_reason, started_at, finished_at
                from healer_attempts
                where issue_id = ?
                order by attempt_no desc
                """,
                (args.issue_id,),
            ).fetchall()
        ]
    finally:
        conn.close()

    report = {
        "issue": issue,
        "attempts": attempts,
    }
    print(json.dumps(report, indent=2, default=str))
    return 0 if issue is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
