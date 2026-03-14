from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from .healer_locks import lock_granularity, lock_keys_conflict


class SQLiteStore:
    """Healer-only SQLite store for standalone Flow Healer."""

    def __init__(self, db_path: Path, *, busy_timeout_ms: int = 5000):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._busy_timeout_ms = max(1000, int(busy_timeout_ms))

    def _connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(
                    self.db_path,
                    check_same_thread=False,
                    timeout=max(1.0, float(self._busy_timeout_ms) / 1000.0),
                )
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
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
                    last_issue_comment_id INTEGER NOT NULL DEFAULT 0,
                    last_review_id INTEGER NOT NULL DEFAULT 0,
                    last_review_comment_id INTEGER NOT NULL DEFAULT 0,
                    pr_last_seen_updated_at TEXT NOT NULL DEFAULT '',
                    feedback_context TEXT NOT NULL DEFAULT '',
                    task_kind TEXT NOT NULL DEFAULT '',
                    output_targets_json TEXT NOT NULL DEFAULT '[]',
                    tool_policy TEXT NOT NULL DEFAULT '',
                    validation_profile TEXT NOT NULL DEFAULT '',
                    ci_status_summary_json TEXT NOT NULL DEFAULT '{}',
                    scope_key TEXT NOT NULL DEFAULT '',
                    dedupe_key TEXT NOT NULL DEFAULT '',
                    conflict_requeue_count INTEGER NOT NULL DEFAULT 0,
                    superseded_by_issue_id TEXT NOT NULL DEFAULT '',
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
                    proposer_output_excerpt TEXT NOT NULL DEFAULT '',
                    swarm_summary_json TEXT NOT NULL DEFAULT '{}',
                    runtime_summary_json TEXT NOT NULL DEFAULT '{}',
                    artifact_bundle_json TEXT NOT NULL DEFAULT '{}',
                    artifact_links_json TEXT NOT NULL DEFAULT '[]',
                    ci_status_summary_json TEXT NOT NULL DEFAULT '{}',
                    judgment_reason_code TEXT NOT NULL DEFAULT '',
                    task_kind TEXT NOT NULL DEFAULT '',
                    output_targets_json TEXT NOT NULL DEFAULT '[]',
                    tool_policy TEXT NOT NULL DEFAULT '',
                    validation_profile TEXT NOT NULL DEFAULT '',
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

                CREATE TABLE IF NOT EXISTS healer_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'info',
                    message TEXT NOT NULL,
                    issue_id TEXT NOT NULL DEFAULT '',
                    attempt_id TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS healer_runtime (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    status TEXT NOT NULL DEFAULT 'idle',
                    last_error TEXT NOT NULL DEFAULT '',
                    heartbeat_at TEXT DEFAULT NULL,
                    last_tick_started_at TEXT DEFAULT NULL,
                    last_tick_finished_at TEXT DEFAULT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS healer_mutation_log (
                    mutation_key TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'pending',
                    lease_owner TEXT DEFAULT NULL,
                    lease_expires_at TEXT DEFAULT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT DEFAULT NULL
                );

                CREATE TABLE IF NOT EXISTS control_commands (
                    command_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    sender TEXT NOT NULL DEFAULT '',
                    repo_name TEXT NOT NULL DEFAULT '',
                    raw_command TEXT NOT NULL DEFAULT '',
                    parsed_command TEXT NOT NULL DEFAULT '',
                    args_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'received',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error_text TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source, external_id)
                );

                """
            )
            conn.execute("INSERT OR IGNORE INTO healer_runtime(singleton, status) VALUES(1, 'idle')")
            conn.commit()
            self._migrate(conn)
            conn.commit()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        with self._lock:
            existing_cols = {
                row["name"] for row in conn.execute("PRAGMA table_info(healer_issues)").fetchall()
            }
            migrations = [
                ("last_issue_comment_id", "ALTER TABLE healer_issues ADD COLUMN last_issue_comment_id INTEGER NOT NULL DEFAULT 0"),
                ("last_review_id", "ALTER TABLE healer_issues ADD COLUMN last_review_id INTEGER NOT NULL DEFAULT 0"),
                ("last_review_comment_id", "ALTER TABLE healer_issues ADD COLUMN last_review_comment_id INTEGER NOT NULL DEFAULT 0"),
                ("pr_last_seen_updated_at", "ALTER TABLE healer_issues ADD COLUMN pr_last_seen_updated_at TEXT NOT NULL DEFAULT ''"),
                ("feedback_context", "ALTER TABLE healer_issues ADD COLUMN feedback_context TEXT NOT NULL DEFAULT ''"),
                ("task_kind", "ALTER TABLE healer_issues ADD COLUMN task_kind TEXT NOT NULL DEFAULT ''"),
                ("output_targets_json", "ALTER TABLE healer_issues ADD COLUMN output_targets_json TEXT NOT NULL DEFAULT '[]'"),
                ("tool_policy", "ALTER TABLE healer_issues ADD COLUMN tool_policy TEXT NOT NULL DEFAULT ''"),
                ("validation_profile", "ALTER TABLE healer_issues ADD COLUMN validation_profile TEXT NOT NULL DEFAULT ''"),
                ("ci_status_summary_json", "ALTER TABLE healer_issues ADD COLUMN ci_status_summary_json TEXT NOT NULL DEFAULT '{}'"),
                ("stuck_since", "ALTER TABLE healer_issues ADD COLUMN stuck_since TEXT DEFAULT NULL"),
                ("scope_key", "ALTER TABLE healer_issues ADD COLUMN scope_key TEXT NOT NULL DEFAULT ''"),
                ("dedupe_key", "ALTER TABLE healer_issues ADD COLUMN dedupe_key TEXT NOT NULL DEFAULT ''"),
                ("conflict_requeue_count", "ALTER TABLE healer_issues ADD COLUMN conflict_requeue_count INTEGER NOT NULL DEFAULT 0"),
                ("superseded_by_issue_id", "ALTER TABLE healer_issues ADD COLUMN superseded_by_issue_id TEXT NOT NULL DEFAULT ''"),
            ]
            for column, statement in migrations:
                if column not in existing_cols:
                    conn.execute(statement)
            attempt_cols = {
                row["name"] for row in conn.execute("PRAGMA table_info(healer_attempts)").fetchall()
            }
            attempt_migrations = [
                ("task_kind", "ALTER TABLE healer_attempts ADD COLUMN task_kind TEXT NOT NULL DEFAULT ''"),
                ("output_targets_json", "ALTER TABLE healer_attempts ADD COLUMN output_targets_json TEXT NOT NULL DEFAULT '[]'"),
                ("tool_policy", "ALTER TABLE healer_attempts ADD COLUMN tool_policy TEXT NOT NULL DEFAULT ''"),
                ("validation_profile", "ALTER TABLE healer_attempts ADD COLUMN validation_profile TEXT NOT NULL DEFAULT ''"),
                ("proposer_output_excerpt", "ALTER TABLE healer_attempts ADD COLUMN proposer_output_excerpt TEXT NOT NULL DEFAULT ''"),
                ("swarm_summary_json", "ALTER TABLE healer_attempts ADD COLUMN swarm_summary_json TEXT NOT NULL DEFAULT '{}'"),
                ("runtime_summary_json", "ALTER TABLE healer_attempts ADD COLUMN runtime_summary_json TEXT NOT NULL DEFAULT '{}'"),
                ("artifact_bundle_json", "ALTER TABLE healer_attempts ADD COLUMN artifact_bundle_json TEXT NOT NULL DEFAULT '{}'"),
                ("artifact_links_json", "ALTER TABLE healer_attempts ADD COLUMN artifact_links_json TEXT NOT NULL DEFAULT '[]'"),
                ("ci_status_summary_json", "ALTER TABLE healer_attempts ADD COLUMN ci_status_summary_json TEXT NOT NULL DEFAULT '{}'"),
                ("judgment_reason_code", "ALTER TABLE healer_attempts ADD COLUMN judgment_reason_code TEXT NOT NULL DEFAULT ''"),
            ]
            for column, statement in attempt_migrations:
                if column not in attempt_cols:
                    conn.execute(statement)
            mutation_cols = {
                row["name"] for row in conn.execute("PRAGMA table_info(healer_mutation_log)").fetchall()
            }
            mutation_migrations = [
                ("lease_owner", "ALTER TABLE healer_mutation_log ADD COLUMN lease_owner TEXT DEFAULT NULL"),
                ("lease_expires_at", "ALTER TABLE healer_mutation_log ADD COLUMN lease_expires_at TEXT DEFAULT NULL"),
                ("retry_count", "ALTER TABLE healer_mutation_log ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0"),
            ]
            for column, statement in mutation_migrations:
                if column not in mutation_cols:
                    conn.execute(statement)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_healer_issues_state_backoff ON healer_issues(state, backoff_until, priority, updated_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_healer_issues_scope_state ON healer_issues(scope_key, state, updated_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_healer_issues_state_priority_updated ON healer_issues(state, priority, updated_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_healer_issues_dedupe_state ON healer_issues(dedupe_key, state, updated_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_healer_issues_state_workspace ON healer_issues(state, workspace_path, updated_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_healer_issues_state_scope_priority_updated ON healer_issues(state, scope_key, priority, updated_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_healer_issues_state_lease ON healer_issues(state, lease_expires_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_healer_attempts_issue_started ON healer_attempts(issue_id, started_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_healer_attempts_state_finished_issue ON healer_attempts(state, finished_at, issue_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_healer_attempts_issue_attempt_no ON healer_attempts(issue_id, attempt_no)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_healer_locks_lease ON healer_locks(lease_expires_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_healer_events_created ON healer_events(created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_healer_events_issue_created ON healer_events(issue_id, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_control_commands_created ON control_commands(created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_control_commands_repo_created ON control_commands(repo_name, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_healer_mutation_log_lease ON healer_mutation_log(lease_expires_at)"
            )
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
        data["output_targets"] = _json_loads(data.pop("output_targets_json", "[]"), [])
        data["ci_status_summary"] = _json_loads(data.pop("ci_status_summary_json", "{}"), {})
        return data

    @staticmethod
    def _decode_healer_attempt_row(data: dict[str, Any] | None) -> dict[str, Any] | None:
        if data is None:
            return None
        data["predicted_lock_set"] = _json_loads(data.pop("predicted_lock_set_json", "[]"), [])
        data["actual_diff_set"] = _json_loads(data.pop("actual_diff_set_json", "[]"), [])
        data["test_summary"] = _json_loads(data.pop("test_summary_json", "{}"), {})
        data["verifier_summary"] = _json_loads(data.pop("verifier_summary_json", "{}"), {})
        data["swarm_summary"] = _json_loads(data.pop("swarm_summary_json", "{}"), {})
        data["runtime_summary"] = _json_loads(data.pop("runtime_summary_json", "{}"), {})
        data["artifact_bundle"] = _json_loads(data.pop("artifact_bundle_json", "{}"), {})
        data["artifact_links"] = _json_loads(data.pop("artifact_links_json", "[]"), [])
        data["ci_status_summary"] = _json_loads(data.pop("ci_status_summary_json", "{}"), {})
        data["output_targets"] = _json_loads(data.pop("output_targets_json", "[]"), [])
        return data

    @staticmethod
    def _decode_healer_lesson_row(data: dict[str, Any] | None) -> dict[str, Any] | None:
        if data is None:
            return None
        data["guardrail"] = _json_loads(data.pop("guardrail_json", "{}"), {})
        return data

    @staticmethod
    def _decode_healer_event_row(data: dict[str, Any] | None) -> dict[str, Any] | None:
        if data is None:
            return None
        data["payload"] = _json_loads(data.pop("payload_json", "{}"), {})
        return data

    @staticmethod
    def _decode_control_command_row(data: dict[str, Any] | None) -> dict[str, Any] | None:
        if data is None:
            return None
        data["args"] = _json_loads(data.pop("args_json", "{}"), {})
        data["result"] = _json_loads(data.pop("result_json", "{}"), {})
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
        scope_key: str = "",
        dedupe_key: str = "",
    ) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO healer_issues(
                    issue_id, repo, title, body, author, labels_json, priority, state, scope_key, dedupe_key
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
                ON CONFLICT(issue_id) DO UPDATE SET
                    repo = excluded.repo,
                    title = excluded.title,
                    body = excluded.body,
                    author = excluded.author,
                    labels_json = excluded.labels_json,
                    priority = excluded.priority,
                    scope_key = excluded.scope_key,
                    dedupe_key = excluded.dedupe_key,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    issue_id,
                    repo,
                    title,
                    body,
                    author,
                    json.dumps(labels or []),
                    int(priority),
                    str(scope_key or ""),
                    str(dedupe_key or ""),
                ),
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

    def list_healer_issue_workspace_refs(
        self,
        *,
        states: list[str],
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        if not states:
            return []
        conn = self._connect()
        with self._lock:
            placeholders = ",".join("?" for _ in states)
            rows = conn.execute(
                f"""
                SELECT issue_id, state, workspace_path, branch_name, lease_owner, lease_expires_at
                FROM healer_issues
                WHERE state IN ({placeholders})
                  AND COALESCE(workspace_path, '') != ''
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                [*states, int(limit)],
            ).fetchall()
        return [entry for row in rows if (entry := self._row_to_dict(row)) is not None]

    def find_active_issue_by_dedupe_key(
        self,
        *,
        dedupe_key: str,
        exclude_issue_id: str = "",
        states: list[str] | None = None,
    ) -> dict[str, Any] | None:
        key = str(dedupe_key or "").strip()
        if not key:
            return None
        active_states = states or ["queued", "claimed", "running", "verify_pending", "pr_open", "pr_pending_approval"]
        conn = self._connect()
        with self._lock:
            placeholders = ",".join("?" for _ in active_states)
            params: list[Any] = [key, *active_states]
            sql = (
                "SELECT * FROM healer_issues "
                f"WHERE dedupe_key = ? AND state IN ({placeholders}) "
            )
            exclude = str(exclude_issue_id or "").strip()
            if exclude:
                sql += "AND issue_id != ? "
                params.append(exclude)
            sql += "ORDER BY created_at ASC, updated_at ASC LIMIT 1"
            row = conn.execute(sql, params).fetchone()
        return self._decode_healer_issue_row(self._row_to_dict(row))

    def claim_next_healer_issue(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        max_active_issues: int = 1,
        enforce_scope_queue: bool = True,
    ) -> dict[str, Any] | None:
        conn = self._connect()
        with self._lock:
            active_limit = max(1, int(max_active_issues))
            active_row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM healer_issues
                WHERE state IN ('claimed', 'running', 'verify_pending')
                  AND (lease_expires_at IS NULL OR lease_expires_at > CURRENT_TIMESTAMP)
                """
            ).fetchone()
            active_count = int(active_row["count"]) if active_row is not None else 0
            if active_count >= active_limit:
                return None
            scope_conflict_clause = ""
            if enforce_scope_queue:
                scope_conflict_clause = (
                    "AND (scope_key = '' OR NOT EXISTS ("
                    "SELECT 1 FROM healer_issues active "
                    "WHERE active.issue_id != healer_issues.issue_id "
                    "AND active.state IN ('claimed', 'running', 'verify_pending', 'pr_open', 'pr_pending_approval') "
                    "AND active.scope_key = healer_issues.scope_key "
                    "AND ("
                    "active.state IN ('pr_open', 'pr_pending_approval') "
                    "OR active.lease_expires_at IS NULL "
                    "OR active.lease_expires_at > CURRENT_TIMESTAMP"
                    ") "
                    "))"
                )
            row = conn.execute(
                f"""
                SELECT issue_id
                FROM healer_issues
                WHERE state = 'queued'
                  AND (backoff_until IS NULL OR backoff_until <= CURRENT_TIMESTAMP)
                  {scope_conflict_clause}
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

    def increment_conflict_requeue_count(self, issue_id: str) -> int:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                UPDATE healer_issues
                SET conflict_requeue_count = conflict_requeue_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE issue_id = ?
                """,
                (issue_id,),
            )
            row = conn.execute(
                "SELECT conflict_requeue_count FROM healer_issues WHERE issue_id = ?",
                (issue_id,),
            ).fetchone()
            conn.commit()
        return int(row["conflict_requeue_count"]) if row is not None else 0

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
        last_issue_comment_id: int | None = None,
        last_review_id: int | None = None,
        last_review_comment_id: int | None = None,
        pr_last_seen_updated_at: str | None = None,
        feedback_context: str | None = None,
        task_kind: str | None = None,
        output_targets: list[str] | None = None,
        tool_policy: str | None = None,
        validation_profile: str | None = None,
        ci_status_summary: dict[str, Any] | None = None,
        scope_key: str | None = None,
        dedupe_key: str | None = None,
        conflict_requeue_count: int | None = None,
        superseded_by_issue_id: str | None = None,
        clear_lease: bool = False,
        expected_state: str | None = None,
        expected_lease_owner: str | None = None,
        expected_worker_id: str | None = None,
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
            if last_issue_comment_id is not None:
                updates.append("last_issue_comment_id = ?")
                params.append(int(last_issue_comment_id))
            if last_review_id is not None:
                updates.append("last_review_id = ?")
                params.append(int(last_review_id))
            if last_review_comment_id is not None:
                updates.append("last_review_comment_id = ?")
                params.append(int(last_review_comment_id))
            if pr_last_seen_updated_at is not None:
                updates.append("pr_last_seen_updated_at = ?")
                params.append(pr_last_seen_updated_at)
            if feedback_context is not None:
                updates.append("feedback_context = ?")
                params.append(feedback_context)
            if task_kind is not None:
                updates.append("task_kind = ?")
                params.append(task_kind)
            if output_targets is not None:
                updates.append("output_targets_json = ?")
                params.append(json.dumps(output_targets))
            if tool_policy is not None:
                updates.append("tool_policy = ?")
                params.append(tool_policy)
            if validation_profile is not None:
                updates.append("validation_profile = ?")
                params.append(validation_profile)
            if ci_status_summary is not None:
                updates.append("ci_status_summary_json = ?")
                params.append(json.dumps(ci_status_summary or {}))
            if scope_key is not None:
                updates.append("scope_key = ?")
                params.append(scope_key)
            if dedupe_key is not None:
                updates.append("dedupe_key = ?")
                params.append(dedupe_key)
            if conflict_requeue_count is not None:
                updates.append("conflict_requeue_count = ?")
                params.append(int(conflict_requeue_count))
            if superseded_by_issue_id is not None:
                updates.append("superseded_by_issue_id = ?")
                params.append(superseded_by_issue_id)
            if clear_lease:
                updates.append("lease_owner = NULL")
                updates.append("lease_expires_at = NULL")
            where_parts = ["issue_id = ?"]
            where_params: list[Any] = [issue_id]
            if expected_state is not None:
                where_parts.append("state = ?")
                where_params.append(expected_state)
            guard_owner = expected_lease_owner if expected_lease_owner is not None else expected_worker_id
            if guard_owner is not None:
                guard_owner = str(guard_owner)
                if guard_owner == "":
                    where_parts.append("COALESCE(lease_owner, '') = ''")
                else:
                    where_parts.append("lease_owner = ?")
                    where_params.append(guard_owner)
            cursor = conn.execute(
                f"UPDATE healer_issues SET {', '.join(updates)} WHERE {' AND '.join(where_parts)}",
                [*params, *where_params],
            )
            conn.commit()
            return cursor.rowcount > 0

    def mark_pr_stuck(self, *, issue_id: str, pr_number: int) -> bool:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                "UPDATE healer_issues SET stuck_since = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE issue_id = ? AND stuck_since IS NULL",
                (issue_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def clear_pr_stuck(self, *, issue_id: str) -> bool:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                "UPDATE healer_issues SET stuck_since = NULL, updated_at = CURRENT_TIMESTAMP WHERE issue_id = ?",
                (issue_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_issue_pr_ci_status(self, *, issue_id: str, ci_status_summary: dict[str, Any]) -> bool:
        normalized_summary = dict(ci_status_summary or {})
        conn = self._connect()
        with self._lock:
            issue_cursor = conn.execute(
                """
                UPDATE healer_issues
                SET ci_status_summary_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE issue_id = ?
                """,
                (json.dumps(normalized_summary), issue_id),
            )
            attempt_row = conn.execute(
                """
                SELECT attempt_id
                FROM healer_attempts
                WHERE issue_id = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (issue_id,),
            ).fetchone()
            if attempt_row is not None:
                conn.execute(
                    """
                    UPDATE healer_attempts
                    SET ci_status_summary_json = ?
                    WHERE attempt_id = ?
                    """,
                    (json.dumps(normalized_summary), str(attempt_row["attempt_id"])),
                )
            conn.commit()
            return issue_cursor.rowcount > 0

    def requeue_expired_healer_issue_leases(self) -> int:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE healer_issues
                SET state = 'queued', lease_owner = NULL, lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE state IN ('claimed', 'running', 'verify_pending')
                  AND (
                    (lease_expires_at IS NOT NULL AND lease_expires_at <= CURRENT_TIMESTAMP)
                    OR ((lease_owner IS NULL OR TRIM(lease_owner) = '') AND lease_expires_at IS NULL)
                  )
                """
            )
            conn.commit()
            return int(cursor.rowcount)

    def interrupt_inactive_healer_attempts(self, *, reason: str = "lease expired or worker stopped") -> int:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE healer_attempts
                SET state = 'interrupted',
                    failure_class = 'interrupted',
                    failure_reason = ?,
                    finished_at = CURRENT_TIMESTAMP
                WHERE state = 'running'
                  AND finished_at IS NULL
                  AND issue_id IN (
                      SELECT issue_id
                      FROM healer_issues
                      WHERE state NOT IN ('claimed', 'running', 'verify_pending')
                  )
                """,
                ((reason or "lease expired or worker stopped")[:500],),
            )
            conn.commit()
            return int(cursor.rowcount or 0)

    def interrupt_superseded_healer_attempts(self, *, reason: str = "superseded by a newer attempt") -> int:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE healer_attempts
                SET state = 'interrupted',
                    failure_class = 'interrupted',
                    failure_reason = ?,
                    finished_at = CURRENT_TIMESTAMP
                WHERE state = 'running'
                  AND finished_at IS NULL
                  AND EXISTS (
                      SELECT 1
                      FROM healer_issues
                      WHERE healer_issues.issue_id = healer_attempts.issue_id
                        AND healer_attempts.attempt_no < healer_issues.attempt_count
                  )
                """,
                ((reason or "superseded by a newer attempt")[:500],),
            )
            conn.commit()
            return int(cursor.rowcount or 0)

    def create_healer_attempt(
        self,
        *,
        attempt_id: str,
        issue_id: str,
        attempt_no: int,
        state: str,
        prediction_source: str,
        predicted_lock_set: list[str],
        task_kind: str = "",
        output_targets: list[str] | None = None,
        tool_policy: str = "",
        validation_profile: str = "",
    ) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO healer_attempts(
                    attempt_id, issue_id, attempt_no, state, prediction_source, predicted_lock_set_json,
                    task_kind, output_targets_json, tool_policy, validation_profile
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    issue_id,
                    int(attempt_no),
                    state,
                    prediction_source,
                    json.dumps(predicted_lock_set or []),
                    task_kind,
                    json.dumps(output_targets or []),
                    tool_policy,
                    validation_profile,
                ),
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
        swarm_summary: dict[str, Any] | None = None,
        runtime_summary: dict[str, Any] | None = None,
        artifact_bundle: dict[str, Any] | None = None,
        artifact_links: list[dict[str, Any]] | None = None,
        ci_status_summary: dict[str, Any] | None = None,
        judgment_reason_code: str = "",
        failure_class: str = "",
        failure_reason: str = "",
        proposer_output_excerpt: str = "",
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
                    swarm_summary_json = ?,
                    runtime_summary_json = ?,
                    artifact_bundle_json = ?,
                    artifact_links_json = ?,
                    ci_status_summary_json = ?,
                    judgment_reason_code = ?,
                    failure_class = ?,
                    failure_reason = ?,
                    proposer_output_excerpt = ?,
                    finished_at = CURRENT_TIMESTAMP
                WHERE attempt_id = ?
                """,
                (
                    state,
                    json.dumps(actual_diff_set or []),
                    json.dumps(test_summary or {}),
                    json.dumps(verifier_summary or {}),
                    json.dumps(swarm_summary or {}),
                    json.dumps(runtime_summary or {}),
                    json.dumps(artifact_bundle or {}),
                    json.dumps(artifact_links or []),
                    json.dumps(ci_status_summary or {}),
                    (judgment_reason_code or "")[:120],
                    (failure_class or "")[:120],
                    (failure_reason or "")[:500],
                    (proposer_output_excerpt or "")[:1500],
                    attempt_id,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_healer_attempts(self, *, issue_id: str, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                (
                    "SELECT * FROM healer_attempts "
                    "WHERE issue_id = ? "
                    "ORDER BY attempt_no DESC, started_at DESC, rowid DESC LIMIT ?"
                ),
                (issue_id, int(limit)),
            ).fetchall()
        return [attempt for row in rows if (attempt := self._decode_healer_attempt_row(self._row_to_dict(row))) is not None]

    def list_recent_healer_attempts(self, *, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                "SELECT * FROM healer_attempts ORDER BY started_at DESC, rowid DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [attempt for row in rows if (attempt := self._decode_healer_attempt_row(self._row_to_dict(row))) is not None]

    def list_healer_attempts_in_window(
        self,
        *,
        days: int,
        offset_days: int = 0,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        window_days = max(1, int(days))
        offset = max(0, int(offset_days))
        start_days = offset + window_days
        conn = self._connect()
        with self._lock:
            if offset > 0:
                rows = conn.execute(
                    """
                    SELECT * FROM healer_attempts
                    WHERE started_at >= datetime('now', ?)
                      AND started_at < datetime('now', ?)
                    ORDER BY started_at DESC, rowid DESC
                    LIMIT ?
                    """,
                    (f"-{start_days} days", f"-{offset} days", int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM healer_attempts
                    WHERE started_at >= datetime('now', ?)
                    ORDER BY started_at DESC, rowid DESC
                    LIMIT ?
                    """,
                    (f"-{start_days} days", int(limit)),
                ).fetchall()
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

    def list_healer_lessons_for_issue(self, *, issue_id: str, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                """
                SELECT * FROM healer_lessons
                WHERE issue_id = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (issue_id, int(limit)),
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
            rows = conn.execute("SELECT * FROM healer_locks ORDER BY lock_key ASC").fetchall()
            renew_existing = False
            for row in rows:
                existing_key = str(row["lock_key"] or "")
                existing_issue_id = str(row["issue_id"] or "")
                if existing_key == lock_key and existing_issue_id == issue_id:
                    renew_existing = True
                    continue
                if existing_issue_id != issue_id and lock_keys_conflict(existing_key, lock_key):
                    conn.commit()
                    return False
            if not renew_existing:
                conn.execute(
                    """
                    INSERT INTO healer_locks(lock_key, granularity, issue_id, lease_owner, lease_expires_at)
                    VALUES(?, ?, ?, ?, datetime('now', ?))
                    """,
                    (lock_key, granularity, issue_id, lease_owner, f"+{int(max(1, lease_seconds))} seconds"),
                )
                conn.commit()
                return True
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

    def acquire_healer_locks_batch(
        self,
        *,
        lock_keys: list[str],
        issue_id: str,
        lease_owner: str,
        lease_seconds: int,
    ) -> tuple[bool, str, list[str]]:
        keys = [str(lock_key or "").strip() for lock_key in lock_keys if str(lock_key or "").strip()]
        if not keys:
            return True, "", []

        conn = self._connect()
        with self._lock:
            # Batch acquisition keeps claim-time lock work to one table scan and one commit.
            conn.execute("DELETE FROM healer_locks WHERE lease_expires_at <= CURRENT_TIMESTAMP")
            rows = conn.execute("SELECT * FROM healer_locks ORDER BY lock_key ASC").fetchall()
            existing_by_key: dict[str, sqlite3.Row] = {}
            for row in rows:
                existing_key = str(row["lock_key"] or "")
                existing_issue_id = str(row["issue_id"] or "")
                existing_by_key[existing_key] = row
                if existing_issue_id == issue_id:
                    continue
                for lock_key in keys:
                    if lock_keys_conflict(existing_key, lock_key):
                        conn.commit()
                        return False, lock_key, []

            renew_keys: list[str] = []
            insert_rows: list[tuple[str, str, str, str, str]] = []
            for lock_key in keys:
                granularity = lock_granularity(lock_key)
                existing = existing_by_key.get(lock_key)
                if existing is not None and str(existing["issue_id"] or "") == issue_id:
                    renew_keys.append(lock_key)
                    continue
                insert_rows.append(
                    (lock_key, granularity, issue_id, lease_owner, f"+{int(max(1, lease_seconds))} seconds")
                )

            if renew_keys:
                placeholders = ",".join("?" for _ in renew_keys)
                conn.execute(
                    f"""
                    UPDATE healer_locks
                    SET lease_owner = ?, lease_expires_at = datetime('now', ?)
                    WHERE issue_id = ? AND lock_key IN ({placeholders})
                    """,
                    [lease_owner, f"+{int(max(1, lease_seconds))} seconds", issue_id, *renew_keys],
                )
            if insert_rows:
                conn.executemany(
                    """
                    INSERT INTO healer_locks(lock_key, granularity, issue_id, lease_owner, lease_expires_at)
                    VALUES(?, ?, ?, ?, datetime('now', ?))
                    """,
                    insert_rows,
                )
            conn.commit()
            return True, "", list(keys)

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

    def release_healer_locks_for_owner(
        self,
        *,
        issue_id: str,
        lease_owner: str,
        lock_keys: list[str] | None = None,
    ) -> int:
        owner = str(lease_owner or "").strip()
        if not owner:
            return 0
        conn = self._connect()
        with self._lock:
            if lock_keys:
                placeholders = ",".join("?" for _ in lock_keys)
                cursor = conn.execute(
                    f"DELETE FROM healer_locks WHERE issue_id = ? AND lease_owner = ? AND lock_key IN ({placeholders})",
                    [issue_id, owner, *lock_keys],
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM healer_locks WHERE issue_id = ? AND lease_owner = ?",
                    (issue_id, owner),
                )
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

    def create_healer_event(
        self,
        *,
        event_type: str,
        message: str,
        level: str = "info",
        issue_id: str = "",
        attempt_id: str = "",
        payload: dict[str, Any] | None = None,
    ) -> str:
        conn = self._connect()
        event_id = f"hev_{uuid4().hex[:12]}"
        with self._lock:
            conn.execute(
                """
                INSERT INTO healer_events(event_id, event_type, level, message, issue_id, attempt_id, payload_json)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event_type.strip()[:80],
                    level.strip()[:20] or "info",
                    message[:500],
                    issue_id.strip(),
                    attempt_id.strip(),
                    json.dumps(payload or {}, ensure_ascii=True),
                ),
            )
            conn.commit()
        return event_id

    def list_healer_events(
        self,
        *,
        issue_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            if issue_id:
                rows = conn.execute(
                    """
                    SELECT * FROM healer_events
                    WHERE issue_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (issue_id, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM healer_events ORDER BY created_at DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
        return [event for row in rows if (event := self._decode_healer_event_row(self._row_to_dict(row))) is not None]

    def has_control_command(self, *, source: str, external_id: str) -> bool:
        conn = self._connect()
        with self._lock:
            row = conn.execute(
                "SELECT 1 AS present FROM control_commands WHERE source = ? AND external_id = ?",
                (source[:40], external_id[:200]),
            ).fetchone()
        return row is not None

    def create_control_command(
        self,
        *,
        source: str,
        external_id: str,
        sender: str,
        repo_name: str,
        raw_command: str,
        parsed_command: str,
        args: dict[str, Any] | None = None,
        status: str = "received",
    ) -> str:
        conn = self._connect()
        command_id = f"hctl_{uuid4().hex[:12]}"
        with self._lock:
            conn.execute(
                """
                INSERT INTO control_commands(
                    command_id, source, external_id, sender, repo_name, raw_command, parsed_command,
                    args_json, status
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command_id,
                    source[:40],
                    external_id[:200],
                    sender[:200],
                    repo_name[:120],
                    raw_command[:500],
                    parsed_command[:120],
                    json.dumps(args or {}, ensure_ascii=True),
                    status[:40],
                ),
            )
            conn.commit()
        return command_id

    def update_control_command(
        self,
        *,
        command_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error_text: str = "",
    ) -> bool:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE control_commands
                SET status = ?,
                    result_json = ?,
                    error_text = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE command_id = ?
                """,
                (
                    status[:40],
                    json.dumps(result or {}, ensure_ascii=True),
                    error_text[:500],
                    command_id,
                ),
            )
            conn.commit()
            return bool(cursor.rowcount)

    def list_control_commands(self, *, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                "SELECT * FROM control_commands ORDER BY created_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [item for row in rows if (item := self._decode_control_command_row(self._row_to_dict(row))) is not None]

    def update_runtime_status(
        self,
        *,
        status: str,
        last_error: str | None = None,
        touch_heartbeat: bool = False,
        touch_tick_started: bool = False,
        touch_tick_finished: bool = False,
    ) -> None:
        conn = self._connect()
        with self._lock:
            updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
            params: list[Any] = [status.strip()[:40] or "idle"]
            if last_error is not None:
                updates.append("last_error = ?")
                params.append(last_error[:500])
            if touch_heartbeat:
                updates.append("heartbeat_at = CURRENT_TIMESTAMP")
            if touch_tick_started:
                updates.append("last_tick_started_at = CURRENT_TIMESTAMP")
            if touch_tick_finished:
                updates.append("last_tick_finished_at = CURRENT_TIMESTAMP")
            params.append(1)
            conn.execute(f"UPDATE healer_runtime SET {', '.join(updates)} WHERE singleton = ?", params)
            conn.commit()

    def get_runtime_status(self) -> dict[str, Any] | None:
        conn = self._connect()
        with self._lock:
            row = conn.execute("SELECT * FROM healer_runtime WHERE singleton = 1").fetchone()
        return self._row_to_dict(row)

    def claim_healer_mutation(
        self,
        *,
        mutation_key: str,
        lease_owner: str | None = None,
        lease_seconds: int = 300,
    ) -> str:
        key = str(mutation_key or "").strip()
        if not key:
            return "failed"
        owner = str(lease_owner or "").strip()
        lease_expr = f"+{int(max(1, lease_seconds))} seconds"
        conn = self._connect()
        with self._lock:
            row = conn.execute(
                "SELECT status, lease_owner, lease_expires_at FROM healer_mutation_log WHERE mutation_key = ?",
                (key,),
            ).fetchone()
            if row is not None:
                status = str(row["status"] or "").strip().lower()
                if status == "success":
                    return "already_success"
                if status == "pending":
                    current_owner = str(row["lease_owner"] or "").strip()
                    lease_expires_at = row["lease_expires_at"]
                    lease_active = False
                    if lease_expires_at:
                        active_row = conn.execute(
                            "SELECT datetime(?) > CURRENT_TIMESTAMP AS active",
                            (str(lease_expires_at),),
                        ).fetchone()
                        lease_active = bool(int(active_row["active"])) if active_row is not None else False
                    same_owner = bool(owner and owner == current_owner)
                    if lease_active or same_owner:
                        return "inflight"
                conn.execute(
                    """
                    UPDATE healer_mutation_log
                    SET status='pending',
                        lease_owner = NULLIF(?, ''),
                        lease_expires_at = datetime('now', ?),
                        retry_count = retry_count + 1,
                        updated_at=CURRENT_TIMESTAMP,
                        completed_at=NULL
                    WHERE mutation_key = ?
                    """,
                    (owner, lease_expr, key),
                )
                conn.commit()
                return "claimed"
            conn.execute(
                """
                INSERT INTO healer_mutation_log(
                    mutation_key, status, lease_owner, lease_expires_at, retry_count, completed_at
                )
                VALUES(?, 'pending', NULLIF(?, ''), datetime('now', ?), 0, NULL)
                """,
                (key, owner, lease_expr),
            )
            conn.commit()
            return "claimed"

    def get_healer_mutation(self, mutation_key: str) -> dict[str, Any] | None:
        key = str(mutation_key or "").strip()
        if not key:
            return None
        conn = self._connect()
        with self._lock:
            row = conn.execute(
                "SELECT * FROM healer_mutation_log WHERE mutation_key = ?",
                (key,),
            ).fetchone()
        return self._row_to_dict(row)

    def complete_healer_mutation(self, *, mutation_key: str, success: bool) -> None:
        key = str(mutation_key or "").strip()
        if not key:
            return
        conn = self._connect()
        with self._lock:
            if success:
                conn.execute(
                    """
                    UPDATE healer_mutation_log
                    SET status='success',
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        updated_at=CURRENT_TIMESTAMP,
                        completed_at=CURRENT_TIMESTAMP
                    WHERE mutation_key = ?
                    """,
                    (key,),
                )
            else:
                conn.execute(
                    "DELETE FROM healer_mutation_log WHERE mutation_key = ?",
                    (key,),
                )
            conn.commit()

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

    def list_scan_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                "SELECT * FROM scan_runs ORDER BY created_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        decoded: list[dict[str, Any]] = []
        for row in rows:
            data = self._row_to_dict(row)
            if data is None:
                continue
            data["summary"] = _json_loads(data.pop("summary_json", "{}"), {})
            decoded.append(data)
        return decoded

    def get_scan_finding(self, fingerprint: str) -> dict[str, Any] | None:
        conn = self._connect()
        with self._lock:
            row = conn.execute("SELECT * FROM scan_findings WHERE fingerprint = ?", (fingerprint,)).fetchone()
        data = self._row_to_dict(row)
        if data is None:
            return None
        data["payload"] = _json_loads(data.pop("payload_json", "{}"), {})
        return data

    def list_scan_findings(
        self,
        *,
        statuses: list[str] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                rows = conn.execute(
                    f"""
                    SELECT * FROM scan_findings
                    WHERE status IN ({placeholders})
                    ORDER BY last_seen_at DESC, severity DESC, title ASC
                    LIMIT ?
                    """,
                    [*statuses, int(limit)],
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM scan_findings
                    ORDER BY last_seen_at DESC, severity DESC, title ASC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
        findings: list[dict[str, Any]] = []
        for row in rows:
            data = self._row_to_dict(row)
            if data is None:
                continue
            data["payload"] = _json_loads(data.pop("payload_json", "{}"), {})
            findings.append(data)
        return findings

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
        self.set_states({key: value})

    def set_states(self, values: dict[str, str]) -> None:
        items = [(str(key), str(value)) for key, value in values.items() if str(key)]
        if not items:
            return
        conn = self._connect()
        with self._lock:
            conn.executemany(
                "INSERT INTO kv_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                items,
            )
            conn.commit()

    def get_state(self, key: str) -> str | None:
        conn = self._connect()
        with self._lock:
            row = conn.execute("SELECT value FROM kv_state WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row is not None else None

    def list_states(self, *, prefix: str = "", limit: int = 500) -> dict[str, str]:
        conn = self._connect()
        with self._lock:
            if str(prefix or "").strip():
                rows = conn.execute(
                    """
                    SELECT key, value
                    FROM kv_state
                    WHERE key LIKE ?
                    ORDER BY key ASC
                    LIMIT ?
                    """,
                    (f"{prefix}%", int(max(1, limit))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT key, value
                    FROM kv_state
                    ORDER BY key ASC
                    LIMIT ?
                    """,
                    (int(max(1, limit)),),
                ).fetchall()
        return {
            str(row["key"]): str(row["value"])
            for row in rows
        }


def _json_loads(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return default
