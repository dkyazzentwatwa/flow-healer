from __future__ import annotations

import curses
import sys
import time
from datetime import UTC, datetime
from typing import Any

from .config import AppConfig
from .service import FlowHealerService
from .telemetry_exports import collect_telemetry_datasets


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

    curses.wrapper(_curses_main, service, repo_name, max(1, int(refresh_seconds)))


def _curses_main(stdscr: Any, service: FlowHealerService, repo_name: str | None, refresh_seconds: int) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    last_refresh = 0.0
    rendered = ""
    while True:
        now = time.monotonic()
        if not rendered or (now - last_refresh) >= refresh_seconds:
            rendered = render_tui_text(build_tui_snapshot(service=service, repo_name=repo_name))
            last_refresh = now
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        for idx, line in enumerate(rendered.splitlines()[: max(1, height - 1)]):
            stdscr.addnstr(idx, 0, line, max(1, width - 1))
        stdscr.refresh()
        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            return
        if key in (ord("r"), ord("R")):
            rendered = ""
        time.sleep(0.1)


def _format_key_values(mapping: dict[str, Any]) -> str:
    return ", ".join(f"{key}={mapping[key]}" for key in sorted(mapping))


def _sparkline_from_counts(mapping: dict[str, Any]) -> str:
    blocks = " ▁▂▃▄▅▆▇█"
    values = [max(0, int(mapping[key])) for key in sorted(mapping)]
    if not values or max(values) <= 0:
        return ""
    peak = max(values)
    return "".join(blocks[min(len(blocks) - 1, round((value / peak) * (len(blocks) - 1)))] for value in values)


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
