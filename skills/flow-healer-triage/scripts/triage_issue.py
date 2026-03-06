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


def _classify(issue: dict[str, Any] | None, attempt: dict[str, Any] | None) -> str:
    failure_class = str((attempt or {}).get("failure_class") or (issue or {}).get("last_failure_class") or "")
    failure_reason = str((attempt or {}).get("failure_reason") or (issue or {}).get("last_failure_reason") or "").lower()
    state = str((issue or {}).get("state") or "")

    if failure_class in {"patch_apply_failed", "no_patch"}:
        return "connector_or_patch_generation"
    if failure_class == "tests_failed":
        if "no module named" in failure_reason or "error collecting" in failure_reason:
            return "repo_fixture_or_setup"
        return "operator_or_environment"
    if state == "queued" and str((issue or {}).get("backoff_until") or ""):
        return "product_bug"
    if "github" in failure_reason or "auth" in failure_reason or "network" in failure_reason:
        return "external_service_or_github"
    return "product_bug" if failure_class else "operator_or_environment"


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

    report = {
        "issue": issue,
        "latest_attempt": attempt,
        "diagnosis": _classify(issue, attempt),
    }
    print(json.dumps(report, indent=2, default=str))
    return 0 if issue is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
