from __future__ import annotations

import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static, TabbedContent, TabPane

from ..config import AppConfig
from ..operator_api import AttemptRow, FlowHealerOperatorAPI, IssueDetail, RepoFleetRow, RepoSnapshot, ScanFindingRow, ScanRunRow
from .state import TUIState, WorkspaceId


def _fmt_ts(value: str) -> str:
    return str(value or "").replace("T", " ")


def _fmt_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}:{value}" for key, value in sorted(counts.items()))


class FlowHealerTUI(App[None]):
    CSS_PATH = "theme.tcss"
    TITLE = "Flow Healer"
    SUB_TITLE = "Operator Console"

    BINDINGS = [
        Binding("1", "switch_workspace('fleet')", "Fleet"),
        Binding("2", "switch_workspace('repo')", "Repo"),
        Binding("3", "switch_workspace('issues')", "Issues"),
        Binding("4", "switch_workspace('attempts')", "Attempts"),
        Binding("5", "switch_workspace('scans')", "Scans"),
        Binding("6", "switch_workspace('audit')", "Audit"),
        Binding("r", "refresh_active", "Refresh"),
        Binding("g", "command_palette", "Command"),
        Binding("escape", "hide_command", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, config: AppConfig, selected_repo: str | None = None) -> None:
        super().__init__()
        self.operator = FlowHealerOperatorAPI(config)
        self.state = TUIState(selected_repo=selected_repo or "")
        self._refresh_in_flight = False
        self._fleet_rows: list[RepoFleetRow] = []
        self._issue_rows: list[Any] = []
        self._attempt_rows: list[AttemptRow] = []
        self._scan_runs: list[ScanRunRow] = []
        self._scan_findings: list[ScanFindingRow] = []
        self._doctor_cache: dict[str, dict[str, object]] = {}
        self._repo_snapshot: RepoSnapshot | None = None
        self._issue_detail: IssueDetail | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Loading Flow Healer operator console...", id="status-bar")
        yield Input(placeholder="Command (repo demo | pause | resume | doctor | scan | scan-dry | once | refresh | tab issues)", id="command-input")

        with TabbedContent(initial=WorkspaceId.FLEET.value, id="workspace-tabs"):
            with TabPane("Fleet", id=WorkspaceId.FLEET.value):
                with VerticalScroll():
                    with Horizontal(classes="toolbar"):
                        yield Button("Refresh", id="btn-refresh-fleet", variant="primary")
                        yield Button("Pause", id="btn-pause")
                        yield Button("Resume", id="btn-resume")
                        yield Button("Run Once", id="btn-once")
                        yield Button("Scan", id="btn-scan")
                        yield Button("Dry Scan", id="btn-scan-dry")
                        yield Button("Doctor", id="btn-doctor")
                    yield Static("", id="fleet-summary", classes="panel hero")
                    yield DataTable(id="fleet-repos")

            with TabPane("Repo", id=WorkspaceId.REPO.value):
                with VerticalScroll():
                    with Horizontal(classes="toolbar"):
                        yield Label("Selected Repo", classes="toolbar-label")
                        yield Static("", id="repo-selected-badge", classes="badge")
                    yield Static("No repo selected.", id="repo-summary", classes="panel")
                    yield Static("Doctor has not been run from the TUI yet.", id="repo-doctor", classes="panel")
                    yield Label("Active Locks", classes="section-title")
                    yield DataTable(id="repo-locks")
                    yield Label("Recent Lessons", classes="section-title")
                    yield DataTable(id="repo-lessons")

            with TabPane("Issues", id=WorkspaceId.ISSUES.value):
                with VerticalScroll():
                    with Horizontal(classes="toolbar"):
                        yield Label("State Filter", classes="toolbar-label")
                        yield Input("", id="issues-filter", placeholder="queued|failed|pr_open")
                        yield Button("Apply", id="btn-apply-issues-filter", variant="primary")
                    yield DataTable(id="issues-table")
                    yield Static("Select an issue to inspect details.", id="issues-detail", classes="panel")

            with TabPane("Attempts", id=WorkspaceId.ATTEMPTS.value):
                with VerticalScroll():
                    yield DataTable(id="attempts-table")
                    yield Static("Select an attempt to inspect details.", id="attempts-detail", classes="panel")

            with TabPane("Scans", id=WorkspaceId.SCANS.value):
                with VerticalScroll():
                    yield Label("Recent Runs", classes="section-title")
                    yield DataTable(id="scan-runs-table")
                    yield Static("Select a scan run or finding for more detail.", id="scans-detail", classes="panel")
                    yield Label("Findings", classes="section-title")
                    yield DataTable(id="scan-findings-table")

            with TabPane("Audit", id=WorkspaceId.AUDIT.value):
                with VerticalScroll():
                    yield Label("Event Timeline", classes="section-title")
                    yield DataTable(id="audit-events-table")
                    yield Label("Issue Lessons", classes="section-title")
                    yield DataTable(id="audit-lessons-table")

        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#command-input", Input).add_class("hidden")
        self._configure_tables()
        self.set_interval(2.0, self._tick_refresh)
        self.run_worker(self.refresh_workspace(self._active_workspace(), force=True), group="startup", exclusive=True)

    def _configure_tables(self) -> None:
        self._setup_table("fleet-repos", ["Repo", "Runtime", "Fresh", "Paused", "Issues", "States", "Locks", "Last Scan", "Last Event"])
        self._setup_table("repo-locks", ["Lock", "Granularity", "Issue", "Lease Owner", "Expires"])
        self._setup_table("repo-lessons", ["Issue", "Kind", "Scope", "Outcome", "Confidence"])
        self._setup_table("issues-table", ["Issue", "State", "Priority", "Author", "Labels", "Branch", "PR", "Updated"])
        self._setup_table("attempts-table", ["Attempt", "Issue", "No", "State", "Started", "Finished", "Prediction", "Failure"])
        self._setup_table("scan-runs-table", ["Run", "Status", "Dry", "Findings", "Created", "Updated"])
        self._setup_table("scan-findings-table", ["Severity", "Type", "Status", "Issue", "Title", "Last Seen"])
        self._setup_table("audit-events-table", ["Time", "Level", "Type", "Issue", "Attempt", "Message"])
        self._setup_table("audit-lessons-table", ["Issue", "Kind", "Scope", "Outcome", "Confidence", "Summary"])

    def _setup_table(self, table_id: str, columns: list[str]) -> None:
        table = self.query_one(f"#{table_id}", DataTable)
        if table.columns:
            return
        for column in columns:
            table.add_column(column)

    def _fill_table(self, table_id: str, rows: list[tuple[Any, ...]]) -> None:
        table = self.query_one(f"#{table_id}", DataTable)
        table.clear(columns=False)
        for row in rows:
            table.add_row(*[str(value) for value in row])

    def _active_workspace(self) -> str:
        return self.query_one("#workspace-tabs", TabbedContent).active

    def _selected_repo(self) -> str:
        if self.state.selected_repo:
            return self.state.selected_repo
        if self._fleet_rows:
            self.state.selected_repo = self._fleet_rows[0].repo
            return self.state.selected_repo
        return ""

    def _tick_refresh(self) -> None:
        if self._refresh_in_flight:
            return
        self.run_worker(self.refresh_workspace(self._active_workspace()), group="active-refresh", exclusive=True)

    def action_switch_workspace(self, workspace: str) -> None:
        self.query_one("#workspace-tabs", TabbedContent).active = workspace
        self.run_worker(self.refresh_workspace(workspace, force=True), group=f"switch-{workspace}", exclusive=True)

    def action_refresh_active(self) -> None:
        self.run_worker(self.refresh_workspace(self._active_workspace(), force=True), group="manual-refresh", exclusive=True)

    def action_command_palette(self) -> None:
        command = self.query_one("#command-input", Input)
        command.remove_class("hidden")
        command.focus()

    def action_hide_command(self) -> None:
        command = self.query_one("#command-input", Input)
        command.add_class("hidden")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "command-input":
            return
        raw = event.value.strip()
        event.input.value = ""
        self.action_hide_command()
        if not raw:
            return
        parts = raw.split()
        command = parts[0].lower()
        if command == "repo" and len(parts) > 1:
            self.state.selected_repo = parts[1]
            await self.refresh_workspace(self._active_workspace(), force=True)
            return
        if command == "pause":
            await self._run_action("Paused selected repo.", self.operator.pause_repo)
            return
        if command == "resume":
            await self._run_action("Resumed selected repo.", self.operator.resume_repo)
            return
        if command == "doctor":
            await self._run_doctor()
            return
        if command == "scan":
            await self._run_scan(False)
            return
        if command == "scan-dry":
            await self._run_scan(True)
            return
        if command == "once":
            await self._run_action("Ran one healer cycle.", self.operator.run_once)
            return
        if command == "refresh":
            await self.refresh_workspace(self._active_workspace(), force=True)
            return
        if command == "tab" and len(parts) > 1:
            self.action_switch_workspace(parts[1].lower())
            return
        if command == "filter" and len(parts) > 2 and parts[1].lower() == "state":
            self.state.issue_state_filter = parts[2]
            await self.refresh_issues(force=True)
            return
        self._set_status(f"Unknown command: {raw}", error=True)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "btn-refresh-fleet":
            await self.refresh_fleet(force=True)
        elif button_id == "btn-pause":
            await self._run_action("Paused selected repo.", self.operator.pause_repo)
        elif button_id == "btn-resume":
            await self._run_action("Resumed selected repo.", self.operator.resume_repo)
        elif button_id == "btn-once":
            await self._run_action("Ran one healer cycle.", self.operator.run_once)
        elif button_id == "btn-scan":
            await self._run_scan(False)
        elif button_id == "btn-scan-dry":
            await self._run_scan(True)
        elif button_id == "btn-doctor":
            await self._run_doctor()
        elif button_id == "btn-apply-issues-filter":
            self.state.issue_state_filter = self.query_one("#issues-filter", Input).value.strip()
            await self.refresh_issues(force=True)

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table_id = event.data_table.id or ""
        row_index = event.cursor_row
        if row_index < 0:
            return
        if table_id == "fleet-repos" and row_index < len(self._fleet_rows):
            self.state.selected_repo = self._fleet_rows[row_index].repo
            self._set_status(f"Selected repo {self.state.selected_repo}")
            if self._active_workspace() != WorkspaceId.FLEET.value:
                await self.refresh_workspace(self._active_workspace(), force=True)
            else:
                await self.refresh_repo(force=True)
        elif table_id == "issues-table" and row_index < len(self._issue_rows):
            self.state.selected_issue_id = self._issue_rows[row_index].issue_id
            await self._refresh_issue_detail()
        elif table_id == "attempts-table" and row_index < len(self._attempt_rows):
            self.state.selected_attempt_id = self._attempt_rows[row_index].attempt_id
            self._render_attempt_detail(self._attempt_rows[row_index])
        elif table_id == "scan-runs-table" and row_index < len(self._scan_runs):
            self._render_scan_run_detail(self._scan_runs[row_index])
        elif table_id == "scan-findings-table" and row_index < len(self._scan_findings):
            self._render_scan_finding_detail(self._scan_findings[row_index])

    async def refresh_workspace(self, workspace: str, force: bool = False) -> None:
        if self._refresh_in_flight:
            return
        self._refresh_in_flight = True
        try:
            await self.refresh_fleet(force=force)
            if workspace == WorkspaceId.REPO.value:
                await self.refresh_repo(force=force)
            elif workspace == WorkspaceId.ISSUES.value:
                await self.refresh_issues(force=force)
            elif workspace == WorkspaceId.ATTEMPTS.value:
                await self.refresh_attempts(force=force)
            elif workspace == WorkspaceId.SCANS.value:
                await self.refresh_scans(force=force)
            elif workspace == WorkspaceId.AUDIT.value:
                await self.refresh_audit(force=force)
            if force:
                self._set_status(f"Refreshed {workspace}")
        finally:
            self._refresh_in_flight = False

    async def refresh_fleet(self, force: bool = False) -> None:
        self._fleet_rows = await asyncio.to_thread(self.operator.fleet_rows)
        if self._fleet_rows and not self.state.selected_repo:
            self.state.selected_repo = self._fleet_rows[0].repo
        rows = [
            (
                row.repo,
                row.runtime.status,
                row.runtime.freshness,
                "yes" if row.paused else "no",
                row.issues_total,
                _fmt_counts(row.state_counts),
                row.active_locks,
                row.last_scan_status,
                _fmt_ts(row.last_event_at),
            )
            for row in self._fleet_rows
        ]
        self._fill_table("fleet-repos", rows)
        selected = self._selected_repo() or "none"
        summary = (
            f"Managed repos: {len(self._fleet_rows)}\n"
            f"Selected repo: {selected}\n"
            f"Controls: pause, resume, run once, scan, dry scan, doctor"
        )
        self.query_one("#fleet-summary", Static).update(summary)
        if force and self._active_workspace() != WorkspaceId.FLEET.value:
            await self.refresh_repo(force=False)

    async def refresh_repo(self, force: bool = False) -> None:
        repo_name = self._selected_repo()
        if not repo_name:
            return
        self._repo_snapshot = await asyncio.to_thread(self.operator.repo_snapshot, repo_name)
        repo = self._repo_snapshot.repo
        self.query_one("#repo-selected-badge", Static).update(repo_name)
        summary = (
            f"Repo: {repo.repo}\n"
            f"Path: {repo.path}\n"
            f"Runtime: {repo.runtime.status} ({repo.runtime.freshness})\n"
            f"Heartbeat: {_fmt_ts(repo.runtime.heartbeat_at)}\n"
            f"Paused: {'yes' if repo.paused else 'no'}\n"
            f"Issues: {repo.issues_total}\n"
            f"States: {_fmt_counts(repo.state_counts)}\n"
            f"Last scan: {repo.last_scan_status or 'none'} at {_fmt_ts(repo.last_scan_at)}\n"
            f"Last event: {_fmt_ts(repo.last_event_at)}\n"
            f"Last error: {repo.runtime.last_error or 'none'}"
        )
        self.query_one("#repo-summary", Static).update(summary)
        doctor = self._doctor_cache.get(repo_name)
        if doctor:
            self.query_one("#repo-doctor", Static).update(
                "\n".join(f"{key}: {value}" for key, value in doctor.items())
            )
        locks_rows = [
            (
                item.get("lock_key", ""),
                item.get("granularity", ""),
                item.get("issue_id", ""),
                item.get("lease_owner", ""),
                _fmt_ts(str(item.get("lease_expires_at") or "")),
            )
            for item in self._repo_snapshot.active_locks
        ]
        lesson_rows = [
            (
                item.get("issue_id", ""),
                item.get("lesson_kind", ""),
                item.get("scope_key", ""),
                item.get("outcome", ""),
                item.get("confidence", ""),
            )
            for item in self._repo_snapshot.recent_lessons
        ]
        self._fill_table("repo-locks", locks_rows)
        self._fill_table("repo-lessons", lesson_rows)

    async def refresh_issues(self, force: bool = False) -> None:
        repo_name = self._selected_repo()
        if not repo_name:
            return
        states = [self.state.issue_state_filter] if self.state.issue_state_filter else None
        self._issue_rows = await asyncio.to_thread(self.operator.list_issues, repo_name, states=states, limit=200)
        rows = [
            (
                item.issue_id,
                item.state,
                item.priority,
                item.author,
                ", ".join(item.labels),
                item.branch_name,
                item.pr_number or "",
                _fmt_ts(item.updated_at),
            )
            for item in self._issue_rows
        ]
        self._fill_table("issues-table", rows)
        if self._issue_rows:
            if not self.state.selected_issue_id:
                self.state.selected_issue_id = self._issue_rows[0].issue_id
            await self._refresh_issue_detail()
        else:
            self.query_one("#issues-detail", Static).update("No issues matched the current filter.")

    async def _refresh_issue_detail(self) -> None:
        repo_name = self._selected_repo()
        if not repo_name or not self.state.selected_issue_id:
            return
        self._issue_detail = await asyncio.to_thread(self.operator.issue_detail, repo_name, self.state.selected_issue_id)
        if self._issue_detail is None:
            self.query_one("#issues-detail", Static).update("Issue detail not found.")
            return
        issue = self._issue_detail.issue
        detail = (
            f"Issue #{issue.issue_id}: {issue.title}\n"
            f"State: {issue.state}  Priority: {issue.priority}  Author: {issue.author}\n"
            f"Labels: {', '.join(issue.labels) or 'none'}\n"
            f"Branch: {issue.branch_name or 'n/a'}\n"
            f"Workspace: {issue.workspace_path or 'n/a'}\n"
            f"PR: {issue.pr_number or 'n/a'}\n"
            f"Last failure: {issue.last_failure_class or 'none'}\n"
            f"Feedback:\n{self._issue_detail.feedback_context or 'none'}\n\n"
            f"Body:\n{self._issue_detail.body or 'none'}"
        )
        self.query_one("#issues-detail", Static).update(detail)

    async def refresh_attempts(self, force: bool = False) -> None:
        repo_name = self._selected_repo()
        if not repo_name:
            return
        self._attempt_rows = await asyncio.to_thread(self.operator.recent_attempts, repo_name, limit=100)
        rows = [
            (
                item.attempt_id,
                item.issue_id,
                item.attempt_no,
                item.state,
                _fmt_ts(item.started_at),
                _fmt_ts(item.finished_at),
                item.prediction_source,
                item.failure_class,
            )
            for item in self._attempt_rows
        ]
        self._fill_table("attempts-table", rows)
        if self._attempt_rows:
            if not self.state.selected_attempt_id:
                self.state.selected_attempt_id = self._attempt_rows[0].attempt_id
            selected = next((item for item in self._attempt_rows if item.attempt_id == self.state.selected_attempt_id), self._attempt_rows[0])
            self._render_attempt_detail(selected)
        else:
            self.query_one("#attempts-detail", Static).update("No attempts recorded yet.")

    def _render_attempt_detail(self, attempt: AttemptRow) -> None:
        detail = (
            f"Attempt {attempt.attempt_no} ({attempt.attempt_id})\n"
            f"Issue: {attempt.issue_id}\n"
            f"State: {attempt.state}\n"
            f"Started: {_fmt_ts(attempt.started_at)}\n"
            f"Finished: {_fmt_ts(attempt.finished_at)}\n"
            f"Prediction source: {attempt.prediction_source}\n"
            f"Predicted locks: {', '.join(attempt.predicted_lock_set) or 'none'}\n"
            f"Actual diff: {', '.join(attempt.actual_diff_set) or 'none'}\n"
            f"Failure: {attempt.failure_class or 'none'}\n"
            f"Reason: {attempt.failure_reason or 'none'}\n"
            f"Tests: {attempt.test_summary}\n"
            f"Verifier: {attempt.verifier_summary}"
        )
        self.query_one("#attempts-detail", Static).update(detail)

    async def refresh_scans(self, force: bool = False) -> None:
        repo_name = self._selected_repo()
        if not repo_name:
            return
        self._scan_runs = await asyncio.to_thread(self.operator.scan_runs, repo_name, limit=25)
        self._scan_findings = await asyncio.to_thread(self.operator.scan_findings, repo_name, limit=100)
        run_rows = [
            (
                item.run_id,
                item.status,
                "yes" if item.dry_run else "no",
                item.summary.get("findings_over_threshold", ""),
                _fmt_ts(item.created_at),
                _fmt_ts(item.updated_at),
            )
            for item in self._scan_runs
        ]
        finding_rows = [
            (
                item.severity,
                item.scan_type,
                item.status,
                item.issue_number or "",
                item.title,
                _fmt_ts(item.last_seen_at),
            )
            for item in self._scan_findings
        ]
        self._fill_table("scan-runs-table", run_rows)
        self._fill_table("scan-findings-table", finding_rows)
        if self._scan_runs:
            self._render_scan_run_detail(self._scan_runs[0])
        elif self._scan_findings:
            self._render_scan_finding_detail(self._scan_findings[0])
        else:
            self.query_one("#scans-detail", Static).update("No scan history recorded yet.")

    def _render_scan_run_detail(self, item: ScanRunRow) -> None:
        detail = (
            f"Run: {item.run_id}\n"
            f"Status: {item.status}\n"
            f"Dry run: {'yes' if item.dry_run else 'no'}\n"
            f"Created: {_fmt_ts(item.created_at)}\n"
            f"Updated: {_fmt_ts(item.updated_at)}\n"
            f"Summary: {item.summary}"
        )
        self.query_one("#scans-detail", Static).update(detail)

    def _render_scan_finding_detail(self, item: ScanFindingRow) -> None:
        detail = (
            f"Finding: {item.title}\n"
            f"Severity: {item.severity}\n"
            f"Type: {item.scan_type}\n"
            f"Status: {item.status}\n"
            f"Issue: {item.issue_number or 'n/a'}\n"
            f"Last seen: {_fmt_ts(item.last_seen_at)}\n"
            f"Payload: {item.payload}"
        )
        self.query_one("#scans-detail", Static).update(detail)

    async def refresh_audit(self, force: bool = False) -> None:
        repo_name = self._selected_repo()
        if not repo_name:
            return
        snapshot = self._repo_snapshot or await asyncio.to_thread(self.operator.repo_snapshot, repo_name)
        events = snapshot.recent_events
        lessons = snapshot.recent_lessons
        event_rows = [
            (
                _fmt_ts(item.created_at),
                item.level,
                item.event_type,
                item.issue_id,
                item.attempt_id,
                item.message,
            )
            for item in events
        ]
        lesson_rows = [
            (
                item.get("issue_id", ""),
                item.get("lesson_kind", ""),
                item.get("scope_key", ""),
                item.get("outcome", ""),
                item.get("confidence", ""),
                item.get("problem_summary", ""),
            )
            for item in lessons
        ]
        self._fill_table("audit-events-table", event_rows)
        self._fill_table("audit-lessons-table", lesson_rows)

    async def _run_action(self, success_message: str, handler: Any) -> None:
        repo_name = self._selected_repo()
        if not repo_name:
            self._set_status("No repo selected.", error=True)
            return
        await asyncio.to_thread(handler, repo_name)
        self._set_status(success_message)
        await self.refresh_workspace(self._active_workspace(), force=True)

    async def _run_scan(self, dry_run: bool) -> None:
        repo_name = self._selected_repo()
        if not repo_name:
            self._set_status("No repo selected.", error=True)
            return
        result = await asyncio.to_thread(self.operator.run_scan, repo_name, dry_run=dry_run)
        summary = result.get("summary") if isinstance(result, dict) else {}
        self._set_status(
            f"Scan finished for {repo_name}: {summary.get('findings_over_threshold', 0)} findings over threshold."
        )
        await self.refresh_workspace(self._active_workspace(), force=True)

    async def _run_doctor(self) -> None:
        repo_name = self._selected_repo()
        if not repo_name:
            self._set_status("No repo selected.", error=True)
            return
        self._doctor_cache[repo_name] = await asyncio.to_thread(self.operator.run_doctor, repo_name)
        self._set_status(f"Doctor completed for {repo_name}.")
        await self.refresh_repo(force=True)

    def _set_status(self, message: str, *, error: bool = False) -> None:
        prefix = "ERROR" if error else "OK"
        self.query_one("#status-bar", Static).update(f"[{prefix}] {message}")


def run_tui(config: AppConfig, selected_repo: str | None = None) -> None:
    app = FlowHealerTUI(config=config, selected_repo=selected_repo)
    app.run()
