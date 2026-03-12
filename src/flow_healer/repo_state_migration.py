from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .store import SQLiteStore

_MIGRATION_MARKER_KEY = "repo_state_migration:last_source_signature"
_MIGRATION_APPLIED_AT_KEY = "repo_state_migration:last_applied_at"


def migrate_repo_state(
    *,
    source_db: Path,
    target_db: Path,
    source_repo_name: str = "flow-healer",
    target_repo_name: str = "flow-healer-self",
    normalize_active_issues: bool = True,
) -> dict[str, Any]:
    source_db = Path(source_db).expanduser().resolve()
    target_db = Path(target_db).expanduser().resolve()

    target_store = SQLiteStore(target_db)
    target_store.bootstrap()
    target_store.close()

    signature = _source_signature(source_db)
    target_conn = sqlite3.connect(target_db)
    target_conn.row_factory = sqlite3.Row
    existing_signature = _get_kv_state(target_conn, _MIGRATION_MARKER_KEY)
    if existing_signature == signature:
        target_conn.close()
        return {
            "source_repo_name": source_repo_name,
            "target_repo_name": target_repo_name,
            "source_db": str(source_db),
            "target_db": str(target_db),
            "skipped": True,
            "tables": {},
        }

    source_conn = sqlite3.connect(source_db)
    source_conn.row_factory = sqlite3.Row
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    table_counts: dict[str, dict[str, int]] = {}

    try:
        with target_conn:
            table_counts["kv_state"] = _merge_kv_state(source_conn, target_conn)
            table_counts["healer_issues"] = _merge_table(
                source_conn,
                target_conn,
                table="healer_issues",
                key_column="issue_id",
                compare_columns=("updated_at", "created_at"),
                row_transform=(
                    lambda row: _normalize_issue_row(row, now=now)
                    if normalize_active_issues
                    else dict(row)
                ),
            )
            table_counts["healer_attempts"] = _merge_table(
                source_conn,
                target_conn,
                table="healer_attempts",
                key_column="attempt_id",
                compare_columns=("finished_at", "started_at"),
            )
            table_counts["healer_lessons"] = _merge_table(
                source_conn,
                target_conn,
                table="healer_lessons",
                key_column="lesson_id",
                compare_columns=("updated_at", "created_at"),
            )
            table_counts["scan_runs"] = _merge_table(
                source_conn,
                target_conn,
                table="scan_runs",
                key_column="run_id",
                compare_columns=("updated_at", "created_at"),
            )
            table_counts["scan_findings"] = _merge_table(
                source_conn,
                target_conn,
                table="scan_findings",
                key_column="fingerprint",
                compare_columns=("last_seen_at", "first_seen_at"),
            )
            table_counts["healer_events"] = _merge_table(
                source_conn,
                target_conn,
                table="healer_events",
                key_column="event_id",
                compare_columns=("created_at",),
            )
            table_counts["control_commands"] = _merge_table(
                source_conn,
                target_conn,
                table="control_commands",
                key_column="command_id",
                compare_columns=("updated_at", "created_at"),
            )
            table_counts["healer_mutation_log"] = _merge_table(
                source_conn,
                target_conn,
                table="healer_mutation_log",
                key_column="mutation_key",
                compare_columns=("updated_at", "created_at"),
            )
            _set_kv_state(target_conn, _MIGRATION_MARKER_KEY, signature)
            _set_kv_state(target_conn, _MIGRATION_APPLIED_AT_KEY, now)
    finally:
        source_conn.close()
        target_conn.close()

    return {
        "source_repo_name": source_repo_name,
        "target_repo_name": target_repo_name,
        "source_db": str(source_db),
        "target_db": str(target_db),
        "skipped": False,
        "tables": table_counts,
    }


def _source_signature(source_db: Path) -> str:
    stat = source_db.stat()
    return f"{source_db}:{stat.st_mtime_ns}:{stat.st_size}"


def _merge_kv_state(source_conn: sqlite3.Connection, target_conn: sqlite3.Connection) -> dict[str, int]:
    rows = source_conn.execute("SELECT key, value FROM kv_state").fetchall()
    upserted = 0
    for row in rows:
        target_conn.execute(
            "INSERT OR REPLACE INTO kv_state(key, value) VALUES (?, ?)",
            (str(row["key"]), str(row["value"])),
        )
        upserted += 1
    return {"upserted": upserted}


def _merge_table(
    source_conn: sqlite3.Connection,
    target_conn: sqlite3.Connection,
    *,
    table: str,
    key_column: str,
    compare_columns: tuple[str, ...],
    row_transform: callable | None = None,
) -> dict[str, int]:
    source_rows = source_conn.execute(f"SELECT * FROM {table}").fetchall()
    upserted = 0
    for source_row in source_rows:
        candidate = row_transform(source_row) if row_transform else dict(source_row)
        current_row = target_conn.execute(
            f"SELECT * FROM {table} WHERE {key_column} = ?",
            (candidate[key_column],),
        ).fetchone()
        if current_row is not None and not _candidate_is_newer(candidate, dict(current_row), compare_columns):
            continue
        _upsert_row(target_conn, table=table, row=candidate)
        upserted += 1
    return {"upserted": upserted}


def _candidate_is_newer(candidate: dict[str, Any], current: dict[str, Any], compare_columns: tuple[str, ...]) -> bool:
    for column in compare_columns:
        candidate_value = str(candidate.get(column) or "")
        current_value = str(current.get(column) or "")
        if candidate_value > current_value:
            return True
        if candidate_value < current_value:
            return False
    return False


def _upsert_row(target_conn: sqlite3.Connection, *, table: str, row: dict[str, Any]) -> None:
    columns = list(row.keys())
    placeholders = ", ".join("?" for _ in columns)
    assignments = ", ".join(f"{column}=excluded.{column}" for column in columns)
    target_conn.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT DO UPDATE SET {assignments}",
        tuple(row[column] for column in columns),
    )


def _normalize_issue_row(row: sqlite3.Row, *, now: str) -> dict[str, Any]:
    normalized = dict(row)
    if str(normalized.get("state") or "") in {"claimed", "running", "verify_pending"}:
        normalized["state"] = "queued"
        normalized["lease_owner"] = ""
        normalized["lease_expires_at"] = None
        normalized["updated_at"] = now
    return normalized


def _get_kv_state(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM kv_state WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row is not None else ""


def _set_kv_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO kv_state(key, value) VALUES (?, ?)", (key, value))
