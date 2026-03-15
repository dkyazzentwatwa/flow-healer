from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    LoadingIndicator,
    Select,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)
from textual import work

from .config import AppConfig
from .healer_runner import _operator_failure_reason
from .service import FlowHealerService
from .store import SQLiteStore
from .telemetry_exports import collect_telemetry_datasets, default_export_dir, write_telemetry_exports

# ---------------------------------------------------------------------------
# Theme list (only built-in Textual themes)
# ---------------------------------------------------------------------------

FLOW_HEALER_THEMES = [
    "textual-dark",
    "nord",
    "gruvbox",
    "tokyo-night",
    "dracula",
    "monokai",
    "textual-light",
]

# ---------------------------------------------------------------------------
# State colours
# ---------------------------------------------------------------------------

STATE_COLORS: dict[str, str] = {
    "queued": "blue",
    "running": "yellow",
    "claimed": "yellow",
    "verify_pending": "yellow",
    "failed": "red",
    "error": "red",
    "blocked": "red",
    "merged": "green",
    "closed": "green",
    "pr_open": "green",
}


def _colored_state(state: str) -> Text:
    color = STATE_COLORS.get(state.lower(), "white")
    return Text(state, style=color)


# ---------------------------------------------------------------------------
# Tab IDs (MVP review-queue-first layout)
# ---------------------------------------------------------------------------

TAB_REVIEW_QUEUE = "tab-review-queue"
TAB_BLOCKED = "tab-blocked"
TAB_REPO_HEALTH = "tab-repo-health"
TAB_HISTORY = "tab-history"


# ---------------------------------------------------------------------------
# TUI preferences (persisted across sessions)
# ---------------------------------------------------------------------------


@dataclass
class TuiPrefs:
    theme: str = "textual-dark"
    refresh_seconds: int = 5
    show_sparkline: bool = True


def load_tui_prefs(config: AppConfig) -> TuiPrefs:
    path = _prefs_path(config)
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return TuiPrefs(
                theme=raw.get("theme", TuiPrefs.theme),
                refresh_seconds=int(raw.get("refresh_seconds", TuiPrefs.refresh_seconds)),
                show_sparkline=bool(raw.get("show_sparkline", TuiPrefs.show_sparkline)),
            )
        except Exception:
            pass
    return TuiPrefs()


def save_tui_prefs(config: AppConfig, prefs: TuiPrefs) -> None:
    path = _prefs_path(config)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(prefs), indent=2), encoding="utf-8")
    tmp.replace(path)


def _prefs_path(config: AppConfig) -> Path:
    return config.state_root_path() / "tui_prefs.json"


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def build_tui_snapshot(*, service: FlowHealerService, repo_name: str | None) -> dict[str, Any]:
    datasets = collect_telemetry_datasets(service=service, repo_name=repo_name)
    return {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "status_rows": datasets["summary_metrics"],
        "queue_rows": datasets["issues"][:12],
        "attempt_rows": datasets["attempts"][:12],
        "event_rows": datasets["events"][:12],
        "log_lines": _recent_log_lines(service.config, limit=12),
    }


def render_tui_text(snapshot: dict[str, Any]) -> str:
    lines = [
        "Flow Healer TUI",
        f"Generated: {snapshot.get('generated_at', '')}",
        "",
        "Status",
    ]
    status_rows = snapshot.get("status_rows") or []
    if not status_rows:
        lines.append("  No status rows.")
    else:
        for row in status_rows:
            trust = row.get("trust") or {}
            counts = row.get("state_counts") or {}
            lines.append(
                f"  {row.get('repo_name', row.get('repo', ''))}: "
                f"{trust.get('state', 'unknown')} | {trust.get('summary', '')}"
            )
            if counts:
                lines.append(f"    queue={_format_key_values(counts)}")
                lines.append(f"    chart={_sparkline_from_counts(counts)}")

    lines.extend(["", "Queue"])
    queue_rows = snapshot.get("queue_rows") or []
    if not queue_rows:
        lines.append("  No queued issues.")
    else:
        for row in queue_rows:
            lines.append(f"  #{row.get('issue_id', '')} [{row.get('state', '')}] {row.get('title', '')}")

    lines.extend(["", "Recent Attempts"])
    attempt_rows = snapshot.get("attempt_rows") or []
    if not attempt_rows:
        lines.append("  No attempts.")
    else:
        for row in attempt_rows:
            summary = row.get("failure_class") or row.get("state") or ""
            lines.append(f"  {row.get('attempt_id', '')} issue={row.get('issue_id', '')} {summary}")

    lines.extend(["", "Recent Events"])
    event_rows = snapshot.get("event_rows") or []
    if not event_rows:
        lines.append("  No events.")
    else:
        for row in event_rows:
            lines.append(
                f"  {row.get('created_at', '')} {row.get('event_type', '')}: {row.get('message', '')}"
            )

    lines.extend(["", "Recent Logs"])
    log_lines = snapshot.get("log_lines") or []
    if not log_lines:
        lines.append("  No logs.")
    else:
        lines.extend(f"  {line}" for line in log_lines)

    lines.extend(["", "Controls", "  q quit    r refresh"])
    return "\n".join(lines)


def tui_queue_summary(row: dict[str, Any], *, width: int) -> str:
    issue_id = row.get("issue_id", "?")
    state = row.get("state", "unknown")
    title = str(row.get("title", "")).strip()
    return _truncate_line(f"#{issue_id} {state} {title}", width)


def tui_detail_lines(item: Any, *, width: int) -> list[str]:
    width = max(12, width)
    if item is None:
        return ["No details available."]
    if isinstance(item, str):
        fields = [item]
    elif isinstance(item, dict):
        fields = [f"{key}: {value}" for key, value in item.items() if value not in (None, "", [], {})]
    else:
        fields = [str(item)]

    lines: list[str] = []
    for field_str in fields:
        wrapped = textwrap.wrap(str(field_str), width=width, replace_whitespace=False, drop_whitespace=False)
        lines.extend(wrapped or [""])
    return lines or ["No details available."]


def _format_attempt_row_for_display(row: dict[str, Any]) -> dict[str, Any]:
    """Map internal attempt row fields to operator-visible display values."""
    failure_class = str(row.get("failure_class") or "")
    return {
        **row,
        "operator_failure": _operator_failure_reason(failure_class),
    }


# ---------------------------------------------------------------------------
# Stats bar widget
# ---------------------------------------------------------------------------


class StatsBar(Static):
    """One-line live stats: counts + sparkline + last refreshed."""

    last_markup: str = ""

    def update_from_snapshot(self, snapshot: dict[str, Any], *, show_sparkline: bool = True) -> None:
        status_rows = snapshot.get("status_rows") or []
        if not status_rows:
            self.update("No data.")
            return

        row = status_rows[0]
        counts: dict[str, Any] = row.get("state_counts") or {}

        queued = counts.get("queued", 0)
        running = counts.get("running", 0) + counts.get("claimed", 0)
        failed = counts.get("failed", 0) + counts.get("error", 0)
        merged = counts.get("merged", 0) + counts.get("pr_open", 0)

        parts: list[str] = [
            f"[blue]◆ {queued} queued[/]",
            f"[yellow]▸ {running} running[/]",
            f"[red]✗ {failed} failed[/]",
            f"[green]✓ {merged} merged[/]",
        ]

        if show_sparkline and counts:
            spark = _sparkline_from_counts(counts)
            if spark:
                parts.append(f"[dim]{spark}[/]")

        generated = snapshot.get("generated_at", "")
        if generated:
            parts.append(f"[dim]refreshed {generated.split()[-1]}[/]")

        self.last_markup = "  ".join(parts)
        self.update(self.last_markup)


# ---------------------------------------------------------------------------
# Settings modal
# ---------------------------------------------------------------------------


class SettingsScreen(ModalScreen[TuiPrefs | None]):
    """Modal settings dialog."""

    CSS = """
    SettingsScreen {
        align: center middle;
    }
    #settings-dialog {
        width: 52;
        height: auto;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    #settings-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    .settings-row {
        height: auto;
        margin-bottom: 1;
        align: left middle;
    }
    .settings-label {
        width: 14;
    }
    #settings-buttons {
        margin-top: 1;
        align: right middle;
        height: auto;
    }
    #btn-save { margin-right: 1; }
    """

    def __init__(self, prefs: TuiPrefs) -> None:
        super().__init__()
        self._prefs = prefs
        self._original_theme = prefs.theme

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Label("⚙  Settings", id="settings-title")
            with Horizontal(classes="settings-row"):
                yield Label("Theme", classes="settings-label")
                yield Select(
                    [(t, t) for t in FLOW_HEALER_THEMES],
                    value=self._prefs.theme,
                    allow_blank=False,
                    id="theme-select",
                )
            with Horizontal(classes="settings-row"):
                yield Label("Refresh (s)", classes="settings-label")
                yield Input(
                    value=str(self._prefs.refresh_seconds),
                    type="integer",
                    id="refresh-input",
                )
            with Horizontal(classes="settings-row"):
                yield Label("Sparkline", classes="settings-label")
                yield Switch(value=self._prefs.show_sparkline, id="sparkline-switch")
            with Horizontal(id="settings-buttons"):
                yield Button("Save", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "theme-select" and event.value is not Select.BLANK:
            self.app.theme = str(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            theme_select = self.query_one("#theme-select", Select)
            refresh_input = self.query_one("#refresh-input", Input)
            sparkline_switch = self.query_one("#sparkline-switch", Switch)

            theme = str(theme_select.value) if theme_select.value is not Select.BLANK else self._prefs.theme
            try:
                refresh = max(1, int(refresh_input.value or "5"))
            except ValueError:
                refresh = self._prefs.refresh_seconds

            new_prefs = TuiPrefs(
                theme=theme,
                refresh_seconds=refresh,
                show_sparkline=sparkline_switch.value,
            )
            self.dismiss(new_prefs)
        else:
            # Cancel — revert theme preview
            self.app.theme = self._original_theme
            self.dismiss(None)


# ---------------------------------------------------------------------------
# Confirm modal
# ---------------------------------------------------------------------------


class ConfirmScreen(ModalScreen[bool]):
    """Generic yes/no confirmation modal."""

    CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-dialog {
        width: 50;
        height: auto;
        border: round $warning;
        background: $surface;
        padding: 1 2;
    }
    #confirm-message {
        margin-bottom: 1;
    }
    #confirm-buttons {
        align: right middle;
        height: auto;
    }
    #btn-confirm { margin-right: 1; }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(self._message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("Confirm", variant="warning", id="btn-confirm")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-confirm")


# ---------------------------------------------------------------------------
# Action bar widget
# ---------------------------------------------------------------------------


class ActionBar(Static):
    """Context-sensitive action hints shown below the queue table."""

    last_markup: str = ""

    def update_for_row(self, row: dict[str, Any] | None) -> None:
        if row is None:
            self.display = False
            self.last_markup = ""
            return
        self.display = True
        has_lock = bool(row.get("lease_owner"))
        has_pr = bool(int(row.get("pr_number") or 0) > 0)
        lock_str = "[ctrl+x] Clear lock" if has_lock else "[dim][ctrl+x] Clear lock[/]"
        pr_str = "[ctrl+p] Open PR" if has_pr else "[dim][ctrl+p] Open PR[/]"
        self.last_markup = f"[bold]Actions:[/]  [ctrl+r] Retry  {lock_str}  [ctrl+c] Copy ID  {pr_str}"
        self.update(self.last_markup)


# ---------------------------------------------------------------------------
# Detail panel helper
# ---------------------------------------------------------------------------


def _render_detail_table(item: dict[str, Any]) -> Table:
    t = Table(box=None, show_header=False, padding=(0, 1))
    t.add_column(style="bold", no_wrap=True)
    t.add_column()
    for key, value in item.items():
        if value not in (None, "", [], {}):
            cell = _colored_state(str(value)) if key == "state" else str(value)
            t.add_row(key, cell)
    return t


def _render_attempt_evidence(attempt: dict[str, Any]) -> str:
    """Structured evidence panel for a healer attempt row."""
    lines: list[str] = []

    attempt_id = attempt.get("attempt_id", "")
    state = str(attempt.get("state", ""))
    issue_id = attempt.get("issue_id", "")
    state_color = STATE_COLORS.get(state.lower(), "white")
    lines.append(f"[bold]Attempt {attempt_id}[/]  state: [{state_color}]{state}[/]   issue #{issue_id}")

    failure_class = str(attempt.get("failure_class") or "")
    failure_reason = str(attempt.get("failure_reason") or "")
    if failure_class or failure_reason:
        lines.append(f"  failure_class   {failure_class}")
        if failure_reason:
            lines.append(f"  failure_reason  {failure_reason}")
    lines.append("")

    test_summary = attempt.get("test_summary") or {}
    if isinstance(test_summary, str):
        try:
            test_summary = json.loads(test_summary)
        except Exception:
            test_summary = {}
    if test_summary and isinstance(test_summary, dict):
        lines.append("[bold]Test Summary[/]")
        passed = test_summary.get("passed", "")
        failed = test_summary.get("failed", "")
        errors = test_summary.get("errors", test_summary.get("error", ""))
        duration = test_summary.get("duration_seconds", test_summary.get("duration", ""))
        lines.append(f"  passed   {passed}    failed   {failed}    errors  {errors}")
        if duration:
            lines.append(f"  duration {duration}s")
        lines.append("")

    verifier_summary = attempt.get("verifier_summary") or {}
    if isinstance(verifier_summary, str):
        try:
            verifier_summary = json.loads(verifier_summary)
        except Exception:
            verifier_summary = {}
    if verifier_summary and isinstance(verifier_summary, dict):
        lines.append("[bold]Verifier[/]")
        outcome = verifier_summary.get("outcome", "")
        reason = verifier_summary.get("reason", "")
        lines.append(f"  outcome  {outcome}")
        if reason:
            lines.append(f"  reason   {reason}")
        lines.append("")

    diff_set = attempt.get("actual_diff_set") or []
    if isinstance(diff_set, str):
        try:
            diff_set = json.loads(diff_set)
        except Exception:
            diff_set = []
    if diff_set:
        lines.append("[bold]Files Touched[/]")
        for f in list(diff_set)[:10]:
            lines.append(f"  {f}")
        lines.append("")

    try:
        pr_number = int(attempt.get("pr_number") or 0)
    except (ValueError, TypeError):
        pr_number = 0
    if pr_number > 0:
        lines.append(f"[bold]PR[/]  #{pr_number}")
    else:
        lines.append("[bold]PR[/]  #0  (no PR opened)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Analytics widget
# ---------------------------------------------------------------------------


def _render_analytics(row: dict[str, Any]) -> str:
    """Build Rich markup string for the Analytics tab from a status row."""
    parts: list[str] = []

    # --- Section A: Reliability ---
    canary: dict[str, Any] = row.get("reliability_canary") or {}
    trends: dict[str, Any] = row.get("reliability_trends") or {}
    rollups: list[dict[str, Any]] = row.get("reliability_daily_rollups") or []

    # first_pass_success_rate is 0.0–1.0; convert to integer percentage
    success_rate = round(float(canary.get("first_pass_success_rate", 0.0)) * 100)
    # mean_time_to_valid_pr_minutes → convert to seconds for display
    avg_dur_s = float(canary.get("mean_time_to_valid_pr_minutes", 0.0)) * 60
    sample = canary.get("sample_size", 0)
    no_op_rate = round(float(canary.get("no_op_rate", 0.0)) * 100)

    rate_color = "green" if success_rate >= 80 else ("yellow" if success_rate >= 60 else "red")
    rate_pct = f"[{rate_color}]{success_rate}%[/]"

    # 7d sparkline from daily rollups (most recent 7)
    spark_blocks = " ▁▂▃▄▅▆▇█"
    spark = ""
    recent_rollups = rollups[:7]
    if recent_rollups:
        rates = [round(float(r.get("first_pass_success_rate", 0.0)) * 100) for r in reversed(recent_rollups)]
        peak = max(rates) if max(rates) > 0 else 1
        spark = "".join(
            spark_blocks[min(len(spark_blocks) - 1, round((v / peak) * (len(spark_blocks) - 1)))]
            for v in rates
        )

    # Delta vs previous 7d — trends["7d"]["current"] / ["previous"]
    trend_7d: dict[str, Any] = trends.get("7d") or {}
    curr7 = round(float((trend_7d.get("current") or {}).get("first_pass_success_rate", success_rate / 100)) * 100)
    prev7 = round(float((trend_7d.get("previous") or {}).get("first_pass_success_rate", curr7 / 100)) * 100)
    delta = curr7 - prev7
    delta_str = f"[green]+{delta}pp[/]" if delta > 0 else (f"[red]{delta}pp[/]" if delta < 0 else "[dim]±0pp[/]")

    parts.append("[bold]Reliability[/]")
    parts.append(f"  Success rate   {rate_pct}   7d trend {spark}")
    parts.append(f"  vs prev 7d     [dim]{prev7}%[/]   Δ {delta_str}   no-op {no_op_rate}%")
    dur_label = f"{avg_dur_s:.0f}s" if avg_dur_s >= 1 else "n/a"
    parts.append(f"  Avg to PR      {dur_label:<8}         Sample  {sample} attempts")
    parts.append("")

    # --- Section B: Failure Breakdown ---
    failure_domains: dict[str, Any] = row.get("failure_domain_metrics") or {}
    domain_keys = ["infra", "code", "contract", "unknown"]
    domain_counts = {k: int(failure_domains.get(k, 0)) for k in domain_keys}
    active_domains = {k: v for k, v in domain_counts.items() if v > 0}

    parts.append("[bold]Failure Breakdown[/]")
    if active_domains:
        max_count = max(active_domains.values())
        total_failures = sum(active_domains.values()) or 1
        for domain, count in sorted(active_domains.items(), key=lambda x: -x[1]):
            bar = _hbar(count, max_count, width=12)
            pct = round(count / total_failures * 100)
            parts.append(f"  {domain:<10} {bar}  {count:>3}  {pct}%")
    else:
        parts.append("  No failures recorded.")
    parts.append("")

    # --- Section C: Pipeline ---
    state_counts: dict[str, Any] = row.get("state_counts") or {}
    active_states = {k: int(v) for k, v in state_counts.items() if int(v or 0) > 0}

    parts.append("[bold]Pipeline[/]")
    if active_states:
        max_count = max(active_states.values())
        for state, count in sorted(active_states.items(), key=lambda x: -x[1]):
            bar = _hbar(count, max_count, width=15)
            parts.append(f"  {state:<14} {bar}  {count:>3}")
    else:
        parts.append("  No active pipeline states.")
    parts.append("")

    # --- Section D: System Health ---
    worker: dict[str, Any] = row.get("worker") or {}
    cb: dict[str, Any] = row.get("circuit_breaker") or {}
    resource: dict[str, Any] = row.get("resource_audit") or {}
    worktrees: dict[str, Any] = resource.get("worktrees") or {}
    locks: dict[str, Any] = resource.get("locks") or {}

    worker_active = bool(worker.get("active"))
    worker_label = "[green]ACTIVE[/]" if worker_active else "[red blink]IDLE[/]"
    uptime_s = int(worker.get("uptime_seconds") or 0)
    uptime_str = f"{uptime_s // 3600}h {(uptime_s % 3600) // 60}m" if uptime_s else "n/a"

    cb_open = bool(cb.get("open"))
    cb_cooldown = int(cb.get("cooldown_remaining_seconds") or 0)
    if cb_open:
        cooldown_min = cb_cooldown // 60
        cb_label = f"[red blink]OPEN ({cooldown_min}m cooldown)[/]"
    else:
        cb_label = "[green]CLOSED[/]"
    cb_rate = float(cb.get("failure_rate") or 0)

    wt_total = worktrees.get("total", 0)
    wt_orphaned = worktrees.get("orphaned", 0)
    lk_total = locks.get("total", 0)
    lk_expired = locks.get("expired", 0)

    parts.append("[bold]System Health[/]")
    parts.append(f"  Worker       {worker_label}    uptime {uptime_str}")
    parts.append(f"  Circuit      {cb_label}    failure rate {cb_rate:.0%}")
    wt_orphan_str = f"[red]{wt_orphaned} orphaned[/]" if wt_orphaned else f"{wt_orphaned} orphaned"
    lk_expired_str = f"[yellow]{lk_expired} expired[/]" if lk_expired else f"{lk_expired} expired"
    parts.append(f"  Worktrees    {wt_total} total, {wt_orphan_str}")
    parts.append(f"  Locks        {lk_total} active, {lk_expired_str}")
    parts.append("")

    # --- Section E: Daily Trend (7d) ---
    parts.append("[bold]Daily Trend (7d)[/]")
    if rollups:
        for entry in rollups[:7]:
            date = str(entry.get("day", ""))
            rate = round(float(entry.get("first_pass_success_rate", 0.0)) * 100)
            issue_count = int(entry.get("issue_count", 0))
            ok = round(issue_count * float(entry.get("first_pass_success_rate", 0.0)))
            fail = issue_count - ok
            bar = _hbar(rate, 100, width=10)
            r_color = "green" if rate >= 80 else ("yellow" if rate >= 60 else "red")
            parts.append(
                f"  {date}  {bar}  ok:{ok:>3}  fail:{fail:<3}  [{r_color}]{rate}%[/]"
            )
    else:
        parts.append("  No daily rollup data.")

    return "\n".join(parts)


class AnalyticsWidget(Static):
    """Rich analytics panel with reliability, failure, pipeline and health charts."""

    last_text: str = ""

    def update_from_snapshot(self, snapshot: dict[str, Any]) -> None:
        status_rows = snapshot.get("status_rows") or []
        if not status_rows:
            self.last_text = "No analytics data available."
            self.update(self.last_text)
            return
        self.last_text = _render_analytics(status_rows[0])
        self.update(self.last_text)


# ---------------------------------------------------------------------------
# Main TUI application
# ---------------------------------------------------------------------------


class FlowHealerApp(App[None]):
    """Textual TUI for Flow Healer."""

    CSS = """
    Screen { background: $surface; }

    #stats-bar {
        height: 1;
        background: $panel;
        padding: 0 2;
    }

    #main { height: 1fr; }
    #queue-panel {
        width: 35%;
        border: round $primary;
        margin-right: 1;
    }
    #inspector-panel {
        width: 65%;
        border: round $primary;
    }
    TabbedContent {
        height: 1fr;
    }
    #details {
        height: 10;
        border: round $accent;
        padding: 0 1;
        background: $panel;
    }
    DataTable { height: 1fr; }
    DataTable > .datatable--cursor { background: $accent-muted; }
    #analytics-widget {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }
    #refresh-loader {
        height: 1;
        display: none;
    }
    #refresh-loader.loading {
        display: block;
    }
    #action-bar {
        height: 1;
        background: $panel;
        padding: 0 1;
        display: none;
    }
    """

    BINDINGS = [
        Binding("r", "refresh_data", "Refresh"),
        Binding("e", "export_data", "Export"),
        Binding("t", "cycle_theme", "Theme"),
        Binding("s", "open_settings", "Settings"),
        Binding("a", "show_analytics", "Analytics"),
        Binding("q", "quit", "Quit"),
        Binding("ctrl+r", "retry_issue", "Retry", show=False),
        Binding("ctrl+x", "clear_lock", "Clear lock", show=False),
        Binding("ctrl+c", "copy_issue_id", "Copy ID", show=False),
        Binding("ctrl+p", "open_pr", "Open PR", show=False),
    ]

    def __init__(
        self,
        service: FlowHealerService,
        repo_name: str | None,
        prefs: TuiPrefs,
    ) -> None:
        super().__init__()
        self._service = service
        self._repo_name = repo_name
        self._prefs = prefs
        self._snapshot: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatsBar(id="stats-bar")
        yield LoadingIndicator(id="refresh-loader")
        with Horizontal(id="main"):
            with Vertical(id="queue-panel"):
                yield DataTable(id="queue-table", cursor_type="row")
                yield ActionBar(id="action-bar")
            with Vertical(id="inspector-panel"):
                with TabbedContent():
                    with TabPane("Attempts", id="tab-attempts"):
                        yield DataTable(id="attempts-table", cursor_type="row")
                    with TabPane("Events", id="tab-events"):
                        yield DataTable(id="events-table", cursor_type="row")
                    with TabPane("Logs", id="tab-logs"):
                        yield DataTable(id="logs-table", cursor_type="row")
                    with TabPane("Analytics", id="tab-analytics"):
                        yield AnalyticsWidget(id="analytics-widget")
                yield Static(id="details")
        yield Footer()

    def on_mount(self) -> None:
        self.theme = self._prefs.theme
        self._setup_tables()
        self.action_refresh_data()
        self.set_interval(self._prefs.refresh_seconds, self.action_refresh_data)
        self.set_interval(2, self._poll_events)

    def _setup_tables(self) -> None:
        queue_table = self.query_one("#queue-table", DataTable)
        queue_table.add_columns("#", "State", "Title")

        attempts_table = self.query_one("#attempts-table", DataTable)
        attempts_table.add_columns("Attempt ID", "Issue", "State", "Failure")

        events_table = self.query_one("#events-table", DataTable)
        events_table.add_columns("Time", "Level", "Type", "Message")

        logs_table = self.query_one("#logs-table", DataTable)
        logs_table.add_columns("Log Line")

        try:
            blocked_table = self.query_one("#blocked-table", DataTable)
            blocked_table.add_columns("#", "State", "Title", "Failure")
        except Exception:
            pass  # blocked-table may not exist in test environments

    def action_refresh_data(self) -> None:
        loader = self.query_one("#refresh-loader", LoadingIndicator)
        loader.add_class("loading")
        try:
            self._snapshot = build_tui_snapshot(service=self._service, repo_name=self._repo_name)
            self._populate_tables()
            self._update_details()
            self._update_stats_bar()
            self._update_analytics()
            status_rows = self._snapshot.get("status_rows") or []
            if status_rows:
                row = status_rows[0]
                trust = row.get("trust") or {}
                repo = row.get("repo_name", row.get("repo", ""))
                state = trust.get("state", "unknown")
                self.title = f"Flow Healer — {repo} [{state}]"
        finally:
            loader.remove_class("loading")

    def _populate_tables(self) -> None:
        queue_table = self.query_one("#queue-table", DataTable)
        queue_table.clear()
        for row in self._snapshot.get("queue_rows") or []:
            queue_table.add_row(
                str(row.get("issue_id", "")),
                _colored_state(str(row.get("state", ""))),
                _truncate_line(str(row.get("title", "")), 60),
            )

        attempts_table = self.query_one("#attempts-table", DataTable)
        attempts_table.clear()
        for row in self._snapshot.get("attempt_rows") or []:
            _display = _format_attempt_row_for_display(row)
            attempts_table.add_row(
                str(_display.get("attempt_id", "")),
                str(_display.get("issue_id", "")),
                _colored_state(str(_display.get("state", ""))),
                str(_display.get("operator_failure", "")),
            )

        events_table = self.query_one("#events-table", DataTable)
        events_table.clear()
        for row in self._snapshot.get("event_rows") or []:
            level = str(row.get("level", "info")).lower()
            level_color = {"error": "red", "warning": "yellow"}.get(level, "dim")
            events_table.add_row(
                str(row.get("created_at", "")),
                Text(level, style=level_color),
                str(row.get("event_type", "")),
                _truncate_line(str(row.get("message", "")), 60),
            )

        logs_table = self.query_one("#logs-table", DataTable)
        logs_table.clear()
        for line in self._snapshot.get("log_lines") or []:
            logs_table.add_row(str(line))

        try:
            blocked_table = self.query_one("#blocked-table", DataTable)
            blocked_table.clear()
            blocked_states = {"failed", "error", "blocked"}
            for row in self._snapshot.get("queue_rows") or []:
                if str(row.get("state", "")).lower() in blocked_states:
                    _display = _format_attempt_row_for_display(row)
                    blocked_table.add_row(
                        f"#{row.get('issue_id', '')}",
                        _colored_state(str(row.get("state", ""))),
                        str(row.get("title", "")),
                        str(_display.get("operator_failure", "")),
                    )
        except Exception:
            pass  # blocked-table may not exist in test environments

    def _update_details(self) -> None:
        details = self.query_one("#details", Static)
        queue_rows = self._snapshot.get("queue_rows") or []
        if not queue_rows:
            details.update("No issue selected.")
            return
        queue_table = self.query_one("#queue-table", DataTable)
        cursor_row = queue_table.cursor_row
        item = queue_rows[min(cursor_row, len(queue_rows) - 1)] if queue_rows else None
        if item is None:
            details.update("No issue selected.")
            return
        details.update(_render_detail_table(item))

    def _update_stats_bar(self) -> None:
        stats_bar = self.query_one("#stats-bar", StatsBar)
        stats_bar.update_from_snapshot(self._snapshot, show_sparkline=self._prefs.show_sparkline)

    def _update_analytics(self) -> None:
        widget = self.query_one("#analytics-widget", AnalyticsWidget)
        widget.update_from_snapshot(self._snapshot)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        details = self.query_one("#details", Static)
        table_id = event.data_table.id

        if table_id == "attempts-table":
            attempt_rows = self._snapshot.get("attempt_rows") or []
            cursor = event.data_table.cursor_row
            item = attempt_rows[min(cursor, len(attempt_rows) - 1)] if attempt_rows else None
            if item is None:
                details.update("No attempt selected.")
            else:
                details.update(_render_attempt_evidence(item))
        elif table_id == "queue-table":
            queue_rows = self._snapshot.get("queue_rows") or []
            cursor = event.data_table.cursor_row
            item = queue_rows[min(cursor, len(queue_rows) - 1)] if queue_rows else None
            if item is None:
                details.update("No issue selected.")
            else:
                details.update(_render_detail_table(item))
            action_bar = self.query_one("#action-bar", ActionBar)
            action_bar.update_for_row(item)
        else:
            self._update_details()

    def action_cycle_theme(self) -> None:
        current = self.theme
        try:
            idx = FLOW_HEALER_THEMES.index(current)
        except ValueError:
            idx = -1
        next_theme = FLOW_HEALER_THEMES[(idx + 1) % len(FLOW_HEALER_THEMES)]
        self.theme = next_theme
        self._prefs = TuiPrefs(
            theme=next_theme,
            refresh_seconds=self._prefs.refresh_seconds,
            show_sparkline=self._prefs.show_sparkline,
        )
        save_tui_prefs(self._service.config, self._prefs)
        self.notify(f"Theme: {next_theme}", title="Theme changed")

    def action_open_settings(self) -> None:
        def _on_dismiss(result: TuiPrefs | None) -> None:
            if result is not None:
                self._prefs = result
                self.theme = result.theme
                save_tui_prefs(self._service.config, result)
                self.notify("Settings saved.", title="Settings")

        self.push_screen(SettingsScreen(self._prefs), _on_dismiss)

    def action_show_analytics(self) -> None:
        tabbed = self.query_one(TabbedContent)
        tabbed.active = "tab-analytics"

    # ------------------------------------------------------------------
    # Store access helper
    # ------------------------------------------------------------------

    def _get_active_store(self) -> SQLiteStore | None:
        """Open a direct SQLiteStore for the active repo. Caller must close it."""
        try:
            repos = self._service.config.select_repos(self._repo_name)
            if not repos:
                return None
            repo = repos[0]
            store = SQLiteStore(self._service.config.repo_db_path(repo.repo_name))
            store.bootstrap()
            return store
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Live events poll (2s interval)
    # ------------------------------------------------------------------

    def _poll_events(self) -> None:
        store = self._get_active_store()
        if store is None:
            return
        try:
            events = store.list_healer_events(limit=40)
        finally:
            store.close()

        events_table = self.query_one("#events-table", DataTable)
        events_table.clear()
        for row in events:
            level = str(row.get("level", "info")).lower()
            level_color = {"error": "red", "warning": "yellow"}.get(level, "dim")
            msg = str(row.get("message", ""))
            payload = row.get("payload")
            if payload:
                if isinstance(payload, dict):
                    fc = payload.get("failure_class", "")
                    if fc:
                        msg = f"{msg} … {{{fc}}}"
                elif isinstance(payload, str) and payload.strip():
                    try:
                        pd = json.loads(payload)
                        fc = pd.get("failure_class", "") if isinstance(pd, dict) else ""
                        if fc:
                            msg = f"{msg} … {{{fc}}}"
                    except Exception:
                        pass
            events_table.add_row(
                str(row.get("created_at", "")),
                Text(level, style=level_color),
                str(row.get("event_type", "")),
                _truncate_line(msg, 60),
            )
        events_table.move_cursor(row=0)

        count = len(events)
        try:
            tab = self.query_one(TabbedContent).get_tab("tab-events")
            tab.label = f"Events ({count})"
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Queue row helper
    # ------------------------------------------------------------------

    def _selected_queue_row(self) -> dict[str, Any] | None:
        queue_rows = self._snapshot.get("queue_rows") or []
        if not queue_rows:
            return None
        queue_table = self.query_one("#queue-table", DataTable)
        cursor = queue_table.cursor_row
        if cursor < 0 or cursor >= len(queue_rows):
            return None
        return queue_rows[cursor]

    def _queue_table_focused(self) -> bool:
        try:
            return self.focused is self.query_one("#queue-table", DataTable)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Per-row actions
    # ------------------------------------------------------------------

    def action_retry_issue(self) -> None:
        if not self._queue_table_focused():
            return
        row = self._selected_queue_row()
        if row is None:
            self.notify("No issue selected.", severity="warning")
            return

        def _on_confirm(confirmed: bool) -> None:
            if confirmed:
                self._do_retry_issue(row)

        self.push_screen(ConfirmScreen(f"Retry issue #{row.get('issue_id')}?"), _on_confirm)

    @work(thread=True)
    def _do_retry_issue(self, row: dict[str, Any]) -> None:
        store = self._get_active_store()
        if store is None:
            self.notify("No store available.", severity="error")
            return
        issue_id = str(row.get("issue_id", ""))
        try:
            store.upsert_healer_issue(issue_id=issue_id, state="queued")
            self.notify(f"Issue #{issue_id} queued for retry.", severity="information")
        except Exception as exc:
            self.notify(f"Retry failed: {exc}", severity="error")
        finally:
            store.close()

    def action_clear_lock(self) -> None:
        if not self._queue_table_focused():
            return
        row = self._selected_queue_row()
        if row is None or not row.get("lease_owner"):
            self.notify("No locked issue selected.", severity="warning")
            return

        def _on_confirm(confirmed: bool) -> None:
            if confirmed:
                self._do_clear_lock(row)

        self.push_screen(ConfirmScreen(f"Clear lock on issue #{row.get('issue_id')}?"), _on_confirm)

    @work(thread=True)
    def _do_clear_lock(self, row: dict[str, Any]) -> None:
        store = self._get_active_store()
        if store is None:
            self.notify("No store available.", severity="error")
            return
        issue_id = str(row.get("issue_id", ""))
        try:
            store.release_healer_locks(issue_id=issue_id, lock_keys=None)
            self.notify(f"Lock cleared for issue #{issue_id}.", severity="information")
        except Exception as exc:
            self.notify(f"Clear lock failed: {exc}", severity="error")
        finally:
            store.close()

    def action_copy_issue_id(self) -> None:
        if not self._queue_table_focused():
            return
        row = self._selected_queue_row()
        if row is None:
            return
        issue_id = str(row.get("issue_id", ""))
        try:
            subprocess.run(["pbcopy"], input=issue_id.encode(), check=True)
            self.notify(f"Copied: {issue_id}", severity="information")
        except Exception:
            self.notify(f"Issue ID: {issue_id}", severity="information")

    def action_open_pr(self) -> None:
        if not self._queue_table_focused():
            return
        row = self._selected_queue_row()
        if row is None:
            return
        try:
            pr_number = int(row.get("pr_number") or 0)
        except (ValueError, TypeError):
            pr_number = 0
        if pr_number <= 0:
            self.notify("No PR for this issue.", severity="warning")
            return
        pr_url = str(row.get("pr_url") or row.get("pr_html_url") or "")
        if not pr_url:
            self.notify(f"PR #{pr_number} (no URL available)", severity="information")
            return
        webbrowser.open(pr_url)
        self.notify(f"Opened PR #{pr_number}", severity="information")

    @work(thread=True)
    def action_export_data(self) -> None:
        out_dir = default_export_dir(self._service.config)
        write_telemetry_exports(service=self._service, repo_name=self._repo_name, output_dir=out_dir)
        self.notify(f"Exported → {out_dir}", title="Export complete", severity="information")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_tui(
    *,
    config: AppConfig,
    service: FlowHealerService,
    repo_name: str | None,
    refresh_seconds: int = 5,
    once: bool = False,
) -> None:
    snapshot = build_tui_snapshot(service=service, repo_name=repo_name)
    if once or not sys.stdout.isatty():
        print(render_tui_text(snapshot))
        return

    prefs = load_tui_prefs(config)
    # CLI-supplied refresh_seconds overrides saved pref only when non-default
    if refresh_seconds != 5:
        prefs = TuiPrefs(
            theme=prefs.theme,
            refresh_seconds=max(1, int(refresh_seconds)),
            show_sparkline=prefs.show_sparkline,
        )
    FlowHealerApp(service, repo_name, prefs).run()


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _truncate_line(value: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return value[: width - 3] + "..."


def _format_key_values(mapping: dict[str, Any]) -> str:
    return ", ".join(f"{key}={mapping[key]}" for key in sorted(mapping))


def _sparkline_from_counts(mapping: dict[str, Any]) -> str:
    blocks = " ▁▂▃▄▅▆▇█"
    values = [max(0, int(mapping[key])) for key in sorted(mapping)]
    if not values or max(values) <= 0:
        return ""
    peak = max(values)
    return "".join(blocks[min(len(blocks) - 1, round((value / peak) * (len(blocks) - 1)))] for value in values)


def _hbar(value: int, max_val: int, width: int = 16) -> str:
    """Horizontal Unicode block bar: '████░░░░░░░░'"""
    if max_val <= 0:
        return "░" * width
    filled = round((value / max_val) * width)
    filled = max(0, min(filled, width))
    return "█" * filled + "░" * (width - filled)


def _recent_log_lines(config: AppConfig, *, limit: int) -> list[str]:
    root = config.state_root_path()
    lines: list[str] = []
    for name in ("flow-healer.log", "serve-web.log"):
        path = root / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            lines.append(f"[{name}] {line}")
    return lines[-limit:]
