from __future__ import annotations

from datetime import UTC, datetime
from html import escape
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse
from uuid import uuid4

from .config import AppConfig
from .control_plane import ControlRouter, parse_command_subject
from .service import FlowHealerService

_REFRESH_MS = 5000


class DashboardServer:
    def __init__(
        self,
        *,
        config: AppConfig,
        service: FlowHealerService,
        router: ControlRouter,
        host: str,
        port: int,
    ) -> None:
        self.config = config
        self.service = service
        self.router = router
        self.host = host
        self.port = int(port)
        self._thread: threading.Thread | None = None
        self._httpd: ThreadingHTTPServer | None = None

    def start(self) -> None:
        handler = self._make_handler()
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="flow-healer-web")
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/api/status":
                    self._write_json({"rows": server.service.status_rows(None)})
                    return
                if parsed.path == "/api/commands":
                    repo = (parse_qs(parsed.query).get("repo") or [""])[0].strip() or None
                    self._write_json({"rows": server.service.control_command_rows(repo, limit=200)})
                    return
                if parsed.path == "/api/logs":
                    lines = _parse_int((parse_qs(parsed.query).get("lines") or [""])[0], default=120, min_value=20, max_value=500)
                    self._write_json(_collect_recent_logs(server.config, max_lines=lines))
                    return
                if parsed.path == "/api/overview":
                    self._write_json(_overview_payload(server.config, server.service))
                    return
                if parsed.path not in {"/", ""}:
                    self.send_error(404, "Not Found")
                    return
                query = parse_qs(parsed.query)
                message = (query.get("msg") or [""])[0]
                self._write_html(_render_dashboard(server.config, server.service, message))

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != "/action":
                    self.send_error(404, "Not Found")
                    return
                params = self._read_form_data()
                command = (params.get("command") or "").strip().lower()
                repo = (params.get("repo") or "").strip()
                dry_run = (params.get("dry_run") or "").strip().lower()

                raw = f"FH: {command}"
                if repo:
                    raw += f" repo={repo}"
                if command == "scan" and dry_run in {"1", "true", "yes", "on"}:
                    raw += " dry_run=true"

                try:
                    parsed_command = parse_command_subject(raw, prefix="FH:")
                    if parsed_command is None:
                        raise ValueError("Invalid command format.")
                    result = server.router.execute(
                        request=parsed_command,
                        source="web",
                        external_id=f"web:{uuid4().hex[:16]}",
                        sender="web-ui",
                    )
                    msg = f"{command} completed" if result.get("ok") else str(result.get("message") or "command failed")
                except Exception as exc:
                    msg = f"error: {exc}"

                self.send_response(303)
                self.send_header("Location", f"/?msg={quote_plus(msg)}")
                self.end_headers()

            def _read_form_data(self) -> dict[str, str]:
                length = int(self.headers.get("Content-Length", "0") or "0")
                data = self.rfile.read(length) if length > 0 else b""
                parsed = parse_qs(data.decode("utf-8"), keep_blank_values=True)
                return {key: (values[0] if values else "") for key, values in parsed.items()}

            def _write_json(self, payload: dict[str, Any], status: int = 200) -> None:
                raw = json.dumps(payload, indent=2, default=str).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _write_html(self, html: str, status: int = 200) -> None:
                raw = html.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        return Handler


def _render_dashboard(config: AppConfig, service: FlowHealerService, notice: str) -> str:
    payload = _overview_payload(config, service)
    action_cards = []
    for repo in config.repos:
        action_cards.append(
            f"""
            <section class='card action-card'>
              <h3>{escape(repo.repo_name)}</h3>
              <form method='post' action='/action' class='actions'>
                <input type='hidden' name='repo' value='{escape(repo.repo_name)}'>
                <button name='command' value='status'>Status</button>
                <button name='command' value='doctor'>Doctor</button>
                <button name='command' value='pause'>Pause</button>
                <button name='command' value='resume'>Resume</button>
                <button name='command' value='once'>Run Once</button>
                <button name='command' value='scan'>Scan</button>
                <label class='dry'><input type='checkbox' name='dry_run' value='true'> dry</label>
              </form>
            </section>
            """
        )

    notice_html = f"<div class='notice'>{escape(notice)}</div>" if notice else ""
    initial = escape(json.dumps(payload, default=str))

    return f"""
<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Flow Healer Dashboard</title>
  <style>
    :root {{ --bg:#0d1117; --panel:#111a22; --line:#2f81f7; --muted:#8b949e; --ok:#7ee787; --warn:#f0b72f; --text:#e6edf3; }}
    * {{ box-sizing:border-box; }}
    body {{ font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif; margin:0; background:var(--bg); color:var(--text); }}
    header {{ padding:14px 16px; background:#111a22; position:sticky; top:0; border-bottom:1px solid #1f2a36; z-index:10; }}
    header h1 {{ margin:0 0 4px 0; font-size:1.1rem; }}
    .subtitle {{ margin:0; color:var(--muted); font-size:0.85rem; }}
    .topbar {{ display:flex; gap:8px; align-items:center; justify-content:space-between; flex-wrap:wrap; }}
    .refresh {{ background:#13202b; color:var(--text); border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-size:.85rem; }}
    main {{ padding:12px; max-width:1200px; margin:0 auto; }}
    .notice {{ background:#13202b; color:var(--warn); padding:10px; margin-bottom:12px; border-radius:8px; }}
    .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:8px; margin-bottom:12px; }}
    .kpi {{ background:var(--panel); border:1px solid #23303d; border-radius:10px; padding:10px; }}
    .kpi .label {{ color:var(--muted); font-size:.75rem; }}
    .kpi .value {{ font-size:1.2rem; font-weight:600; margin-top:4px; }}
    .grid {{ display:grid; grid-template-columns:1.2fr .8fr; gap:12px; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px; }}
    .card h2 {{ margin:0 0 8px 0; font-size:1rem; }}
    .actions {{ display:flex; gap:6px; flex-wrap:wrap; align-items:center; }}
    .actions button {{ background:#13202b; color:var(--text); border:1px solid var(--line); border-radius:8px; padding:7px 9px; font-size:.82rem; }}
    .dry {{ color:var(--muted); font-size:.82rem; }}
    table {{ width:100%; border-collapse:collapse; font-size:.83rem; }}
    th, td {{ border-bottom:1px solid #23303d; padding:8px; text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-weight:600; }}
    .status-pill {{ display:inline-block; border-radius:999px; padding:2px 8px; border:1px solid #2f81f7; font-size:.75rem; }}
    .logs {{ background:#0b141d; border:1px solid #23303d; border-radius:8px; min-height:220px; max-height:400px; overflow:auto; padding:10px; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.76rem; white-space:pre-wrap; }}
    .muted {{ color:var(--muted); }}
    .actions-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:8px; }}
    .action-card h3 {{ margin:0 0 8px 0; font-size:.95rem; }}
    @media (max-width: 920px) {{ .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <div class='topbar'>
      <div>
        <h1>Flow Healer Dashboard</h1>
        <p class='subtitle'>{escape(config.service.state_root)} • Auto refresh every 5s</p>
      </div>
      <button class='refresh' id='refresh-btn' type='button'>Refresh Now</button>
    </div>
  </header>
  <main>
    {notice_html}
    <section class='kpis' id='kpis'></section>

    <section class='card' style='margin-bottom:12px;'>
      <h2>Quick Actions</h2>
      <div class='actions-grid'>
        {''.join(action_cards)}
      </div>
    </section>

    <section class='grid'>
      <section class='card'>
        <h2>Repos</h2>
        <table>
          <thead><tr><th>Repo</th><th>Paused</th><th>Issues</th><th>States</th><th>Connector</th><th>Breaker</th></tr></thead>
          <tbody id='repo-rows'></tbody>
        </table>
      </section>

      <section class='card'>
        <h2>Recent Logs</h2>
        <div class='muted' id='log-meta'></div>
        <div class='logs' id='log-lines'></div>
      </section>
    </section>

    <section class='card' style='margin-top:12px;'>
      <h2>Recent Commands</h2>
      <table>
        <thead><tr><th>Time</th><th>Repo</th><th>Source</th><th>Command</th><th>Status</th><th>Error</th></tr></thead>
        <tbody id='command-rows'></tbody>
      </table>
    </section>
  </main>

  <script id='initial-data' type='application/json'>{initial}</script>
  <script>
    const refreshMs = {_REFRESH_MS};

    const esc = (value) => String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

    function render(payload) {{
      const rows = Array.isArray(payload.rows) ? payload.rows : [];
      const commands = Array.isArray(payload.commands) ? payload.commands : [];
      const logs = payload.logs || {{ lines: [], files: [] }};

      const totalIssues = rows.reduce((acc, row) => acc + Number(row.issues_total || 0), 0);
      const pausedRepos = rows.filter((row) => !!row.paused).length;
      const unavailable = rows.filter((row) => !(row.connector || {{}}).available).length;
      const breakerOpen = rows.filter((row) => !!((row.circuit_breaker || {{}}).open)).length;

      document.getElementById('kpis').innerHTML = `
        <div class='kpi'><div class='label'>Repos</div><div class='value'>${{rows.length}}</div></div>
        <div class='kpi'><div class='label'>Total Issues</div><div class='value'>${{totalIssues}}</div></div>
        <div class='kpi'><div class='label'>Paused Repos</div><div class='value'>${{pausedRepos}}</div></div>
        <div class='kpi'><div class='label'>Connector Down</div><div class='value'>${{unavailable}}</div></div>
        <div class='kpi'><div class='label'>Breaker Open</div><div class='value'>${{breakerOpen}}</div></div>
      `;

      document.getElementById('repo-rows').innerHTML = rows.map((row) => {{
        const counts = row.state_counts || {{}};
        const countsText = Object.entries(counts).sort((a, b) => a[0].localeCompare(b[0])).map(([k, v]) => `${{k}}:${{v}}`).join(', ') || 'none';
        const connector = row.connector || {{}};
        const breaker = row.circuit_breaker || {{}};
        return `<tr>
          <td><b>${{esc(row.repo)}}</b></td>
          <td>${{row.paused ? 'yes' : 'no'}}</td>
          <td>${{esc(row.issues_total)}}</td>
          <td>${{esc(countsText)}}</td>
          <td><span class='status-pill'>${{connector.available ? 'up' : 'down'}}</span></td>
          <td><span class='status-pill'>${{breaker.open ? 'open' : 'closed'}}</span></td>
        </tr>`;
      }}).join('');

      document.getElementById('command-rows').innerHTML = commands.map((item) => `<tr>
        <td>${{esc(item.created_at)}}</td>
        <td>${{esc(item.repo_name)}}</td>
        <td>${{esc(item.source)}}</td>
        <td>${{esc(item.parsed_command)}}</td>
        <td>${{esc(item.status)}}</td>
        <td>${{esc(item.error_text)}}</td>
      </tr>`).join('');

      const lines = Array.isArray(logs.lines) ? logs.lines : [];
      document.getElementById('log-lines').textContent = lines.length ? lines.join('\\n') : 'No recent logs found.';
      const files = Array.isArray(logs.files) ? logs.files : [];
      const generated = payload.generated_at || '';
      document.getElementById('log-meta').textContent = `Files: ${{files.join(', ') || 'none'}} • Updated: ${{generated}}`;
    }}

    async function refreshOverview() {{
      try {{
        const response = await fetch('/api/overview', {{ cache: 'no-store' }});
        if (!response.ok) return;
        const payload = await response.json();
        render(payload);
      }} catch (error) {{
        // Keep last good UI state.
      }}
    }}

    document.getElementById('refresh-btn').addEventListener('click', refreshOverview);

    try {{
      const initial = JSON.parse(document.getElementById('initial-data').textContent || '{{}}');
      render(initial);
    }} catch (error) {{}}

    setInterval(refreshOverview, refreshMs);
  </script>
</body>
</html>
"""


def _overview_payload(config: AppConfig, service: FlowHealerService) -> dict[str, Any]:
    return {
        "rows": service.status_rows(None),
        "commands": service.control_command_rows(None, limit=120),
        "logs": _collect_recent_logs(config, max_lines=160),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
    }


def _collect_recent_logs(config: AppConfig, *, max_lines: int = 120) -> dict[str, Any]:
    root = Path(config.service.state_root).expanduser().resolve()
    candidates = [root / "flow-healer.log", root / "serve-web.log"]
    per_file = max(20, int(max_lines / max(1, len(candidates))))

    lines: list[str] = []
    files: list[str] = []
    for path in candidates:
        if not path.exists() or not path.is_file():
            continue
        files.append(path.name)
        for line in _tail_file_lines(path, per_file):
            text = line.rstrip("\n")
            if not text:
                continue
            lines.append(f"[{path.name}] {text}")

    if len(lines) > max_lines:
        lines = lines[-max_lines:]

    return {
        "files": files,
        "lines": lines,
    }


def _tail_file_lines(path: Path, max_lines: int) -> list[str]:
    wanted = max(1, int(max_lines))
    with path.open("rb") as handle:
        handle.seek(0, 2)
        file_size = handle.tell()
        if file_size <= 0:
            return []

        block_size = 4096
        cursor = file_size
        data = b""

        while cursor > 0 and data.count(b"\n") <= wanted:
            read_size = min(block_size, cursor)
            cursor -= read_size
            handle.seek(cursor)
            data = handle.read(read_size) + data

    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > wanted:
        lines = lines[-wanted:]
    return lines


def _parse_int(raw: str, *, default: int, min_value: int, max_value: int) -> int:
    text = (raw or "").strip()
    if not text:
        return default
    try:
        value = int(text)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))
