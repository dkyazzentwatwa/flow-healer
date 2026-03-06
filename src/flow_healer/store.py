from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class SQLiteStore:
    """Healer-only SQLite store for standalone Flow Healer."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    def _connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                self._conn = conn
            return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def bootstrap(self) -> None:
        conn = self._connect()
        with self._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kv_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS healer_issues (
                    issue_id TEXT PRIMARY KEY,
                    repo TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    author TEXT NOT NULL DEFAULT '',
                    labels_json TEXT NOT NULL DEFAULT '[]',
                    priority INTEGER NOT NULL DEFAULT 100,
                    state TEXT NOT NULL DEFAULT 'queued',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    backoff_until TEXT DEFAULT NULL,
                    lease_owner TEXT DEFAULT NULL,
                    lease_expires_at TEXT DEFAULT NULL,
                    workspace_path TEXT NOT NULL DEFAULT '',
                    branch_name TEXT NOT NULL DEFAULT '',
                    pr_number INTEGER DEFAULT NULL,
                    pr_state TEXT NOT NULL DEFAULT '',
                    last_failure_class TEXT NOT NULL DEFAULT '',
                    last_failure_reason TEXT NOT NULL DEFAULT '',
                    last_comment_id TEXT DEFAULT NULL,
                    feedback_context TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS healer_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    issue_id TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    prediction_source TEXT NOT NULL DEFAULT '',
                    predicted_lock_set_json TEXT NOT NULL DEFAULT '[]',
                    actual_diff_set_json TEXT NOT NULL DEFAULT '[]',
                    test_summary_json TEXT NOT NULL DEFAULT '{}',
                    verifier_summary_json TEXT NOT NULL DEFAULT '{}',
                    failure_class TEXT NOT NULL DEFAULT '',
                    failure_reason TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT DEFAULT NULL
                );

                CREATE TABLE IF NOT EXISTS healer_lessons (
                    lesson_id TEXT PRIMARY KEY,
                    issue_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    lesson_kind TEXT NOT NULL,
                    scope_key TEXT NOT NULL DEFAULT 'repo:*',
                    fingerprint TEXT NOT NULL DEFAULT '',
                    problem_summary TEXT NOT NULL DEFAULT '',
                    lesson_text TEXT NOT NULL,
                    test_hint TEXT NOT NULL DEFAULT '',
                    guardrail_json TEXT NOT NULL DEFAULT '{}',
                    confidence INTEGER NOT NULL DEFAULT 50,
                    outcome TEXT NOT NULL DEFAULT 'unknown',
                    use_count INTEGER NOT NULL DEFAULT 0,
                    last_used_at TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS healer_locks (
                    lock_key TEXT PRIMARY KEY,
                    granularity TEXT NOT NULL,
                    issue_id TEXT NOT NULL,
                    lease_owner TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS scan_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    dry_run INTEGER NOT NULL DEFAULT 0,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS scan_findings (
                    fingerprint TEXT PRIMARY KEY,
                    scan_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    issue_number INTEGER DEFAULT NULL,
                    status TEXT NOT NULL DEFAULT 'detected',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_healer_issues_state_backoff ON healer_issues(state, backoff_until, priority, updated_at);
                CREATE INDEX IF NOT EXISTS idx_healer_attempts_started ON healer_attempts(started_at);
                CREATE INDEX IF NOT EXISTS idx_healer_locks_lease ON healer_locks(lease_expires_at);
                """
            )
            conn.commit()
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        with self._lock:
            existing_cols = {
                row["name"] for row in conn.execute("PRAGMA table_info(healer_issues)").fetchall()
            }
            if "last_comment_id" not in existing_cols:
                conn.execute("ALTER TABLE healer_issues ADD COLUMN last_comment_id TEXT DEFAULT NULL")
            if "feedback_context" not in existing_cols:
                conn.execute("ALTER TABLE healer_issues ADD COLUMN feedback_context TEXT NOT NULL DEFAULT ''")
            conn.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {key: row[key] for key in row.keys()}

    @staticmethod
    def _decode_healer_issue_row(data: dict[str, Any] | None) -> dict[str, Any] | None:
        if data is None:
            return None
        data["labels"] = _json_loads(data.pop("labels_json", "[]"), [])
        return data

    @staticmethod
    def _decode_healer_attempt_row(data: dict[str, Any] | None) -> dict[str, Any] | None:
        if data is None:
            return None
        data["predicted_lock_set"] = _json_loads(data.pop("predicted_lock_set_json", "[]"), [])
        data["actual_diff_set"] = _json_loads(data.pop("actual_diff_set_json", "[]"), [])
        data["test_summary"] = _json_loads(data.pop("test_summary_json", "{}"), {})
        data["verifier_summary"] = _json_loads(data.pop("verifier_summary_json", "{}"), {})
        return data

    @staticmethod
    def _decode_healer_lesson_row(data: dict[str, Any] | None) -> dict[str, Any] | None:
        if data is None:
            return None
        data["guardrail"] = _json_loads(data.pop("guardrail_json", "{}"), {})
        return data

    def upsert_healer_issue(
        self,
        *,
        issue_id: str,
        repo: str,
        title: str,
        body: str,
        author: str,
        labels: list[str],
        priority: int = 100,
    ) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO healer_issues(issue_id, repo, title, body, author, labels_json, priority, state)
                VALUES(?, ?, ?, ?, ?, ?, ?, 'queued')
                ON CONFLICT(issue_id) DO UPDATE SET
                    repo = excluded.repo,
                    title = excluded.title,
                    body = excluded.body,
                    author = excluded.author,
                    labels_json = excluded.labels_json,
                    priority = excluded.priority,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (issue_id, repo, title, body, author, json.dumps(labels or []), int(priority)),
            )
            conn.commit()

    def get_healer_issue(self, issue_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        with self._lock:
            row = conn.execute("SELECT * FROM healer_issues WHERE issue_id = ?", (issue_id,)).fetchone()
        return self._decode_healer_issue_row(self._row_to_dict(row))

    def list_healer_issues(self, *, states: list[str] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            if states:
                placeholders = ",".join("?" for _ in states)
                rows = conn.execute(
                    f"SELECT * FROM healer_issues WHERE state IN ({placeholders}) ORDER BY priority ASC, updated_at ASC LIMIT ?",
                    [*states, int(limit)],
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM healer_issues ORDER BY updated_at DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
        return [issue for row in rows if (issue := self._decode_healer_issue_row(self._row_to_dict(row))) is not None]

    def claim_next_healer_issue(self, *, worker_id: str, lease_seconds: int) -> dict[str, Any] | None:
        conn = self._connect()
        with self._lock:
            row = conn.execute(
                """
                SELECT issue_id
                FROM healer_issues
                WHERE state = 'queued'
                  AND (backoff_until IS NULL OR backoff_until <= CURRENT_TIMESTAMP)
                ORDER BY priority ASC, updated_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            issue_id = str(row["issue_id"])
            cursor = conn.execute(
                """
                UPDATE healer_issues
                SET state = 'claimed',
                    lease_owner = ?,
                    lease_expires_at = datetime('now', ?),
                    updated_at = CURRENT_TIMESTAMP
                WHERE issue_id = ? AND state = 'queued'
                """,
                (worker_id, f"+{int(max(1, lease_seconds))} seconds", issue_id),
            )
            if cursor.rowcount == 0:
                conn.commit()
                return None
            row = conn.execute("SELECT * FROM healer_issues WHERE issue_id = ?", (issue_id,)).fetchone()
            conn.commit()
        return self._decode_healer_issue_row(self._row_to_dict(row))

    def renew_healer_issue_lease(self, *, issue_id: str, worker_id: str, lease_seconds: int) -> bool:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE healer_issues
                SET lease_expires_at = datetime('now', ?), updated_at = CURRENT_TIMESTAMP
                WHERE issue_id = ? AND lease_owner = ? AND state IN ('claimed', 'running', 'verify_pending')
                """,
                (f"+{int(max(1, lease_seconds))} seconds", issue_id, worker_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def increment_healer_attempt(self, issue_id: str) -> int:
        conn = self._connect()
        with self._lock:
            conn.execute(
                "UPDATE healer_issues SET attempt_count = attempt_count + 1, updated_at = CURRENT_TIMESTAMP WHERE issue_id = ?",
                (issue_id,),
            )
            row = conn.execute("SELECT attempt_count FROM healer_issues WHERE issue_id = ?", (issue_id,)).fetchone()
            conn.commit()
        return int(row["attempt_count"]) if row is not None else 0

    def set_healer_issue_state(
        self,
        *,
        issue_id: str,
        state: str,
        backoff_until: str | None = None,
        workspace_path: str | None = None,
        branch_name: str | None = None,
        pr_number: int | None = None,
        pr_state: str | None = None,
        last_failure_class: str | None = None,
        last_failure_reason: str | None = None,
        last_comment_id: str | None = None,
        feedback_context: str | None = None,
        clear_lease: bool = False,
    ) -> bool:
        conn = self._connect()
        with self._lock:
            updates = ["state = ?", "updated_at = CURRENT_TIMESTAMP"]
            params: list[Any] = [state]
            if backoff_until is not None:
                updates.append("backoff_until = ?")
                params.append(backoff_until)
            if workspace_path is not None:
                updates.append("workspace_path = ?")
                params.append(workspace_path)
            if branch_name is not None:
                updates.append("branch_name = ?")
                params.append(branch_name)
            if pr_number is not None:
                updates.append("pr_number = ?")
                params.append(int(pr_number))
            if pr_state is not None:
                updates.append("pr_state = ?")
                params.append(pr_state)
            if last_failure_class is not None:
                updates.append("last_failure_class = ?")
                params.append(last_failure_class)
            if last_failure_reason is not None:
                updates.append("last_failure_reason = ?")
                params.append(last_failure_reason)
            if last_comment_id is not None:
                updates.append("last_comment_id = ?")
                params.append(last_comment_id)
            if feedback_context is not None:
                updates.append("feedback_context = ?")
                params.append(feedback_context)
            if clear_lease:
                updates.append("lease_owner = NULL")
                updates.append("lease_expires_at = NULL")
            params.append(issue_id)
            cursor = conn.execute(f"UPDATE healer_issues SET {', '.join(updates)} WHERE issue_id = ?", params)
            conn.commit()
            return cursor.rowcount > 0

    def requeue_expired_healer_issue_leases(self) -> int:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE healer_issues
                SET state = 'queued', lease_owner = NULL, lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE state IN ('claimed', 'running', 'verify_pending')
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at <= CURRENT_TIMESTAMP
                """
            )
            conn.commit()
            return int(cursor.rowcount)

    def create_healer_attempt(
        self,
        *,
        attempt_id: str,
        issue_id: str,
        attempt_no: int,
        state: str,
        prediction_source: str,
        predicted_lock_set: list[str],
    ) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO healer_attempts(
                    attempt_id, issue_id, attempt_no, state, prediction_source, predicted_lock_set_json
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (attempt_id, issue_id, int(attempt_no), state, prediction_source, json.dumps(predicted_lock_set or [])),
            )
            conn.commit()

    def finish_healer_attempt(
        self,
        *,
        attempt_id: str,
        state: str,
        actual_diff_set: list[str],
        test_summary: dict[str, Any],
        verifier_summary: dict[str, Any],
        failure_class: str = "",
        failure_reason: str = "",
    ) -> bool:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE healer_attempts
                SET state = ?,
                    actual_diff_set_json = ?,
                    test_summary_json = ?,
                    verifier_summary_json = ?,
                    failure_class = ?,
                    failure_reason = ?,
                    finished_at = CURRENT_TIMESTAMP
                WHERE attempt_id = ?
                """,
                (
                    state,
                    json.dumps(actual_diff_set or []),
                    json.dumps(test_summary or {}),
                    json.dumps(verifier_summary or {}),
                    (failure_class or "")[:120],
                    (failure_reason or "")[:500],
                    attempt_id,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_healer_attempts(self, *, issue_id: str, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                "SELECT * FROM healer_attempts WHERE issue_id = ? ORDER BY started_at DESC LIMIT ?",
                (issue_id, int(limit)),
            ).fetchall()
        return [attempt for row in rows if (attempt := self._decode_healer_attempt_row(self._row_to_dict(row))) is not None]

    def list_recent_healer_attempts(self, *, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute("SELECT * FROM healer_attempts ORDER BY started_at DESC LIMIT ?", (int(limit),)).fetchall()
        return [attempt for row in rows if (attempt := self._decode_healer_attempt_row(self._row_to_dict(row))) is not None]

    def create_healer_lesson(
        self,
        *,
        lesson_id: str,
        issue_id: str,
        attempt_id: str,
        lesson_kind: str,
        scope_key: str,
        fingerprint: str,
        problem_summary: str,
        lesson_text: str,
        test_hint: str,
        guardrail: dict[str, Any],
        confidence: int,
        outcome: str,
    ) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO healer_lessons(
                    lesson_id, issue_id, attempt_id, lesson_kind, scope_key, fingerprint,
                    problem_summary, lesson_text, test_hint, guardrail_json, confidence, outcome
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lesson_id,
                    issue_id,
                    attempt_id,
                    lesson_kind,
                    scope_key or "repo:*",
                    fingerprint,
                    problem_summary,
                    lesson_text,
                    test_hint,
                    json.dumps(guardrail or {}, ensure_ascii=True),
                    int(max(0, min(100, confidence))),
                    outcome,
                ),
            )
            conn.commit()

    def list_healer_lessons(self, *, limit: int = 200) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                "SELECT * FROM healer_lessons ORDER BY updated_at DESC, created_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [lesson for row in rows if (lesson := self._decode_healer_lesson_row(self._row_to_dict(row))) is not None]

    def mark_healer_lessons_used(self, lesson_ids: list[str]) -> int:
        lesson_ids = [lesson_id for lesson_id in dict.fromkeys(lesson_ids) if str(lesson_id).strip()]
        if not lesson_ids:
            return 0
        conn = self._connect()
        with self._lock:
            placeholders = ",".join("?" for _ in lesson_ids)
            cursor = conn.execute(
                f"""
                UPDATE healer_lessons
                SET use_count = use_count + 1, last_used_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE lesson_id IN ({placeholders})
                """,
                lesson_ids,
            )
            conn.commit()
            return int(cursor.rowcount or 0)

    def cleanup_expired_healer_locks(self) -> int:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute("DELETE FROM healer_locks WHERE lease_expires_at <= CURRENT_TIMESTAMP")
            conn.commit()
            return int(cursor.rowcount)

    def acquire_healer_lock(
        self,
        *,
        lock_key: str,
        granularity: str,
        issue_id: str,
        lease_owner: str,
        lease_seconds: int,
    ) -> bool:
        conn = self._connect()
        with self._lock:
            conn.execute("DELETE FROM healer_locks WHERE lease_expires_at <= CURRENT_TIMESTAMP")
            row = conn.execute("SELECT * FROM healer_locks WHERE lock_key = ?", (lock_key,)).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO healer_locks(lock_key, granularity, issue_id, lease_owner, lease_expires_at)
                    VALUES(?, ?, ?, ?, datetime('now', ?))
                    """,
                    (lock_key, granularity, issue_id, lease_owner, f"+{int(max(1, lease_seconds))} seconds"),
                )
                conn.commit()
                return True
            if str(row["issue_id"]) != issue_id:
                conn.commit()
                return False
            conn.execute(
                """
                UPDATE healer_locks
                SET granularity = ?, lease_owner = ?, lease_expires_at = datetime('now', ?)
                WHERE lock_key = ? AND issue_id = ?
                """,
                (granularity, lease_owner, f"+{int(max(1, lease_seconds))} seconds", lock_key, issue_id),
            )
            conn.commit()
            return True

    def release_healer_locks(self, *, issue_id: str, lock_keys: list[str] | None = None) -> int:
        conn = self._connect()
        with self._lock:
            if lock_keys:
                placeholders = ",".join("?" for _ in lock_keys)
                cursor = conn.execute(
                    f"DELETE FROM healer_locks WHERE issue_id = ? AND lock_key IN ({placeholders})",
                    [issue_id, *lock_keys],
                )
            else:
                cursor = conn.execute("DELETE FROM healer_locks WHERE issue_id = ?", (issue_id,))
            conn.commit()
            return int(cursor.rowcount)

    def list_healer_locks(self, *, issue_id: str | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            if issue_id:
                rows = conn.execute("SELECT * FROM healer_locks WHERE issue_id = ? ORDER BY lock_key ASC", (issue_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM healer_locks ORDER BY lock_key ASC").fetchall()
        return [entry for row in rows if (entry := self._row_to_dict(row)) is not None]

    def create_scan_run(self, *, run_id: str, dry_run: bool) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute("INSERT INTO scan_runs(run_id, status, dry_run) VALUES(?, 'running', ?)", (run_id, 1 if dry_run else 0))
            conn.commit()

    def finish_scan_run(self, *, run_id: str, status: str, summary: dict[str, Any]) -> bool:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                "UPDATE scan_runs SET status = ?, summary_json = ?, updated_at = CURRENT_TIMESTAMP WHERE run_id = ?",
                (status, json.dumps(summary or {}), run_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_scan_finding(self, fingerprint: str) -> dict[str, Any] | None:
        conn = self._connect()
        with self._lock:
            row = conn.execute("SELECT * FROM scan_findings WHERE fingerprint = ?", (fingerprint,)).fetchone()
        data = self._row_to_dict(row)
        if data is None:
            return None
        data["payload"] = _json_loads(data.pop("payload_json", "{}"), {})
        return data

    def upsert_scan_finding(
        self,
        *,
        fingerprint: str,
        scan_type: str,
        severity: str,
        title: str,
        status: str,
        payload: dict[str, Any],
        issue_number: int | None = None,
    ) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO scan_findings(fingerprint, scan_type, severity, title, issue_number, status, payload_json)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    scan_type = excluded.scan_type,
                    severity = excluded.severity,
                    title = excluded.title,
                    issue_number = COALESCE(excluded.issue_number, scan_findings.issue_number),
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    last_seen_at = CURRENT_TIMESTAMP
                """,
                (fingerprint, scan_type, severity, title, issue_number, status, json.dumps(payload or {})),
            )
            conn.commit()

    def set_state(self, key: str, value: str) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                "INSERT INTO kv_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            conn.commit()

    def get_state(self, key: str) -> str | None:
        conn = self._connect()
        with self._lock:
            row = conn.execute("SELECT value FROM kv_state WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row is not None else None


def _json_loads(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return default
