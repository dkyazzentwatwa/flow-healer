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

    # Build repo action buttons as Alpine.js powered dropdowns
    repo_actions = []
    for repo in config.repos:
        repo_actions.append(
            f"""
            <div class='border border-gray-800 rounded-lg p-4 bg-gray-900'>
              <div class='flex items-center justify-between'>
                <h3 class='text-sm font-semibold text-gray-100'>{escape(repo.repo_name)}</h3>
                <button
                  @click="activeActions === '{escape(repo.repo_name)}' ? activeActions = '' : activeActions = '{escape(repo.repo_name)}'"
                  class='px-2 py-1 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded transition'
                >
                  Actions
                </button>
              </div>
              <div x-show="activeActions === '{escape(repo.repo_name)}'" class='mt-3 pt-3 border-t border-gray-800'>
                <div class='space-y-2'>
                  <form method='post' action='/action' class='contents'>
                    <input type='hidden' name='repo' value='{escape(repo.repo_name)}'>
                    <button type='submit' name='command' value='status' class='w-full text-left px-3 py-2 text-xs bg-gray-800 hover:bg-gray-700 text-gray-100 rounded transition'>
                      Status
                    </button>
                    <button type='submit' name='command' value='doctor' class='w-full text-left px-3 py-2 text-xs bg-gray-800 hover:bg-gray-700 text-gray-100 rounded transition'>
                      Doctor
                    </button>
                    <button type='submit' name='command' value='pause' class='w-full text-left px-3 py-2 text-xs bg-gray-800 hover:bg-gray-700 text-gray-100 rounded transition'>
                      Pause
                    </button>
                    <button type='submit' name='command' value='resume' class='w-full text-left px-3 py-2 text-xs bg-gray-800 hover:bg-gray-700 text-gray-100 rounded transition'>
                      Resume
                    </button>
                    <button type='submit' name='command' value='once' class='w-full text-left px-3 py-2 text-xs bg-gray-800 hover:bg-gray-700 text-gray-100 rounded transition'>
                      Run Once
                    </button>
                    <div class='flex items-center gap-2 px-3 py-2'>
                      <button type='submit' name='command' value='scan' class='flex-1 text-left text-xs bg-gray-800 hover:bg-gray-700 text-gray-100 rounded px-2 py-1 transition'>
                        Scan
                      </button>
                      <label class='text-xs text-gray-400 flex items-center gap-1'>
                        <input type='checkbox' name='dry_run' value='true' class='rounded'>
                        dry
                      </label>
                    </div>
                  </form>
                </div>
              </div>
            </div>
            """
        )

    notice_html = f"""
    <div class='mb-4 p-3 bg-amber-900/30 border border-amber-800 rounded-lg text-amber-300 text-sm'>
      {escape(notice)}
    </div>
    """ if notice else ""

    initial = escape(json.dumps(payload, default=str))

    return f"""
<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Flow Healer Dashboard</title>
  <script src='https://cdn.tailwindcss.com'></script>
  <script defer src='https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js'></script>
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          colors: {{
            dark: '#0f172a'
          }}
        }}
      }}
    }}
  </script>
</head>
<body class='bg-gray-950 text-gray-100 font-sans'>
  <header class='sticky top-0 z-10 bg-gray-900 border-b border-gray-800'>
    <div class='px-6 py-4'>
      <div class='flex items-center justify-between'>
        <div>
          <h1 class='text-lg font-bold text-gray-100'>Flow Healer Dashboard</h1>
          <p class='text-xs text-gray-400 mt-1'>{escape(config.service.state_root)} • Auto-refresh every 5s</p>
        </div>
        <div class='flex items-center gap-3'>
          <span class='inline-flex items-center gap-2 text-xs text-gray-400'>
            <span class='inline-block w-2 h-2 bg-emerald-400 rounded-full'></span>
            Live
          </span>
          <button
            @click='refresh()'
            class='px-3 py-2 text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition'
          >
            Refresh Now
          </button>
        </div>
      </div>
    </div>
  </header>

  <main class='max-w-7xl mx-auto px-6 py-6' x-data='dashboardApp()' @load='init()'>
    {notice_html}

    <!-- KPI Strip -->
    <div class='grid grid-cols-2 md:grid-cols-5 gap-4 mb-6'>
      <div class='bg-gray-900 border border-gray-800 rounded-lg p-4'>
        <div class='text-xs text-gray-400 uppercase tracking-wide'>Repos</div>
        <div class='text-2xl font-bold text-gray-100 mt-2' x-text='rows.length'></div>
      </div>
      <div class='bg-gray-900 border border-gray-800 rounded-lg p-4'>
        <div class='text-xs text-gray-400 uppercase tracking-wide'>Total Issues</div>
        <div class='text-2xl font-bold text-gray-100 mt-2' x-text='totalIssues'></div>
      </div>
      <div class='bg-gray-900 border border-gray-800 rounded-lg p-4'>
        <div class='text-xs text-gray-400 uppercase tracking-wide'>Paused Repos</div>
        <div class='text-2xl font-bold text-amber-400 mt-2' x-text='pausedRepos'></div>
      </div>
      <div class='bg-gray-900 border border-gray-800 rounded-lg p-4'>
        <div class='text-xs text-gray-400 uppercase tracking-wide'>Connector Down</div>
        <div class='text-2xl font-bold text-red-400 mt-2' x-text='connectorDown'></div>
      </div>
      <div class='bg-gray-900 border border-gray-800 rounded-lg p-4'>
        <div class='text-xs text-gray-400 uppercase tracking-wide'>Breaker Open</div>
        <div class='text-2xl font-bold text-red-400 mt-2' x-text='breakerOpen'></div>
      </div>
    </div>

    <!-- Repo Actions (Inline per repo) -->
    <div class='mb-6'>
      <h2 class='text-sm font-semibold text-gray-100 mb-4'>Repos</h2>
      <div class='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'>
        {''.join(repo_actions)}
      </div>
    </div>

    <!-- Two-column layout: Commands & Logs -->
    <div class='grid grid-cols-1 lg:grid-cols-3 gap-6'>
      <!-- Recent Commands (spans 2 cols on desktop) -->
      <div class='lg:col-span-2 bg-gray-900 border border-gray-800 rounded-lg p-4'>
        <h2 class='text-sm font-semibold text-gray-100 mb-4'>Recent Commands</h2>
        <div class='overflow-x-auto'>
          <table class='w-full text-xs'>
            <thead>
              <tr class='border-b border-gray-800'>
                <th class='text-left px-3 py-2 text-gray-400 font-medium'>Time</th>
                <th class='text-left px-3 py-2 text-gray-400 font-medium'>Repo</th>
                <th class='text-left px-3 py-2 text-gray-400 font-medium'>Source</th>
                <th class='text-left px-3 py-2 text-gray-400 font-medium'>Command</th>
                <th class='text-left px-3 py-2 text-gray-400 font-medium'>Status</th>
              </tr>
            </thead>
            <tbody>
              <template x-for='cmd in commands' :key='cmd.created_at + cmd.parsed_command'>
                <tr class='border-b border-gray-800 hover:bg-gray-800/50'>
                  <td class='px-3 py-2 text-gray-400' x-text='cmd.created_at'></td>
                  <td class='px-3 py-2 text-gray-200' x-text='cmd.repo_name'></td>
                  <td class='px-3 py-2 text-gray-400' x-text='cmd.source'></td>
                  <td class='px-3 py-2 text-gray-300' x-text='cmd.parsed_command'></td>
                  <td class='px-3 py-2'>
                    <span :class='statusClass(cmd.status)' x-text='cmd.status'></span>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
          <div x-show='!commands.length' class='text-center py-6 text-gray-400 text-xs'>
            No recent commands
          </div>
        </div>
      </div>

      <!-- Log Viewer -->
      <div class='bg-gray-900 border border-gray-800 rounded-lg p-4 flex flex-col'>
        <h2 class='text-sm font-semibold text-gray-100 mb-2'>Recent Logs</h2>
        <div class='text-xs text-gray-500 mb-3' x-text='logMeta'></div>
        <div class='flex-1 bg-gray-950 border border-gray-800 rounded p-3 overflow-y-auto font-mono text-xs leading-relaxed text-gray-300 whitespace-pre-wrap'>
          <template x-if='logs.length'>
            <div x-text='logs.join("\\n")'></div>
          </template>
          <template x-if='!logs.length'>
            <div class='text-gray-500'>No recent logs found.</div>
          </template>
        </div>
      </div>
    </div>
  </main>

  <script id='initial-data' type='application/json'>{initial}</script>
  <script>
    function dashboardApp() {{
      return {{
        rows: [],
        commands: [],
        logs: [],
        logMeta: '',
        activeActions: '',
        refreshMs: {_REFRESH_MS},

        get totalIssues() {{
          return this.rows.reduce((acc, row) => acc + Number(row.issues_total || 0), 0);
        }},

        get pausedRepos() {{
          return this.rows.filter((row) => !!row.paused).length;
        }},

        get connectorDown() {{
          return this.rows.filter((row) => !(row.connector || {{}}).available).length;
        }},

        get breakerOpen() {{
          return this.rows.filter((row) => !!((row.circuit_breaker || {{}}).open)).length;
        }},

        statusClass(status) {{
          const lower = (status || '').toLowerCase();
          if (lower === 'ok' || lower === 'success' || lower === 'completed') {{
            return 'text-emerald-400';
          }}
          if (lower === 'error' || lower === 'failed') {{
            return 'text-red-400';
          }}
          if (lower === 'pending' || lower === 'running') {{
            return 'text-amber-400';
          }}
          return 'text-gray-400';
        }},

        async init() {{
          try {{
            const script = document.getElementById('initial-data');
            if (script) {{
              const initial = JSON.parse(script.textContent || '{{}}');
              this.updateFromPayload(initial);
            }}
          }} catch (e) {{
            console.error('Failed to parse initial data:', e);
          }}
          setInterval(() => this.refresh(), this.refreshMs);
        }},

        async refresh() {{
          try {{
            const response = await fetch('/api/overview', {{ cache: 'no-store' }});
            if (!response.ok) return;
            const payload = await response.json();
            this.updateFromPayload(payload);
          }} catch (error) {{
            console.error('Failed to refresh:', error);
          }}
        }},

        updateFromPayload(payload) {{
          this.rows = Array.isArray(payload.rows) ? payload.rows : [];
          this.commands = Array.isArray(payload.commands) ? payload.commands : [];
          const logsData = payload.logs || {{}};
          this.logs = Array.isArray(logsData.lines) ? logsData.lines : [];
          const files = Array.isArray(logsData.files) ? logsData.files : [];
          const generated = payload.generated_at || '';
          this.logMeta = `Files: ${{files.join(', ') || 'none'}} • Updated: ${{generated}}`;
        }}
      }};
    }}
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
