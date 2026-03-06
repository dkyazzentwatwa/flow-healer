from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .config import AppConfig, RelaySettings
from .service import FlowHealerService
from .store import SQLiteStore


@dataclass(slots=True)
class RuntimeSnapshot:
    status: str
    heartbeat_at: str
    last_tick_started_at: str
    last_tick_finished_at: str
    last_error: str
    freshness: str


@dataclass(slots=True)
class RepoFleetRow:
    repo: str
    path: str
    paused: bool
    runtime: RuntimeSnapshot
    issues_total: int
    state_counts: dict[str, int]
    active_locks: int
    last_scan_status: str
    last_scan_at: str
    last_event_at: str


@dataclass(slots=True)
class AuditEventRow:
    created_at: str
    event_type: str
    level: str
    message: str
    issue_id: str
    attempt_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IssueRow:
    issue_id: str
    title: str
    state: str
    priority: int
    author: str
    labels: list[str]
    updated_at: str
    branch_name: str
    workspace_path: str
    pr_number: int
    last_failure_class: str


@dataclass(slots=True)
class AttemptRow:
    attempt_id: str
    issue_id: str
    attempt_no: int
    state: str
    started_at: str
    finished_at: str
    prediction_source: str
    predicted_lock_set: list[str]
    actual_diff_set: list[str]
    failure_class: str
    failure_reason: str
    test_summary: dict[str, Any] = field(default_factory=dict)
    verifier_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScanRunRow:
    run_id: str
    status: str
    dry_run: bool
    created_at: str
    updated_at: str
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScanFindingRow:
    fingerprint: str
    scan_type: str
    severity: str
    title: str
    status: str
    issue_number: int
    last_seen_at: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RepoSnapshot:
    repo: RepoFleetRow
    recent_events: list[AuditEventRow]
    active_locks: list[dict[str, Any]]
    recent_findings: list[ScanFindingRow]
    recent_runs: list[ScanRunRow]
    recent_lessons: list[dict[str, Any]]


@dataclass(slots=True)
class IssueDetail:
    issue: IssueRow
    feedback_context: str
    body: str
    attempts: list[AttemptRow]
    events: list[AuditEventRow]
    lessons: list[dict[str, Any]]
    locks: list[dict[str, Any]]


class FlowHealerOperatorAPI:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.service = FlowHealerService(config)

    def fleet_rows(self) -> list[RepoFleetRow]:
        rows: list[RepoFleetRow] = []
        for repo in self.config.repos:
            with self._store(repo) as store:
                issues = store.list_healer_issues(limit=500)
                counts: dict[str, int] = {}
                for issue in issues:
                    state = str(issue.get("state") or "unknown")
                    counts[state] = counts.get(state, 0) + 1
                last_scan = store.list_scan_runs(limit=1)
                last_event = store.list_healer_events(limit=1)
                rows.append(
                    RepoFleetRow(
                        repo=repo.repo_name,
                        path=repo.healer_repo_path,
                        paused=store.get_state("healer_paused") == "true",
                        runtime=self._runtime_snapshot(store.get_runtime_status(), repo),
                        issues_total=len(issues),
                        state_counts=counts,
                        active_locks=len(store.list_healer_locks()),
                        last_scan_status=str((last_scan[0] if last_scan else {}).get("status") or ""),
                        last_scan_at=str((last_scan[0] if last_scan else {}).get("updated_at") or ""),
                        last_event_at=str((last_event[0] if last_event else {}).get("created_at") or ""),
                    )
                )
        return rows

    def repo_snapshot(self, repo_name: str) -> RepoSnapshot:
        repo = self._select_repo(repo_name)
        with self._store(repo) as store:
            fleet_row = next((row for row in self.fleet_rows() if row.repo == repo.repo_name), None)
            if fleet_row is None:
                fleet_row = RepoFleetRow(
                    repo=repo.repo_name,
                    path=repo.healer_repo_path,
                    paused=False,
                    runtime=self._runtime_snapshot(store.get_runtime_status(), repo),
                    issues_total=0,
                    state_counts={},
                    active_locks=0,
                    last_scan_status="",
                    last_scan_at="",
                    last_event_at="",
                )
            return RepoSnapshot(
                repo=fleet_row,
                recent_events=[self._event_row(item) for item in store.list_healer_events(limit=25)],
                active_locks=store.list_healer_locks(),
                recent_findings=[self._scan_finding_row(item) for item in store.list_scan_findings(limit=25)],
                recent_runs=[self._scan_run_row(item) for item in store.list_scan_runs(limit=10)],
                recent_lessons=store.list_healer_lessons(limit=15),
            )

    def list_issues(self, repo_name: str, *, states: list[str] | None = None, limit: int = 200) -> list[IssueRow]:
        repo = self._select_repo(repo_name)
        with self._store(repo) as store:
            return [self._issue_row(item) for item in store.list_healer_issues(states=states, limit=limit)]

    def issue_detail(self, repo_name: str, issue_id: str) -> IssueDetail | None:
        repo = self._select_repo(repo_name)
        with self._store(repo) as store:
            issue = store.get_healer_issue(issue_id)
            if issue is None:
                return None
            return IssueDetail(
                issue=self._issue_row(issue),
                feedback_context=str(issue.get("feedback_context") or ""),
                body=str(issue.get("body") or ""),
                attempts=[self._attempt_row(item) for item in store.list_healer_attempts(issue_id=issue_id, limit=25)],
                events=[self._event_row(item) for item in store.list_healer_events(issue_id=issue_id, limit=50)],
                lessons=store.list_healer_lessons_for_issue(issue_id=issue_id, limit=20),
                locks=store.list_healer_locks(issue_id=issue_id),
            )

    def recent_attempts(self, repo_name: str, *, limit: int = 100) -> list[AttemptRow]:
        repo = self._select_repo(repo_name)
        with self._store(repo) as store:
            return [self._attempt_row(item) for item in store.list_recent_healer_attempts(limit=limit)]

    def scan_runs(self, repo_name: str, *, limit: int = 50) -> list[ScanRunRow]:
        repo = self._select_repo(repo_name)
        with self._store(repo) as store:
            return [self._scan_run_row(item) for item in store.list_scan_runs(limit=limit)]

    def scan_findings(
        self,
        repo_name: str,
        *,
        statuses: list[str] | None = None,
        limit: int = 200,
    ) -> list[ScanFindingRow]:
        repo = self._select_repo(repo_name)
        with self._store(repo) as store:
            return [self._scan_finding_row(item) for item in store.list_scan_findings(statuses=statuses, limit=limit)]

    def audit_events(self, repo_name: str, *, limit: int = 200) -> list[AuditEventRow]:
        repo = self._select_repo(repo_name)
        with self._store(repo) as store:
            return [self._event_row(item) for item in store.list_healer_events(limit=limit)]

    def run_doctor(self, repo_name: str) -> dict[str, object]:
        rows = self.service.doctor_rows(repo_name)
        return rows[0] if rows else {}

    def pause_repo(self, repo_name: str) -> None:
        self.service.set_paused(True, repo_name)

    def resume_repo(self, repo_name: str) -> None:
        self.service.set_paused(False, repo_name)

    def run_scan(self, repo_name: str, *, dry_run: bool) -> dict[str, object]:
        rows = self.service.run_scan(repo_name, dry_run=dry_run)
        return rows[0] if rows else {}

    def run_once(self, repo_name: str) -> None:
        self.service.start(repo_name, once=True)

    def _select_repo(self, repo_name: str) -> RelaySettings:
        repos = self.config.select_repos(repo_name)
        if not repos:
            raise ValueError(f"Unknown repo: {repo_name}")
        return repos[0]

    def _store(self, repo: RelaySettings) -> _StoreContext:
        return _StoreContext(self.config.repo_db_path(repo.repo_name))

    @staticmethod
    def _runtime_snapshot(data: dict[str, Any] | None, repo: RelaySettings) -> RuntimeSnapshot:
        raw = data or {}
        heartbeat_at = str(raw.get("heartbeat_at") or "")
        freshness = "unknown"
        heartbeat = _parse_sqlite_ts(heartbeat_at)
        if heartbeat is not None:
            delta = datetime.now(UTC) - heartbeat
            freshness = "stale" if delta > timedelta(seconds=max(90.0, repo.healer_poll_interval_seconds * 2.5)) else "fresh"
        return RuntimeSnapshot(
            status=str(raw.get("status") or "idle"),
            heartbeat_at=heartbeat_at,
            last_tick_started_at=str(raw.get("last_tick_started_at") or ""),
            last_tick_finished_at=str(raw.get("last_tick_finished_at") or ""),
            last_error=str(raw.get("last_error") or ""),
            freshness=freshness,
        )

    @staticmethod
    def _event_row(item: dict[str, Any]) -> AuditEventRow:
        return AuditEventRow(
            created_at=str(item.get("created_at") or ""),
            event_type=str(item.get("event_type") or ""),
            level=str(item.get("level") or "info"),
            message=str(item.get("message") or ""),
            issue_id=str(item.get("issue_id") or ""),
            attempt_id=str(item.get("attempt_id") or ""),
            payload=dict(item.get("payload") or {}),
        )

    @staticmethod
    def _issue_row(item: dict[str, Any]) -> IssueRow:
        return IssueRow(
            issue_id=str(item.get("issue_id") or ""),
            title=str(item.get("title") or ""),
            state=str(item.get("state") or ""),
            priority=int(item.get("priority") or 0),
            author=str(item.get("author") or ""),
            labels=list(item.get("labels") or []),
            updated_at=str(item.get("updated_at") or ""),
            branch_name=str(item.get("branch_name") or ""),
            workspace_path=str(item.get("workspace_path") or ""),
            pr_number=int(item.get("pr_number") or 0),
            last_failure_class=str(item.get("last_failure_class") or ""),
        )

    @staticmethod
    def _attempt_row(item: dict[str, Any]) -> AttemptRow:
        return AttemptRow(
            attempt_id=str(item.get("attempt_id") or ""),
            issue_id=str(item.get("issue_id") or ""),
            attempt_no=int(item.get("attempt_no") or 0),
            state=str(item.get("state") or ""),
            started_at=str(item.get("started_at") or ""),
            finished_at=str(item.get("finished_at") or ""),
            prediction_source=str(item.get("prediction_source") or ""),
            predicted_lock_set=list(item.get("predicted_lock_set") or []),
            actual_diff_set=list(item.get("actual_diff_set") or []),
            failure_class=str(item.get("failure_class") or ""),
            failure_reason=str(item.get("failure_reason") or ""),
            test_summary=dict(item.get("test_summary") or {}),
            verifier_summary=dict(item.get("verifier_summary") or {}),
        )

    @staticmethod
    def _scan_run_row(item: dict[str, Any]) -> ScanRunRow:
        return ScanRunRow(
            run_id=str(item.get("run_id") or ""),
            status=str(item.get("status") or ""),
            dry_run=bool(item.get("dry_run")),
            created_at=str(item.get("created_at") or ""),
            updated_at=str(item.get("updated_at") or ""),
            summary=dict(item.get("summary") or {}),
        )

    @staticmethod
    def _scan_finding_row(item: dict[str, Any]) -> ScanFindingRow:
        return ScanFindingRow(
            fingerprint=str(item.get("fingerprint") or ""),
            scan_type=str(item.get("scan_type") or ""),
            severity=str(item.get("severity") or ""),
            title=str(item.get("title") or ""),
            status=str(item.get("status") or ""),
            issue_number=int(item.get("issue_number") or 0),
            last_seen_at=str(item.get("last_seen_at") or ""),
            payload=dict(item.get("payload") or {}),
        )


class _StoreContext:
    def __init__(self, db_path: Any) -> None:
        self._store = SQLiteStore(db_path)

    def __enter__(self) -> SQLiteStore:
        self._store.bootstrap()
        return self._store

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._store.close()


def _parse_sqlite_ts(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for candidate in (raw.replace(" ", "T"), raw):
        try:
            return datetime.fromisoformat(candidate).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None
