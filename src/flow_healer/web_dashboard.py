from __future__ import annotations

from datetime import UTC, datetime
from html import escape
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import secrets
import threading
import tempfile
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse
from uuid import uuid4

from .config import AppConfig
from .control_plane import ControlRouter, parse_command_subject
from .service import FlowHealerService

_REFRESH_MS = 5000
_ACTIVITY_LIMIT = 240
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>[A-Z]+)\s+"
    r"(?P<subsystem>[^:]+):\s*"
    r"(?P<message>.*)$"
)
_ISSUE_ID_RE = re.compile(r"issue\s+#(?P<issue_id>\d+)", re.IGNORECASE)
_PR_ID_RE = re.compile(r"PR\s+#(?P<pr_id>\d+)", re.IGNORECASE)
_ATTEMPT_ID_RE = re.compile(r"\b(?P<attempt_id>hat_[a-z0-9]+)\b", re.IGNORECASE)
_BRANCH_RE = re.compile(r"\b(?P<branch>healer/[A-Za-z0-9._/\-]+)\b")
_POINT_WEIGHTS: tuple[tuple[str, str, int], ...] = (
    ("issue_successes", "Issue wins", 120),
    ("issue_failures", "Issue losses", -90),
    ("first_pass_success_rate", "First-pass success", 400),
    ("no_op_rate", "No-op rate", -180),
    ("wrong_root_rate", "Wrong-root rate", -220),
    ("current_success_streak", "Success streak", 35),
)


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
                query = parse_qs(parsed.query)
                if parsed.path == "/api/queue":
                    self._write_json(_queue_payload(server.config, server.service))
                    return
                if parsed.path == "/api/issue-detail":
                    repo = (query.get("repo") or [""])[0].strip()
                    issue_id = (query.get("issue_id") or [""])[0].strip()
                    self._write_json(_issue_detail_payload(server.config, server.service, repo_name=repo, issue_id=issue_id))
                    return
                if parsed.path == "/api/status":
                    self._write_json({"rows": server.service.status_rows(None)})
                    return
                if parsed.path == "/api/commands":
                    repo = (query.get("repo") or [""])[0].strip() or None
                    self._write_json({"rows": server.service.control_command_rows(repo, limit=200)})
                    return
                if parsed.path == "/api/logs":
                    lines = _parse_int((query.get("lines") or [""])[0], default=120, min_value=20, max_value=500)
                    self._write_json(_collect_recent_logs(server.config, max_lines=lines))
                    return
                if parsed.path == "/api/activity":
                    self._write_json({"rows": _collect_activity(server.config, server.service)})
                    return
                if parsed.path == "/api/overview":
                    self._write_json(_overview_payload(server.config, server.service))
                    return
                if parsed.path.startswith("/assets/"):
                    asset_path = _resolve_dashboard_static_path(parsed.path)
                    if asset_path is None or not asset_path.exists() or not asset_path.is_file():
                        self.send_error(404, "Not Found")
                        return
                    self._write_file(asset_path)
                    return
                if parsed.path == "/artifact":
                    artifact_path = _resolve_dashboard_artifact_path(
                        server.config,
                        (query.get("path") or [""])[0],
                    )
                    if artifact_path is None:
                        self.send_error(403, "Artifact path not allowed")
                        return
                    if not artifact_path.exists() or not artifact_path.is_file():
                        self.send_error(404, "Artifact not found")
                        return
                    self._write_file(artifact_path)
                    return
                if parsed.path not in {"/", ""}:
                    self.send_error(404, "Not Found")
                    return
                message = (query.get("msg") or [""])[0]
                self._write_html(_render_dashboard(server.config, server.service, message))

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != "/action":
                    self.send_error(404, "Not Found")
                    return
                params = self._read_form_data()
                allowed, status, reason = _web_request_is_authorized(
                    server.config,
                    headers=dict(self.headers.items()),
                    params=params,
                )
                if not allowed:
                    self._write_json({"ok": False, "message": reason}, status=status)
                    return
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

            def _write_file(self, path: Path, status: int = 200) -> None:
                raw = path.read_bytes()
                content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        return Handler


def _render_dashboard(config: AppConfig, service: FlowHealerService, notice: str) -> str:
    payload = _overview_payload(config, service)
    repo_names = [repo.repo_name for repo in config.repos]
    initial = json.dumps(payload, default=str).replace("</", "<\\/")
    repo_actions = _render_repo_action_cards(config)
    repo_options = "".join(
        f"<option value='{escape(repo_name)}'>{escape(repo_name)}</option>" for repo_name in repo_names
    )
    notice_html = (
        f"""
        <div class='mb-6 rounded-3xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100 shadow-lg shadow-amber-950/30'>
          {escape(notice)}
        </div>
        """
        if notice
        else ""
    )

    return f"""
<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Flow Healer Dashboard</title>
  <link rel='preconnect' href='https://fonts.googleapis.com'>
  <link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>
  <link href='https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap' rel='stylesheet'>
  <script src='https://cdn.tailwindcss.com'></script>
  <script defer src='https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js'></script>
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          fontFamily: {{
            display: ['Space Grotesk', 'ui-sans-serif', 'system-ui', 'sans-serif'],
            mono: ['IBM Plex Mono', 'SFMono-Regular', 'ui-monospace', 'monospace']
          }},
          boxShadow: {{
            glow: '6px 6px 0 rgba(2, 6, 23, 0.95)'
          }}
        }}
      }}
    }}
  </script>
  <style>
    :root {{
      color-scheme: dark;
      --fh-bg: #0a0a0a;
      --fh-panel: #121212;
      --fh-panel-soft: #191919;
      --fh-panel-mute: #101010;
      --fh-border: #f3f4f6;
      --fh-border-soft: #4b5563;
      --fh-text: #f3f4f6;
      --fh-muted: #9ca3af;
      --fh-shadow: rgba(0, 0, 0, 0.92);
      --fh-atmosphere: linear-gradient(180deg, #050505 0%, #101010 52%, #050505 100%);
    }}
    :root[data-theme='light'] {{
      color-scheme: light;
      --fh-bg: #f2efe9;
      --fh-panel: #ffffff;
      --fh-panel-soft: #f8f4ee;
      --fh-panel-mute: #ece7dc;
      --fh-border: #111827;
      --fh-border-soft: #6b7280;
      --fh-text: #111827;
      --fh-muted: #4b5563;
      --fh-shadow: rgba(17, 24, 39, 0.35);
      --fh-atmosphere: linear-gradient(180deg, #f7f4ed 0%, #efe9dd 52%, #e8e1d3 100%);
    }}
    body {{
      background: var(--fh-bg) !important;
      color: var(--fh-text) !important;
      font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif;
    }}
    .app-atmosphere {{
      background: var(--fh-atmosphere);
    }}
    .dashboard-root [class*='rounded-'] {{
      border-radius: 0.2rem !important;
    }}
    .dashboard-root .shadow-glow,
    .dashboard-root .shadow-2xl,
    .dashboard-root .shadow-lg {{
      box-shadow: 6px 6px 0 var(--fh-shadow) !important;
    }}
    .dashboard-root .backdrop-blur,
    .dashboard-root .backdrop-blur-sm,
    .dashboard-root .backdrop-blur-xl {{
      backdrop-filter: none !important;
    }}
    .dashboard-root .bg-slate-900\\/80,
    .dashboard-root .bg-slate-900\\/75,
    .dashboard-root .bg-slate-900\\/70,
    .dashboard-root .bg-slate-950\\/95,
    .dashboard-root .bg-slate-950\\/80,
    .dashboard-root .bg-slate-950\\/20 {{
      background-color: var(--fh-panel-soft) !important;
    }}
    .dashboard-root .bg-white\\/5,
    .dashboard-root .bg-white\\/\\[0\\.03\\],
    .dashboard-root .bg-black\\/30 {{
      background-color: var(--fh-panel-mute) !important;
    }}
    .dashboard-root .border-white\\/10,
    .dashboard-root .border-white\\/5 {{
      border-color: var(--fh-border-soft) !important;
    }}
    .dashboard-root .text-white,
    .dashboard-root .text-slate-100,
    .dashboard-root .text-slate-200 {{
      color: var(--fh-text) !important;
    }}
    .dashboard-root .text-slate-300,
    .dashboard-root .text-slate-400,
    .dashboard-root .text-slate-500 {{
      color: var(--fh-muted) !important;
    }}
  </style>
</head>
<body class='min-h-screen'>
  <div class='app-atmosphere absolute inset-0 -z-10'></div>

  <main class='dashboard-root mx-auto max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8' x-data='dashboardApp()' x-init='init()' @keydown.window.escape='closeInspector()'>
    {notice_html}

    <header class='mb-6 rounded-[32px] border border-white/10 bg-slate-900/80 px-5 py-5 shadow-glow backdrop-blur-xl'>
      <div class='flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between'>
        <div class='space-y-3'>
          <div class='inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-200'>
            <span class='inline-block h-2 w-2 rounded-full bg-cyan-300'></span>
            Live Operations Console
          </div>
          <div>
            <h1 class='font-display text-3xl font-semibold tracking-tight text-white sm:text-4xl'>Flow Healer Activity Console</h1>
            <p class='mt-2 max-w-3xl text-sm text-slate-300'>
              Unified commands, attempts, and runtime logs in one place, with drilldown inspectors that make the ugly parts readable.
            </p>
          </div>
        </div>
        <div class='grid grid-cols-2 gap-3 sm:grid-cols-5'>
          <div class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Refresh</div>
            <div class='mt-2 text-lg font-semibold text-white'>5s</div>
          </div>
          <div class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Activity Rows</div>
            <div class='mt-2 text-lg font-semibold text-white' x-text='activity.length'></div>
          </div>
          <div class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Log Files</div>
            <div class='mt-2 text-lg font-semibold text-white' x-text='logFilesLabel'></div>
          </div>
          <div class='flex items-center justify-end'>
            <button
              @click='refresh()'
              class='inline-flex items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/15 px-4 py-3 text-sm font-medium text-cyan-100 transition hover:bg-cyan-400/20'
            >
              Refresh now
            </button>
          </div>
          <div class='flex items-center justify-end'>
            <button
              @click='toggleTheme()'
              class='inline-flex items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-slate-100 transition hover:bg-white/10'
            >
              Dark / Light
            </button>
          </div>
        </div>
      </div>
    </header>

    <section class='mb-6 grid grid-cols-2 gap-4 xl:grid-cols-5'>
      <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
        <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Repos</div>
        <div class='mt-3 text-3xl font-semibold text-white' x-text='rows.length'></div>
      </div>
      <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
        <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Open Issues</div>
        <div class='mt-3 text-3xl font-semibold text-white' x-text='totalIssues'></div>
      </div>
      <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
        <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Active Attempts</div>
        <div class='mt-3 text-3xl font-semibold text-amber-300' x-text='activeAttempts'></div>
      </div>
      <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
        <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Failures</div>
        <div class='mt-3 text-3xl font-semibold text-rose-300' x-text='failureCount'></div>
      </div>
      <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
        <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Paused Repos</div>
        <div class='mt-3 text-3xl font-semibold text-amber-300' x-text='pausedRepos'></div>
      </div>
    </section>

    <section class='mb-6 rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-5 shadow-glow backdrop-blur'>
      <div class='flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between'>
        <div>
          <h2 class='text-xl font-semibold text-white'>Flow Healer Progress</h2>
          <p class='mt-1 text-sm text-slate-300'>
            Shareable scoreboard mode: every stat is derived from live issue and attempt telemetry, with the scoring formula exposed inline.
          </p>
        </div>
        <div class='flex flex-wrap items-center gap-2'>
          <button
            type='button'
            @click='showScoreExplainer = !showScoreExplainer'
            class='rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1.5 text-[11px] uppercase tracking-[0.24em] text-cyan-100 transition hover:bg-cyan-400/15'
          >
            How points work
          </button>
          <div class='rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[11px] uppercase tracking-[0.24em] text-slate-300'>
            Real telemetry only
          </div>
        </div>
      </div>
      <div class='mt-4 grid grid-cols-2 gap-4 xl:grid-cols-6'>
        <div class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
          <div class='text-[11px] uppercase tracking-[0.2em] text-slate-400'>Agent Level</div>
          <div class='mt-2 text-3xl font-semibold text-white' x-text='scoreboard.agent_level || 1'></div>
        </div>
        <div class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
          <div class='text-[11px] uppercase tracking-[0.2em] text-slate-400'>Agent Points</div>
          <div class='mt-2 text-3xl font-semibold text-white' x-text='scoreboard.agent_points || 0'></div>
        </div>
        <div class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
          <div class='text-[11px] uppercase tracking-[0.2em] text-slate-400'>First-Pass Success</div>
          <div class='mt-2 text-3xl font-semibold text-emerald-200' x-text='formatPercent(scoreboard.first_pass_success_rate)'></div>
        </div>
        <div class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
          <div class='text-[11px] uppercase tracking-[0.2em] text-slate-400'>Win Rate</div>
          <div class='mt-2 text-3xl font-semibold text-white' x-text='formatPercent(scoreboard.win_rate)'></div>
        </div>
        <div class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
          <div class='text-[11px] uppercase tracking-[0.2em] text-slate-400'>Current Success Streak</div>
          <div class='mt-2 text-3xl font-semibold text-cyan-100' x-text='scoreboard.current_success_streak || 0'></div>
        </div>
        <div class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
          <div class='text-[11px] uppercase tracking-[0.2em] text-slate-400'>Issue Wins vs Losses</div>
          <div class='mt-2 text-2xl font-semibold text-white' x-text='`${{scoreboard.issue_successes || 0}} / ${{scoreboard.issue_failures || 0}}`'></div>
        </div>
      </div>
      <div x-show='showScoreExplainer' x-transition.opacity class='mt-4 rounded-2xl border border-cyan-400/20 bg-cyan-400/5 px-4 py-4'>
        <div class='flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between'>
          <div>
            <h3 class='text-sm font-semibold uppercase tracking-[0.22em] text-cyan-100'>Point Formula</h3>
            <p class='mt-2 max-w-3xl text-sm text-slate-300' x-text='scoreExplainer.summary || ""'></p>
          </div>
          <div class='rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-300'>
            <span x-text='`Samples: ${{(scoreExplainer.samples || {{}}).issues || 0}} issues / ${{(scoreExplainer.samples || {{}}).attempts || 0}} attempts`'></span>
          </div>
        </div>
        <div class='mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3'>
          <template x-for='row in scoreExplainer.formula_rows || []' :key='row.label'>
            <div class='rounded-2xl border border-white/10 bg-slate-950/40 px-3 py-3'>
              <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500' x-text='row.label'></div>
              <div class='mt-2 text-sm text-slate-100'>
                <span class='font-semibold' x-text='row.value'></span>
                <span class='text-slate-400' x-text='` × ${{row.weight}}`'></span>
              </div>
              <div class='mt-2 text-xs text-cyan-100' x-text='signedNumber(row.contribution)'></div>
            </div>
          </template>
        </div>
        <div class='mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2'>
          <div class='rounded-2xl border border-white/10 bg-white/5 px-3 py-3 text-xs text-slate-300' x-text='(scoreExplainer.definitions || {{}}).win_rate || ""'></div>
          <div class='rounded-2xl border border-white/10 bg-white/5 px-3 py-3 text-xs text-slate-300' x-text='(scoreExplainer.definitions || {{}}).streak || ""'></div>
        </div>
      </div>
      <div class='mt-4 rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
        <div class='mb-2 flex items-center justify-between text-xs uppercase tracking-[0.2em] text-slate-400'>
          <span>XP Progress</span>
          <span x-text='`${{scoreboard.xp_in_level || 0}} / 1000`'></span>
        </div>
        <div class='h-4 border border-white/10 bg-slate-950/20'>
          <div class='h-full bg-cyan-400/40 transition-all duration-500' :style='`width: ${{scoreboard.xp_progress_pct || 0}}%`'></div>
        </div>
        <p class='mt-2 text-xs text-slate-300' x-text='`${{scoreboard.xp_to_next || 1000}} XP to next level`'></p>
      </div>
    </section>

    <section class='mb-6 rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-5 shadow-glow backdrop-blur'>
      <div class='flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between'>
        <div>
          <h2 class='text-xl font-semibold text-white'>Telemetry Trends</h2>
          <p class='mt-1 text-sm text-slate-300'>Collapsible trend deck built for quick diagnosis and screenshot-ready shareability.</p>
        </div>
        <button
          type='button'
          @click='showTelemetryCharts = !showTelemetryCharts'
          class='rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-slate-100 transition hover:bg-white/10'
          x-text='showTelemetryCharts ? "Hide charts" : "Show charts"'
        ></button>
      </div>
      <div x-show='showTelemetryCharts' x-transition.opacity class='mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2'>
        <div class='rounded-[28px] border border-white/10 bg-slate-950/40 p-4'>
          <div class='mb-3 flex items-center justify-between gap-3'>
            <div>
              <h3 class='text-sm font-semibold uppercase tracking-[0.22em] text-slate-200'>First-pass vs Drift</h3>
              <p class='mt-1 text-xs text-slate-400'>Green is better. Amber and rose should trend downward.</p>
            </div>
            <div class='text-right text-[11px] uppercase tracking-[0.2em] text-slate-500'>30d</div>
          </div>
          <svg viewBox='0 0 640 240' class='h-64 w-full rounded-2xl border border-white/10 bg-black/20 p-2'>
            <polyline fill='none' stroke='#86efac' stroke-width='4' :points='linePoints(chartSeries.reliability || [], "first_pass_success_rate")'></polyline>
            <polyline fill='none' stroke='#fbbf24' stroke-width='3' :points='linePoints(chartSeries.reliability || [], "no_op_rate")'></polyline>
            <polyline fill='none' stroke='#f87171' stroke-width='3' :points='linePoints(chartSeries.reliability || [], "wrong_root_rate")'></polyline>
          </svg>
          <div class='mt-3 flex flex-wrap gap-2 text-xs'>
            <span class='rounded-full border border-emerald-300/30 bg-emerald-400/10 px-2 py-1 text-emerald-100'>First-pass success</span>
            <span class='rounded-full border border-amber-300/30 bg-amber-400/10 px-2 py-1 text-amber-100'>No-op rate</span>
            <span class='rounded-full border border-rose-300/30 bg-rose-400/10 px-2 py-1 text-rose-100'>Wrong-root rate</span>
          </div>
        </div>
        <div class='rounded-[28px] border border-white/10 bg-slate-950/40 p-4'>
          <div class='mb-3 flex items-center justify-between gap-3'>
            <div>
              <h3 class='text-sm font-semibold uppercase tracking-[0.22em] text-slate-200'>Issue Outcomes</h3>
              <p class='mt-1 text-xs text-slate-400'>Daily terminal issue outcomes by current observed state.</p>
            </div>
            <div class='text-right text-[11px] uppercase tracking-[0.2em] text-slate-500'>Wins / losses</div>
          </div>
          <svg viewBox='0 0 640 240' class='h-64 w-full rounded-2xl border border-white/10 bg-black/20 p-2'>
            <template x-for='bar in stackedBars(chartSeries.issue_outcomes || [])' :key='bar.day'>
              <g>
                <rect :x='bar.x' :y='bar.failureY' :width='bar.width' :height='bar.failureHeight' fill='#f87171'></rect>
                <rect :x='bar.x' :y='bar.successY' :width='bar.width' :height='bar.successHeight' fill='#34d399'></rect>
              </g>
            </template>
          </svg>
          <div class='mt-3 flex flex-wrap gap-2 text-xs'>
            <span class='rounded-full border border-emerald-300/30 bg-emerald-400/10 px-2 py-1 text-emerald-100'>Issue wins</span>
            <span class='rounded-full border border-rose-300/30 bg-rose-400/10 px-2 py-1 text-rose-100'>Issue losses</span>
          </div>
        </div>
      </div>
    </section>

    <section class='mb-6 rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-5 shadow-glow backdrop-blur'>
      <div class='flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between'>
        <div>
          <h2 class='text-xl font-semibold text-white'>Infra/Ops Deep Dive</h2>
          <p class='mt-1 text-sm text-slate-300'>Expanded diagnostics for canary, swarm routing, failure domains, and retry patterns.</p>
        </div>
        <button
          type='button'
          @click='showAdvancedMetrics = !showAdvancedMetrics'
          class='rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-slate-100 transition hover:bg-white/10'
          x-text='showAdvancedMetrics ? "Hide deep dive" : "Show deep dive"'
        ></button>
      </div>

      <div x-show='showAdvancedMetrics' x-transition.opacity class='mt-4 space-y-4'>
        <div class='grid grid-cols-2 gap-4 xl:grid-cols-6'>
          <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Canary First Pass</div>
            <div class='mt-3 text-3xl font-semibold text-emerald-300' x-text='canaryFirstPassRate'></div>
          </div>
          <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Canary No-op</div>
            <div class='mt-3 text-3xl font-semibold text-amber-300' x-text='canaryNoOpRate'></div>
          </div>
          <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Canary Wrong Root</div>
            <div class='mt-3 text-3xl font-semibold text-rose-300' x-text='canaryWrongRootRate'></div>
          </div>
          <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Canary Mean TTVP</div>
            <div class='mt-3 text-3xl font-semibold text-cyan-200' x-text='canaryMeanTimeToValidPr'></div>
          </div>
          <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Swarm Domain Skips</div>
            <div class='mt-3 text-3xl font-semibold text-slate-100' x-text='swarmDomainSkips'></div>
          </div>
          <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Native Recovery</div>
            <div class='mt-3 text-3xl font-semibold text-fuchsia-200' x-text='nativeRecoveryRate'></div>
          </div>
        </div>

        <div class='grid grid-cols-1 gap-4 xl:grid-cols-6'>
          <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Needs Clarification</div>
            <div class='mt-3 text-3xl font-semibold text-amber-200' x-text='needsClarificationIssues'></div>
          </div>
          <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Failure Domain Infra</div>
            <div class='mt-3 text-3xl font-semibold text-rose-200' x-text='failureDomainInfra'></div>
          </div>
          <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Failure Domain Contract</div>
            <div class='mt-3 text-3xl font-semibold text-orange-200' x-text='failureDomainContract'></div>
          </div>
          <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Retry Playbook Runs</div>
            <div class='mt-3 text-3xl font-semibold text-lime-200' x-text='retryPlaybookRuns'></div>
          </div>
          <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Retry Hotspot</div>
            <div class='mt-3 text-2xl font-semibold text-lime-100' x-text='retryPlaybookHotspot'></div>
          </div>
          <div class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-4 shadow-glow backdrop-blur'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>7d First-pass Delta</div>
            <div class='mt-3 text-3xl font-semibold text-cyan-100' x-text='firstPassTrend7d'></div>
          </div>
        </div>
      </div>
    </section>

    <section class='mb-6'>
      <div class='mb-3 flex items-center justify-between'>
        <h2 class='text-sm font-semibold uppercase tracking-[0.24em] text-slate-300'>Repo Trust</h2>
        <p class='text-xs text-slate-400'>One contract for trust state, score, rationale, and the next operator move.</p>
      </div>
      <div class='grid grid-cols-1 gap-4 xl:grid-cols-2'>
        <template x-for='row in rows' :key='`trust-${{row.repo || "unknown"}}`'>
          <article class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-5 shadow-glow backdrop-blur'>
            <div class='flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between'>
              <div>
                <div class='text-[11px] uppercase tracking-[0.24em] text-slate-500'>Repo</div>
                <h3 class='mt-2 text-lg font-semibold text-white' x-text='row.repo || "Unknown repo"'></h3>
                <p class='mt-2 text-sm text-slate-300' x-text='row.trust && row.trust.summary ? row.trust.summary : "Trust signals have not been computed yet."'></p>
              </div>
              <div class='flex flex-wrap items-center gap-2'>
                <span class='rounded-full border px-3 py-1 text-[11px] font-medium uppercase tracking-[0.2em]' :class='trustBadgeClass(row.trust && row.trust.state ? row.trust.state : "")' x-text='formatTrustState(row.trust && row.trust.state ? row.trust.state : "")'></span>
                <span class='rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] uppercase tracking-[0.2em] text-slate-300'>
                  Score <span class='font-semibold text-white' x-text='row.trust && Number.isFinite(Number(row.trust.score)) ? Number(row.trust.score) : 0'></span>
                </span>
              </div>
            </div>

            <div class='mt-4 grid grid-cols-1 gap-3 lg:grid-cols-4'>
              <div class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
                <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500'>Operator recommendation</div>
                <div class='mt-2 text-sm font-medium text-cyan-100' x-text='row.trust && row.trust.recommended_operator_action ? row.trust.recommended_operator_action : "observe_repo"'></div>
              </div>
              <div class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
                <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500'>Policy outcome</div>
                <div class='mt-2 text-sm font-medium text-amber-100' x-text='row.policy && row.policy.outcome ? row.policy.outcome : (row.trust && row.trust.policy_outcome ? row.trust.policy_outcome : "retry")'></div>
              </div>
              <div class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
                <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500'>Dominant failure domain</div>
                <div class='mt-2 text-sm font-medium text-white' x-text='row.trust && row.trust.dominant_failure_domain ? row.trust.dominant_failure_domain : "none"'></div>
              </div>
              <div class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
                <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500'>Open issues</div>
                <div class='mt-2 text-sm font-medium text-white' x-text='row.issues_total || 0'></div>
              </div>
            </div>

            <div class='mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2'>
              <div class='rounded-2xl border border-white/10 bg-slate-950/30 px-4 py-3'>
                <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500'>Why blocked</div>
                <p class='mt-2 text-sm text-slate-200' x-text='row.trust && row.trust.why_blocked ? row.trust.why_blocked : "No active blocker is recorded."'></p>
              </div>
              <div class='rounded-2xl border border-white/10 bg-slate-950/30 px-4 py-3'>
                <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500'>Why runnable</div>
                <p class='mt-2 text-sm text-slate-200' x-text='row.trust && row.trust.why_runnable ? row.trust.why_runnable : "No runnable rationale is currently exposed."'></p>
              </div>
              <div class='rounded-2xl border border-white/10 bg-slate-950/30 px-4 py-3 lg:col-span-2'>
                <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500'>Policy summary</div>
                <p class='mt-2 text-sm text-slate-200' x-text='row.policy && row.policy.summary ? row.policy.summary : "No policy summary is currently exposed."'></p>
              </div>
            </div>
          </article>
        </template>
      </div>
    </section>

    <section class='mb-6'>
      <div class='mb-3 flex items-center justify-between'>
        <h2 class='text-sm font-semibold uppercase tracking-[0.24em] text-slate-300'>Issue Why / Why Not</h2>
        <p class='text-xs text-slate-400'>Per-issue reason codes and next actions derived from current issue state and repo trust.</p>
      </div>
      <div class='grid grid-cols-1 gap-4 xl:grid-cols-2'>
        <template x-for='row in rows' :key='`issue-why-${{row.repo || "unknown"}}`'>
          <article class='rounded-[28px] border border-white/10 bg-slate-900/70 px-5 py-5 shadow-glow backdrop-blur'>
            <div class='flex items-center justify-between gap-3'>
              <div>
                <div class='text-[11px] uppercase tracking-[0.24em] text-slate-500'>Repo</div>
                <h3 class='mt-2 text-lg font-semibold text-white' x-text='row.repo || "Unknown repo"'></h3>
              </div>
              <span class='rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] uppercase tracking-[0.2em] text-slate-300'>
                Items <span class='font-semibold text-white' x-text='(row.issue_explanations || []).length'></span>
              </span>
            </div>

            <div class='mt-4 space-y-3' x-show='(row.issue_explanations || []).length'>
              <template x-for='item in (row.issue_explanations || [])' :key='`issue-expl-${{row.repo || "unknown"}}-${{item.issue_id || item.reason_code || "item"}}`'>
                <div class='rounded-2xl border border-white/10 bg-slate-950/35 px-4 py-3'>
                  <div class='flex flex-wrap items-center gap-2'>
                    <span class='rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.2em] text-slate-100' x-text='item.issue_id ? `#${{item.issue_id}}` : "Issue"'></span>
                    <span class='rounded-full border px-3 py-1 text-[11px] font-medium uppercase tracking-[0.2em]' :class='reasonBadgeClass(item.reason_code || "")' x-text='formatIssueReasonCode(item.reason_code || "")'></span>
                    <span class='rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] uppercase tracking-[0.2em] text-slate-300' x-text='item.state || "unknown"'></span>
                  </div>
                  <p class='mt-3 text-sm text-slate-200' x-text='item.summary || "No issue-level explanation is recorded."'></p>
                  <div class='mt-3 text-[11px] uppercase tracking-[0.2em] text-slate-500'>Recommended action</div>
                  <p class='mt-1 text-sm font-medium text-cyan-100' x-text='item.recommended_action || "observe_issue"'></p>
                </div>
              </template>
            </div>
            <p class='mt-4 text-sm text-slate-400' x-show='!(row.issue_explanations || []).length'>No tracked issues currently need an issue-level explanation.</p>
          </article>
        </template>
      </div>
    </section>

    <section class='mb-6'>
      <div class='mb-3 flex items-center justify-between'>
        <h2 class='text-sm font-semibold uppercase tracking-[0.24em] text-slate-300'>Repo Controls</h2>
        <p class='text-xs text-slate-400'>Inline ops stay available, but the main surface now prioritizes investigation.</p>
      </div>
      <div class='grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3'>
        {repo_actions}
      </div>
    </section>

    <section class='rounded-[32px] border border-white/10 bg-slate-900/80 shadow-glow backdrop-blur'>
      <div class='border-b border-white/10 px-5 py-5'>
        <div class='flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between'>
          <div>
            <h2 class='text-xl font-semibold text-white'>Activity Table</h2>
            <p class='mt-1 text-sm text-slate-400'>Parsed rows across commands, attempts, and runtime logs. Click any row for full context.</p>
          </div>
          <div class='flex flex-wrap gap-2'>
            <template x-for='tab in kindTabs' :key='tab.value'>
              <button
                type='button'
                @click='kindFilter = tab.value'
                :class='kindFilter === tab.value ? "bg-cyan-400/20 text-cyan-100 border-cyan-300/40" : "bg-white/5 text-slate-300 border-white/10 hover:bg-white/10"'
                class='rounded-full border px-3 py-2 text-xs font-medium transition'
                x-text='tab.label'
              ></button>
            </template>
          </div>
        </div>

        <div class='mt-5 grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1.4fr)_220px_220px_auto]'>
          <label class='rounded-2xl border border-white/10 bg-white/5 px-3 py-2'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-500'>Search</div>
            <input x-model='searchText' type='text' placeholder='Issue id, branch, subsystem, summary...' class='mt-2 w-full bg-transparent text-sm text-white outline-none placeholder:text-slate-500'>
          </label>
          <label class='rounded-2xl border border-white/10 bg-white/5 px-3 py-2'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-500'>Repo</div>
            <select x-model='repoFilter' class='mt-2 w-full bg-transparent text-sm text-white outline-none'>
              <option value=''>All repos</option>
              {repo_options}
            </select>
          </label>
          <label class='rounded-2xl border border-white/10 bg-white/5 px-3 py-2'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-500'>Signal</div>
            <select x-model='signalFilter' class='mt-2 w-full bg-transparent text-sm text-white outline-none'>
              <option value=''>Any signal</option>
              <option value='failure'>Failure / error</option>
              <option value='running'>Running / pending</option>
              <option value='ok'>Healthy / complete</option>
            </select>
          </label>
          <button type='button' @click='clearFilters()' class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-slate-200 transition hover:bg-white/10'>
            Clear filters
          </button>
        </div>
      </div>

      <div class='px-5 py-4'>
        <div class='mb-3 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-400'>
          <div x-text='activitySummary'></div>
          <div x-text='lastUpdatedLabel'></div>
        </div>

        <div class='overflow-hidden rounded-[28px] border border-white/10'>
          <div class='max-h-[760px] overflow-auto'>
            <table class='min-w-full divide-y divide-white/10 text-sm'>
              <thead class='sticky top-0 z-10 bg-slate-950/95 backdrop-blur'>
                <tr class='text-left text-[11px] uppercase tracking-[0.24em] text-slate-500'>
                  <th class='px-4 py-3 font-medium'>Time</th>
                  <th class='px-4 py-3 font-medium'>Type</th>
                  <th class='px-4 py-3 font-medium'>Repo</th>
                  <th class='px-4 py-3 font-medium'>Context</th>
                  <th class='px-4 py-3 font-medium'>Subsystem</th>
                  <th class='px-4 py-3 font-medium'>Summary</th>
                  <th class='px-4 py-3 font-medium'>Signal</th>
                </tr>
              </thead>
              <tbody class='divide-y divide-white/5'>
                <template x-for='item in filteredActivities' :key='item.id'>
                  <tr
                    @click='openInspector(item.id)'
                    :class='selectedActivityId === item.id ? "bg-cyan-400/10" : "bg-slate-950/20 hover:bg-white/5"'
                    class='cursor-pointer transition'
                  >
                    <td class='px-4 py-3 align-top text-xs text-slate-400' x-text='item.timestamp || "Unknown"'></td>
                    <td class='px-4 py-3 align-top'>
                      <span class='rounded-full border px-2 py-1 text-[11px] font-medium uppercase tracking-[0.2em]' :class='kindBadgeClass(item.kind)' x-text='item.kind'></span>
                    </td>
                    <td class='px-4 py-3 align-top text-slate-200' x-text='item.repo || "—"'></td>
                    <td class='px-4 py-3 align-top text-xs text-slate-300'>
                      <div class='flex flex-wrap gap-1.5'>
                        <template x-if='item.issue_id'><span class='rounded-full bg-white/5 px-2 py-1' x-text='`Issue #${{item.issue_id}}`'></span></template>
                        <template x-if='item.pr_id'><span class='rounded-full bg-white/5 px-2 py-1' x-text='`PR #${{item.pr_id}}`'></span></template>
                        <template x-if='item.attempt_id'><span class='rounded-full bg-white/5 px-2 py-1 font-mono' x-text='item.attempt_id'></span></template>
                      </div>
                    </td>
                    <td class='px-4 py-3 align-top text-xs text-slate-400' x-text='item.subsystem || item.source_file || "—"'></td>
                    <td class='max-w-[520px] px-4 py-3 align-top text-sm text-slate-100'>
                      <div class='line-clamp-2' x-text='item.summary'></div>
                    </td>
                    <td class='px-4 py-3 align-top'>
                      <span class='rounded-full border px-2 py-1 text-[11px] font-medium uppercase tracking-[0.2em]' :class='signalBadgeClass(item.signal)' x-text='item.signal || "info"'></span>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>

            <div x-show='!filteredActivities.length' class='px-6 py-16 text-center'>
              <div class='mx-auto max-w-md rounded-[28px] border border-dashed border-white/10 bg-white/[0.03] px-6 py-8'>
                <div class='text-sm font-medium text-white'>No activity matched these filters.</div>
                <p class='mt-2 text-sm text-slate-400'>Try widening the repo or signal filter, or clear search text.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class='mt-6 lg:hidden'>
      <div class='mb-3 flex items-center justify-between'>
        <h2 class='text-sm font-semibold uppercase tracking-[0.24em] text-slate-300'>Activity Cards</h2>
        <p class='text-xs text-slate-400'>Tap any card for full context.</p>
      </div>
      <div class='grid grid-cols-1 gap-3'>
        <template x-for='item in filteredActivities' :key='`mobile-${{item.id}}`'>
          <button
            type='button'
            @click='openInspector(item.id)'
            class='w-full rounded-3xl border border-white/10 bg-slate-900/70 p-4 text-left transition hover:bg-white/5'
          >
            <div class='flex items-start justify-between gap-3'>
              <div>
                <div class='text-xs text-slate-400' x-text='item.timestamp || "Unknown"'></div>
                <div class='mt-2 text-sm font-medium text-white line-clamp-2' x-text='item.summary'></div>
              </div>
              <span class='rounded-full border px-2 py-1 text-[11px] font-medium uppercase tracking-[0.2em]' :class='signalBadgeClass(item.signal)' x-text='item.signal || "info"'></span>
            </div>
            <div class='mt-3 flex flex-wrap gap-2 text-xs'>
              <span class='rounded-full border px-2 py-1' :class='kindBadgeClass(item.kind)' x-text='item.kind'></span>
              <template x-if='item.repo'><span class='rounded-full border border-white/10 bg-white/5 px-2 py-1 text-slate-300' x-text='item.repo'></span></template>
              <template x-if='item.issue_id'><span class='rounded-full border border-white/10 bg-white/5 px-2 py-1 text-slate-300' x-text='`Issue #${{item.issue_id}}`'></span></template>
            </div>
          </button>
        </template>
      </div>
      <div x-show='!filteredActivities.length' class='mt-3 rounded-3xl border border-dashed border-white/10 bg-white/[0.03] p-4 text-center text-sm text-slate-400'>
        No activity matched these filters.
      </div>
    </section>

    <template x-if='selectedActivity'>
      <div class='fixed inset-0 z-40'>
        <div class='absolute inset-0 bg-slate-950/70 backdrop-blur-sm' @click='closeInspector()'></div>
        <aside class='absolute inset-y-0 right-0 flex w-full max-w-3xl flex-col border-l border-white/10 bg-slate-950/95 shadow-2xl shadow-slate-950/80'>
          <div class='flex items-start justify-between border-b border-white/10 px-5 py-5'>
            <div class='pr-4'>
              <div class='flex flex-wrap items-center gap-2'>
                <span class='rounded-full border px-2 py-1 text-[11px] font-medium uppercase tracking-[0.2em]' :class='kindBadgeClass(selectedActivity.kind)' x-text='selectedActivity.kind'></span>
                <span class='rounded-full border px-2 py-1 text-[11px] font-medium uppercase tracking-[0.2em]' :class='signalBadgeClass(selectedActivity.signal)' x-text='selectedActivity.signal || "info"'></span>
              </div>
              <h3 class='mt-3 text-xl font-semibold text-white' x-text='selectedActivity.summary'></h3>
              <p class='mt-2 text-sm text-slate-400' x-text='selectedActivity.timestamp'></p>
            </div>
            <button type='button' @click='closeInspector()' class='rounded-full border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-300 transition hover:bg-white/10'>
              Close
            </button>
          </div>

          <div class='flex-1 overflow-y-auto px-5 py-5'>
            <section class='mb-5 rounded-[28px] border border-white/10 bg-white/[0.03] p-4'>
              <h4 class='text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400'>Context</h4>
              <div class='mt-3 flex flex-wrap gap-2 text-xs'>
                <template x-for='chip in contextChips(selectedActivity)' :key='chip.label + chip.value'>
                  <div class='rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-slate-200'>
                    <span class='text-slate-400' x-text='`${{chip.label}}:`'></span>
                    <span class='ml-1 font-medium' x-text='chip.value'></span>
                  </div>
                </template>
              </div>
            </section>

            <section class='mb-5 rounded-[28px] border border-white/10 bg-white/[0.03] p-4'>
              <div class='flex flex-wrap gap-2'>
                <button type='button' @click='copyText(selectedActivity.raw_text || selectedActivity.summary || "")' class='rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-slate-100 transition hover:bg-white/10'>
                  Copy full text
                </button>
                <template x-if='selectedActivity.issue_id'>
                  <button type='button' @click='copyText(String(selectedActivity.issue_id))' class='rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-slate-100 transition hover:bg-white/10'>
                    Copy issue id
                  </button>
                </template>
                <template x-if='selectedActivity.attempt_id'>
                  <button type='button' @click='copyText(selectedActivity.attempt_id)' class='rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-slate-100 transition hover:bg-white/10'>
                    Copy attempt id
                  </button>
                </template>
                <template x-for='link in selectedActivity.jump_urls || []' :key='link.url'>
                  <a :href='link.url' target='_blank' rel='noreferrer' class='rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-2 text-xs font-medium text-cyan-100 transition hover:bg-cyan-400/20' x-text='link.label'></a>
                </template>
              </div>
            </section>

            <section class='mb-5 rounded-[28px] border border-white/10 bg-white/[0.03] p-4'>
              <h4 class='text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400'>Structured Detail</h4>
              <dl class='mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2'>
                <template x-for='entry in detailEntries(selectedActivity)' :key='entry.label'>
                  <div class='rounded-2xl border border-white/5 bg-slate-900/50 px-3 py-3'>
                    <dt class='text-[11px] uppercase tracking-[0.2em] text-slate-500' x-text='entry.label'></dt>
                    <dd class='mt-2 break-words text-sm text-slate-100' x-text='entry.value'></dd>
                  </div>
                </template>
              </dl>
            </section>

            <section class='rounded-[28px] border border-white/10 bg-slate-950/80 p-4'>
              <h4 class='text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400'>Raw Text</h4>
              <pre class='mt-4 max-h-[420px] overflow-auto whitespace-pre-wrap rounded-2xl border border-white/5 bg-black/30 p-4 font-mono text-xs leading-6 text-slate-200' x-text='selectedActivity.raw_text || "No raw text available."'></pre>
            </section>
          </div>
        </aside>
      </div>
    </template>
  </main>

  <script id='initial-data' type='application/json'>{initial}</script>
  <script>
    function dashboardApp() {{
      return {{
        rows: [],
        activity: [],
        logs: [],
        logEvents: [],
        activeActions: '',
        refreshMs: {_REFRESH_MS},
        kindFilter: 'all',
        repoFilter: '',
        signalFilter: '',
        searchText: '',
        selectedActivityId: '',
        selectedActivitySnapshot: null,
        generatedAt: '',
        logFiles: [],
        scoreboard: {{}},
        scoreExplainer: {{ formula_rows: [], samples: {{}}, definitions: {{}} }},
        chartSeries: {{ reliability: [], issue_outcomes: [] }},
        showAdvancedMetrics: false,
        showTelemetryCharts: false,
        showScoreExplainer: false,
        themeMode: 'dark',
        kindTabs: [
          {{ value: 'all', label: 'All activity' }},
          {{ value: 'log', label: 'Logs' }},
          {{ value: 'command', label: 'Commands' }},
          {{ value: 'attempt', label: 'Attempts' }}
        ],

        get totalIssues() {{
          return this.rows.reduce((acc, row) => acc + Number(row.issues_total || 0), 0);
        }},

        get pausedRepos() {{
          return this.rows.filter((row) => !!row.paused).length;
        }},

        get canaryFirstPassRate() {{
          const values = this.rows
            .map((row) => Number((row.reliability_canary || {{}}).first_pass_success_rate || 0))
            .filter((value) => !Number.isNaN(value));
          if (!values.length) return '0.0%';
          const avg = values.reduce((acc, value) => acc + value, 0) / values.length;
          return `${{(avg * 100).toFixed(1)}}%`;
        }},

        get canaryNoOpRate() {{
          const values = this.rows
            .map((row) => Number((row.reliability_canary || {{}}).no_op_rate || 0))
            .filter((value) => !Number.isNaN(value));
          if (!values.length) return '0.0%';
          const avg = values.reduce((acc, value) => acc + value, 0) / values.length;
          return `${{(avg * 100).toFixed(1)}}%`;
        }},

        get canaryWrongRootRate() {{
          const values = this.rows
            .map((row) => Number((row.reliability_canary || {{}}).wrong_root_execution_rate || 0))
            .filter((value) => !Number.isNaN(value));
          if (!values.length) return '0.0%';
          const avg = values.reduce((acc, value) => acc + value, 0) / values.length;
          return `${{(avg * 100).toFixed(1)}}%`;
        }},

        get canaryMeanTimeToValidPr() {{
          const values = this.rows
            .map((row) => Number((row.reliability_canary || {{}}).mean_time_to_valid_pr_minutes || 0))
            .filter((value) => !Number.isNaN(value));
          if (!values.length) return '0.00m';
          const avg = values.reduce((acc, value) => acc + value, 0) / values.length;
          return `${{avg.toFixed(2)}}m`;
        }},

        get swarmDomainSkips() {{
          return this.rows.reduce((acc, row) => acc + Number((row.swarm_metrics || {{}}).skipped_domain || 0), 0);
        }},

        get nativeRecoveryRate() {{
          const aggregate = this.rows.reduce((acc, row) => {{
            const metrics = row.codex_native_multi_agent_metrics || {{}};
            acc.attempts += Number(metrics.recovery_attempts || 0);
            acc.success += Number(metrics.recovery_success || 0);
            return acc;
          }}, {{ attempts: 0, success: 0 }});
          if (!aggregate.attempts) return '0/0';
          return `${{aggregate.success}}/${{aggregate.attempts}}`;
        }},

        get needsClarificationIssues() {{
          return this.rows.reduce((acc, row) => acc + Number((row.state_counts || {{}}).needs_clarification || 0), 0);
        }},

        get failureDomainInfra() {{
          return this.rows.reduce((acc, row) => acc + Number((row.failure_domain_metrics || {{}}).infra || 0), 0);
        }},

        get failureDomainContract() {{
          return this.rows.reduce((acc, row) => acc + Number((row.failure_domain_metrics || {{}}).contract || 0), 0);
        }},

        get retryPlaybookRuns() {{
          return this.rows.reduce((acc, row) => acc + Number((row.retry_playbook_metrics || {{}}).total || 0), 0);
        }},

        get retryPlaybookHotspot() {{
          const domainCounts = this.rows.reduce((acc, row) => {{
            const domains = ((row.retry_playbook_metrics || {{}}).domain_counts || {{}});
            for (const [domain, count] of Object.entries(domains)) {{
              acc[domain] = (acc[domain] || 0) + Number(count || 0);
            }}
            return acc;
          }}, {{}});
          const entries = Object.entries(domainCounts).sort((a, b) => (Number(b[1]) - Number(a[1])) || String(a[0]).localeCompare(String(b[0])));
          if (!entries.length) return 'none';
          const [domain, count] = entries[0];
          return `${{domain}} (${{count}})`;
        }},

        get firstPassTrend7d() {{
          const values = this.rows
            .map((row) => Number((((row.reliability_trends || {{}})['7d'] || {{}}).changes || {{}}).first_pass_success_rate || 0))
            .filter((value) => !Number.isNaN(value));
          if (!values.length) return '0.0pp';
          const avg = values.reduce((acc, value) => acc + value, 0) / values.length;
          const pp = avg * 100;
          return `${{pp >= 0 ? '+' : ''}}${{pp.toFixed(1)}}pp`;
        }},

        get activeAttempts() {{
          return this.activity.filter((item) => item.kind === 'attempt' && ['running', 'pending'].includes((item.signal || '').toLowerCase())).length;
        }},

        get failureCount() {{
          return this.activity.filter((item) => ['failure', 'error'].includes((item.signal || '').toLowerCase())).length;
        }},

        get filteredActivities() {{
          let sourceRows = this.activity;
          if (this.kindFilter === 'log') {{
            sourceRows = this.logEvents;
          }}
          const search = (this.searchText || '').trim().toLowerCase();
          return sourceRows.filter((item) => {{
            if (this.kindFilter !== 'all' && item.kind !== this.kindFilter) {{
              return false;
            }}
            if (this.repoFilter && item.repo !== this.repoFilter) {{
              return false;
            }}
            if (this.signalFilter && !this.matchesSignalFilter(item, this.signalFilter)) {{
              return false;
            }}
            if (!search) {{
              return true;
            }}
            const haystack = [
              item.summary,
              item.raw_text,
              item.repo,
              item.subsystem,
              item.issue_id,
              item.pr_id,
              item.attempt_id,
              item.branch
            ].join(' ').toLowerCase();
            return haystack.includes(search);
          }});
        }},

        get selectedActivity() {{
          if (!this.selectedActivityId) {{
            return null;
          }}
          return this.activity.find((item) => item.id === this.selectedActivityId)
            || this.logEvents.find((item) => item.id === this.selectedActivityId)
            || this.selectedActivitySnapshot;
        }},

        get activitySummary() {{
          return `${{this.filteredActivities.length}} visible rows • ${{this.activity.length}} total in memory`;
        }},

        get lastUpdatedLabel() {{
          return this.generatedAt ? `Updated ${{this.generatedAt}}` : 'Waiting for data';
        }},

        get logFilesLabel() {{
          return this.logFiles.length ? this.logFiles.length : '0';
        }},

        kindBadgeClass(kind) {{
          const lower = String(kind || '').toLowerCase();
          if (lower === 'log') return 'border-rose-300/30 bg-rose-400/10 text-rose-100';
          if (lower === 'command') return 'border-cyan-300/30 bg-cyan-400/10 text-cyan-100';
          if (lower === 'attempt') return 'border-amber-300/30 bg-amber-400/10 text-amber-100';
          return 'border-white/10 bg-white/5 text-slate-200';
        }},

        signalBadgeClass(signal) {{
          const lower = String(signal || '').toLowerCase();
          if (['failure', 'error'].includes(lower)) return 'border-rose-300/30 bg-rose-400/10 text-rose-100';
          if (['running', 'pending'].includes(lower)) return 'border-amber-300/30 bg-amber-400/10 text-amber-100';
          if (['ok', 'completed'].includes(lower)) return 'border-emerald-300/30 bg-emerald-400/10 text-emerald-100';
          return 'border-white/10 bg-white/5 text-slate-200';
        }},

        trustBadgeClass(state) {{
          const lower = String(state || '').toLowerCase();
          if (lower === 'ready') return 'border-emerald-300/30 bg-emerald-400/10 text-emerald-100';
          if (lower === 'degraded') return 'border-amber-300/30 bg-amber-400/10 text-amber-100';
          if (lower === 'paused') return 'border-slate-300/30 bg-slate-400/10 text-slate-100';
          if (lower === 'quarantined') return 'border-rose-300/30 bg-rose-400/10 text-rose-100';
          if (lower === 'needs_environment_fix') return 'border-orange-300/30 bg-orange-400/10 text-orange-100';
          if (lower === 'needs_contract_fix') return 'border-fuchsia-300/30 bg-fuchsia-400/10 text-fuchsia-100';
          return 'border-white/10 bg-white/5 text-slate-200';
        }},

        reasonBadgeClass(code) {{
          const lower = String(code || '').toLowerCase();
          if (['eligible', 'actively_processing', 'resolved', 'pr_open', 'awaiting_pr_approval'].includes(lower)) {{
            return 'border-emerald-300/30 bg-emerald-400/10 text-emerald-100';
          }}
          if (['repo_paused', 'circuit_breaker_open', 'environment_blocked', 'needs_clarification', 'backoff_active', 'last_attempt_failed'].includes(lower)) {{
            return 'border-amber-300/30 bg-amber-400/10 text-amber-100';
          }}
          return 'border-white/10 bg-white/5 text-slate-200';
        }},

        formatTrustState(state) {{
          const lower = String(state || '').trim().toLowerCase();
          if (!lower) return 'Unknown';
          return lower
            .split('_')
            .map((part) => part ? `${{part.charAt(0).toUpperCase()}}${{part.slice(1)}}` : '')
            .join(' ');
        }},

        formatIssueReasonCode(code) {{
          const lower = String(code || '').trim().toLowerCase();
          if (!lower) return 'Unknown';
          return lower
            .split('_')
            .map((part) => part ? `${{part.charAt(0).toUpperCase()}}${{part.slice(1)}}` : '')
            .join(' ');
        }},

        matchesSignalFilter(item, filterValue) {{
          const signal = String(item.signal || '').toLowerCase();
          if (filterValue === 'failure') return ['failure', 'error'].includes(signal);
          if (filterValue === 'running') return ['running', 'pending'].includes(signal);
          if (filterValue === 'ok') return ['ok', 'completed'].includes(signal);
          return true;
        }},

        async init() {{
          this.initTheme();
          try {{
            const script = document.getElementById('initial-data');
            if (script) {{
              const initial = JSON.parse(script.textContent || '{{}}');
              this.updateFromPayload(initial);
            }}
          }} catch (error) {{
            console.error('Failed to parse initial payload', error);
          }}
          setInterval(() => this.refresh(), this.refreshMs);
        }},

        initTheme() {{
          let mode = 'dark';
          try {{
            const stored = localStorage.getItem('flow-healer-theme');
            if (stored === 'light' || stored === 'dark') {{
              mode = stored;
            }}
          }} catch (_error) {{
            mode = 'dark';
          }}
          this.themeMode = mode;
          this.applyTheme();
        }},

        applyTheme() {{
          document.documentElement.setAttribute('data-theme', this.themeMode);
        }},

        toggleTheme() {{
          this.themeMode = this.themeMode === 'dark' ? 'light' : 'dark';
          this.applyTheme();
          try {{
            localStorage.setItem('flow-healer-theme', this.themeMode);
          }} catch (_error) {{
            console.warn('Theme preference could not be saved');
          }}
        }},

        async refresh() {{
          try {{
            const response = await fetch('/api/overview', {{ cache: 'no-store' }});
            if (!response.ok) return;
            const payload = await response.json();
            this.updateFromPayload(payload);
          }} catch (error) {{
            console.error('Failed to refresh dashboard', error);
          }}
        }},

        updateFromPayload(payload) {{
          this.rows = Array.isArray(payload.rows) ? payload.rows : [];
          this.activity = Array.isArray(payload.activity) ? payload.activity : [];
          const logsData = payload.logs || {{}};
          this.logs = Array.isArray(logsData.lines) ? logsData.lines : [];
          this.logEvents = Array.isArray(logsData.events) ? logsData.events : [];
          this.logFiles = Array.isArray(logsData.files) ? logsData.files : [];
          this.scoreboard = payload.scoreboard || {{}};
          this.scoreExplainer = payload.score_explainer || {{ formula_rows: [], samples: {{}}, definitions: {{}} }};
          this.chartSeries = payload.chart_series || {{ reliability: [], issue_outcomes: [] }};
          this.generatedAt = payload.generated_at || '';
          if (this.selectedActivityId) {{
            const live = this.activity.find((item) => item.id === this.selectedActivityId)
              || this.logEvents.find((item) => item.id === this.selectedActivityId);
            if (live) {{
              this.selectedActivitySnapshot = live;
            }}
          }}
        }},

        openInspector(id) {{
          this.selectedActivityId = id;
          this.selectedActivitySnapshot = this.activity.find((item) => item.id === id)
            || this.logEvents.find((item) => item.id === id)
            || null;
        }},

        closeInspector() {{
          this.selectedActivityId = '';
          this.selectedActivitySnapshot = null;
        }},

        clearFilters() {{
          this.kindFilter = 'all';
          this.repoFilter = '';
          this.signalFilter = '';
          this.searchText = '';
        }},

        async copyText(value) {{
          const text = String(value || '');
          if (!text) return;
          try {{
            await navigator.clipboard.writeText(text);
          }} catch (_error) {{
            console.warn('Clipboard write failed');
          }}
        }},

        formatCurrency(value) {{
          const amount = Number(value || 0);
          const rounded = Number.isFinite(amount) ? Math.max(0, amount) : 0;
          return new Intl.NumberFormat('en-US', {{
            style: 'currency',
            currency: 'USD',
            maximumFractionDigits: 0,
          }}).format(rounded);
        }},

        formatPercent(value) {{
          const numeric = Number(value || 0);
          if (!Number.isFinite(numeric)) return '0.0%';
          return `${{(numeric * 100).toFixed(1)}}%`;
        }},

        signedNumber(value) {{
          const numeric = Number(value || 0);
          if (!Number.isFinite(numeric)) return '+0';
          return `${{numeric >= 0 ? '+' : ''}}${{Math.round(numeric)}}`;
        }},

        linePoints(series, key) {{
          const rows = Array.isArray(series) ? series : [];
          if (!rows.length) return '0,210 640,210';
          const width = 600;
          const height = 180;
          const insetX = 20;
          const insetY = 20;
          const spanX = rows.length > 1 ? width / (rows.length - 1) : 0;
          return rows.map((row, index) => {{
            const value = Math.max(0, Math.min(1, Number(row[key] || 0)));
            const x = insetX + (spanX * index);
            const y = insetY + ((1 - value) * height);
            return `${{x.toFixed(1)}},${{y.toFixed(1)}}`;
          }}).join(' ');
        }},

        stackedBars(series) {{
          const rows = Array.isArray(series) ? series : [];
          if (!rows.length) return [];
          const width = 600;
          const maxTotal = Math.max(...rows.map((row) => Number(row.total || 0)), 1);
          const barWidth = Math.max(8, Math.floor(width / Math.max(rows.length, 1)) - 6);
          return rows.map((row, index) => {{
            const total = Number(row.total || 0);
            const success = Number(row.success || 0);
            const failure = Number(row.failure || 0);
            const x = 20 + (index * (barWidth + 6));
            const scaledTotal = total > 0 ? (total / maxTotal) * 180 : 0;
            const failureHeight = total > 0 ? (failure / total) * scaledTotal : 0;
            const successHeight = total > 0 ? (success / total) * scaledTotal : 0;
            const baseline = 210;
            return {{
              day: row.day || `${{index}}`,
              x,
              width: barWidth,
              failureHeight,
              successHeight,
              failureY: baseline - failureHeight,
              successY: baseline - failureHeight - successHeight,
            }};
          }});
        }},

        contextChips(item) {{
          return [
            item.repo ? {{ label: 'Repo', value: item.repo }} : null,
            item.issue_id ? {{ label: 'Issue', value: `#${{item.issue_id}}` }} : null,
            item.pr_id ? {{ label: 'PR', value: `#${{item.pr_id}}` }} : null,
            item.attempt_id ? {{ label: 'Attempt', value: item.attempt_id }} : null,
            item.branch ? {{ label: 'Branch', value: item.branch }} : null,
            item.source_file ? {{ label: 'File', value: item.source_file }} : null
          ].filter(Boolean);
        }},

        detailEntries(item) {{
          return [
            {{ label: 'Timestamp', value: item.timestamp || 'Unknown' }},
            {{ label: 'Type', value: item.kind || 'Unknown' }},
            {{ label: 'Signal', value: item.signal || 'info' }},
            {{ label: 'Subsystem', value: item.subsystem || '—' }},
            {{ label: 'Status', value: item.status || '—' }},
            {{ label: 'Level', value: item.level || '—' }},
            {{ label: 'Raw source', value: item.source_file || '—' }},
            {{ label: 'Message', value: item.message || item.summary || '—' }}
          ];
        }}
      }};
    }}
  </script>
</body>
</html>
"""


def _overview_payload(config: AppConfig, service: FlowHealerService) -> dict[str, Any]:
    logs = _collect_recent_logs(config, max_lines=160)
    status_rows = service.cached_status_rows(None)
    scoreboard = _build_scoreboard(status_rows)
    return {
        "rows": status_rows,
        "commands": service.control_command_rows(None, limit=120),
        "logs": logs,
        "activity": _collect_activity(
            config,
            service,
            logs=logs,
            limit=_ACTIVITY_LIMIT,
            status_rows=status_rows,
        ),
        "scoreboard": scoreboard,
        "score_explainer": _build_score_explainer(scoreboard),
        "chart_series": _build_chart_series(status_rows),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
    }


def _build_scoreboard(status_rows: list[dict[str, Any]]) -> dict[str, Any]:
    issue_successes = 0
    issue_failures = 0
    active_issues = 0
    recent_terminal_outcomes: list[dict[str, Any]] = []
    weighted_first_pass_total = 0.0
    weighted_issue_total = 0
    weighted_no_op_total = 0.0
    weighted_wrong_root_total = 0.0
    weighted_attempt_sample_total = 0

    for row in status_rows:
        outcomes = row.get("issue_outcomes") or {}
        issue_successes += int(outcomes.get("success") or 0)
        issue_failures += int(outcomes.get("failure") or 0)
        active_issues += int(outcomes.get("active") or 0)
        recent_terminal_outcomes.extend(outcomes.get("recent_terminal_outcomes") or [])

        canary = row.get("reliability_canary") or {}
        issue_count = int(canary.get("issue_count") or 0)
        sample_size = int(canary.get("sample_size") or 0)
        weighted_issue_total += issue_count
        weighted_attempt_sample_total += sample_size
        weighted_first_pass_total += float(canary.get("first_pass_success_rate") or 0.0) * float(issue_count)
        weighted_no_op_total += float(canary.get("no_op_rate") or 0.0) * float(sample_size)
        weighted_wrong_root_total += float(canary.get("wrong_root_execution_rate") or 0.0) * float(sample_size)

    recent_terminal_outcomes.sort(
        key=lambda item: (str(item.get("updated_at") or ""), str(item.get("issue_id") or "")),
        reverse=True,
    )
    current_success_streak = 0
    for item in recent_terminal_outcomes:
        if str(item.get("outcome") or "") != "success":
            break
        current_success_streak += 1

    terminal_total = issue_successes + issue_failures
    win_rate = float(issue_successes) / float(max(1, terminal_total)) if terminal_total else 0.0
    first_pass_success_rate = (
        weighted_first_pass_total / float(max(1, weighted_issue_total))
        if weighted_issue_total
        else 0.0
    )
    no_op_rate = (
        weighted_no_op_total / float(max(1, weighted_attempt_sample_total))
        if weighted_attempt_sample_total
        else 0.0
    )
    wrong_root_rate = (
        weighted_wrong_root_total / float(max(1, weighted_attempt_sample_total))
        if weighted_attempt_sample_total
        else 0.0
    )
    points = _compute_agent_points(
        issue_successes=issue_successes,
        issue_failures=issue_failures,
        first_pass_success_rate=first_pass_success_rate,
        no_op_rate=no_op_rate,
        wrong_root_rate=wrong_root_rate,
        current_success_streak=current_success_streak,
    )
    xp_in_level = points % 1000
    return {
        "issue_successes": issue_successes,
        "issue_failures": issue_failures,
        "active_issues": active_issues,
        "terminal_total": terminal_total,
        "win_rate": round(win_rate, 4),
        "first_pass_success_rate": round(first_pass_success_rate, 4),
        "no_op_rate": round(no_op_rate, 4),
        "wrong_root_rate": round(wrong_root_rate, 4),
        "current_success_streak": current_success_streak,
        "agent_points": points,
        "agent_level": int(points / 1000) + 1,
        "xp_in_level": xp_in_level,
        "xp_to_next": 1000 - xp_in_level if xp_in_level else 1000,
        "xp_progress_pct": round((xp_in_level / 1000.0) * 100.0, 2),
        "sample_issue_count": weighted_issue_total,
        "sample_attempt_count": weighted_attempt_sample_total,
        "recent_terminal_outcomes": recent_terminal_outcomes[:25],
    }


def _compute_agent_points(
    *,
    issue_successes: int,
    issue_failures: int,
    first_pass_success_rate: float,
    no_op_rate: float,
    wrong_root_rate: float,
    current_success_streak: int,
) -> int:
    values = {
        "issue_successes": float(issue_successes),
        "issue_failures": float(issue_failures),
        "first_pass_success_rate": float(first_pass_success_rate),
        "no_op_rate": float(no_op_rate),
        "wrong_root_rate": float(wrong_root_rate),
        "current_success_streak": float(current_success_streak),
    }
    score = 0.0
    for key, _label, weight in _POINT_WEIGHTS:
        score += values.get(key, 0.0) * float(weight)
    return max(0, int(round(score)))


def _build_score_explainer(scoreboard: dict[str, Any]) -> dict[str, Any]:
    values = {
        "issue_successes": float(scoreboard.get("issue_successes") or 0),
        "issue_failures": float(scoreboard.get("issue_failures") or 0),
        "first_pass_success_rate": float(scoreboard.get("first_pass_success_rate") or 0.0),
        "no_op_rate": float(scoreboard.get("no_op_rate") or 0.0),
        "wrong_root_rate": float(scoreboard.get("wrong_root_rate") or 0.0),
        "current_success_streak": float(scoreboard.get("current_success_streak") or 0),
    }
    formula_rows: list[dict[str, Any]] = []
    for key, label, weight in _POINT_WEIGHTS:
        raw_value = values[key]
        display_value = f"{raw_value * 100:.1f}%" if key.endswith("_rate") else str(int(raw_value))
        formula_rows.append(
            {
                "label": label,
                "weight": weight,
                "value": display_value,
                "contribution": int(round(raw_value * float(weight))),
            }
        )
    return {
        "title": "Agent Points are derived from observed telemetry.",
        "summary": "The score rewards issue wins and clean first-pass execution, while penalizing losses, no-op churn, and wrong-root drift.",
        "formula_rows": formula_rows,
        "samples": {
            "issues": int(scoreboard.get("sample_issue_count") or 0),
            "attempts": int(scoreboard.get("sample_attempt_count") or 0),
        },
        "definitions": {
            "win_rate": "Each issue counts once. Wins are pr_open, pr_pending_approval, or resolved. Losses are failed or blocked.",
            "streak": "Current streak counts consecutive successful terminal issue outcomes from newest to oldest.",
        },
    }


def _build_chart_series(status_rows: list[dict[str, Any]]) -> dict[str, Any]:
    reliability_days: dict[str, dict[str, float]] = {}
    issue_outcome_days: dict[str, dict[str, int]] = {}
    for row in status_rows:
        for item in row.get("reliability_daily_rollups") or []:
            day = str(item.get("day") or "").strip()
            if not day:
                continue
            bucket = reliability_days.setdefault(
                day,
                {
                    "first_pass_weighted": 0.0,
                    "issue_count": 0.0,
                    "no_op_weighted": 0.0,
                    "wrong_root_weighted": 0.0,
                    "sample_size": 0.0,
                },
            )
            issue_count = float(item.get("issue_count") or 0)
            sample_size = float(item.get("sample_size") or 0)
            bucket["issue_count"] += issue_count
            bucket["sample_size"] += sample_size
            bucket["first_pass_weighted"] += float(item.get("first_pass_success_rate") or 0.0) * issue_count
            bucket["no_op_weighted"] += float(item.get("no_op_rate") or 0.0) * sample_size
            bucket["wrong_root_weighted"] += float(item.get("wrong_root_execution_rate") or 0.0) * sample_size

        outcomes = (row.get("issue_outcomes") or {}).get("daily_terminal_outcomes") or []
        for item in outcomes:
            day = str(item.get("day") or "").strip()
            if not day:
                continue
            bucket = issue_outcome_days.setdefault(day, {"success": 0, "failure": 0})
            bucket["success"] += int(item.get("success") or 0)
            bucket["failure"] += int(item.get("failure") or 0)

    reliability = []
    for day in sorted(reliability_days.keys()):
        bucket = reliability_days[day]
        issue_count = int(bucket["issue_count"])
        sample_size = int(bucket["sample_size"])
        reliability.append(
            {
                "day": day,
                "issue_count": issue_count,
                "sample_size": sample_size,
                "first_pass_success_rate": round(bucket["first_pass_weighted"] / float(max(1, issue_count)), 4) if issue_count else 0.0,
                "no_op_rate": round(bucket["no_op_weighted"] / float(max(1, sample_size)), 4) if sample_size else 0.0,
                "wrong_root_rate": round(bucket["wrong_root_weighted"] / float(max(1, sample_size)), 4) if sample_size else 0.0,
            }
        )

    issue_outcomes = []
    for day in sorted(issue_outcome_days.keys()):
        bucket = issue_outcome_days[day]
        issue_outcomes.append(
            {
                "day": day,
                "success": bucket["success"],
                "failure": bucket["failure"],
                "total": bucket["success"] + bucket["failure"],
            }
        )
    return {
        "reliability": reliability[-30:],
        "issue_outcomes": issue_outcomes[-30:],
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
        "events": _normalize_log_activity_rows(lines, repo_slug_by_name=_repo_slug_by_name(config)),
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


def _collect_activity(
    config: AppConfig,
    service: FlowHealerService,
    *,
    logs: dict[str, Any] | None = None,
    limit: int = _ACTIVITY_LIMIT,
    status_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    status_rows = status_rows if status_rows is not None else service.cached_status_rows(None)
    command_rows = service.control_command_rows(None, limit=max(120, limit))
    event_rows = service.healer_event_rows(None, limit=max(120, limit))
    logs_payload = logs or _collect_recent_logs(config, max_lines=max(160, limit))
    repo_slug_by_name = _repo_slug_by_name(config)
    activity: list[dict[str, Any]] = []
    activity.extend(_normalize_command_activity_rows(command_rows, repo_slug_by_name=repo_slug_by_name))
    activity.extend(_normalize_event_activity_rows(event_rows, repo_slug_by_name=repo_slug_by_name))
    activity.extend(_normalize_attempt_activity_rows(status_rows, repo_slug_by_name=repo_slug_by_name))
    activity.extend(_normalize_log_activity_rows(logs_payload.get("lines", []), repo_slug_by_name=repo_slug_by_name))
    activity.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    if len(activity) > limit:
        activity = activity[:limit]
    return activity


def _repo_slug_by_name(config: AppConfig) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for repo in config.repos:
        slug = str(repo.healer_repo_slug or "").strip()
        if slug:
            mapping[repo.repo_name] = slug
    return mapping


def _render_repo_action_cards(config: AppConfig) -> str:
    cards: list[str] = []
    auth_mode = str(getattr(config.control.web, "auth_mode", "none") or "none").strip().lower()
    auth_note = ""
    auth_fields = ""
    if auth_mode == "token":
        auth_env = escape(str(getattr(config.control.web, "auth_token_env", "FLOW_HEALER_WEB_TOKEN") or "FLOW_HEALER_WEB_TOKEN"))
        auth_note = (
            "<div class='mt-3 rounded-2xl border border-amber-400/20 bg-amber-400/10 px-3 py-2 text-[11px] "
            f"text-amber-100'>Action token required via <span class='font-mono'>{auth_env}</span>.</div>"
        )
        auth_fields = (
            "<label class='mt-2 block text-[11px] text-slate-400'>"
            "<span class='mb-1 block uppercase tracking-[0.2em] text-slate-500'>Auth token</span>"
            "<input type='password' name='auth_token' "
            "class='w-full rounded-xl border border-white/10 bg-slate-950/70 px-3 py-2 text-xs text-white outline-none placeholder:text-slate-500' "
            "placeholder='Web auth token'>"
            "</label>"
        )
    for repo in config.repos:
        repo_name = escape(repo.repo_name)
        cards.append(
            f"""
            <div class='rounded-[28px] border border-white/10 bg-slate-900/75 p-4 shadow-glow backdrop-blur'>
              <div class='flex items-start justify-between gap-3'>
                <div>
                  <div class='text-xs uppercase tracking-[0.24em] text-slate-500'>Repo</div>
                  <h3 class='mt-2 text-lg font-semibold text-white'>{repo_name}</h3>
                </div>
                <button
                  type='button'
                  @click="activeActions === '{repo_name}' ? activeActions = '' : activeActions = '{repo_name}'"
                  class='rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-slate-200 transition hover:bg-white/10'
                >
                  Actions
                </button>
              </div>

              <div class='mt-4 text-xs text-slate-400'>Fast controls stay local to the repo card. Investigations happen in the activity console below.</div>
              {auth_note}

              <div x-show="activeActions === '{repo_name}'" class='mt-4 grid grid-cols-2 gap-2 border-t border-white/10 pt-4'>
                <form method='post' action='/action'>
                  <input type='hidden' name='repo' value='{repo_name}'>
                  {auth_fields}
                  <button type='submit' name='command' value='status' class='w-full rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-left text-xs text-slate-100 transition hover:bg-white/10'>Status</button>
                </form>
                <form method='post' action='/action'>
                  <input type='hidden' name='repo' value='{repo_name}'>
                  {auth_fields}
                  <button type='submit' name='command' value='doctor' class='w-full rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-left text-xs text-slate-100 transition hover:bg-white/10'>Doctor</button>
                </form>
                <form method='post' action='/action'>
                  <input type='hidden' name='repo' value='{repo_name}'>
                  {auth_fields}
                  <button type='submit' name='command' value='pause' class='w-full rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-left text-xs text-slate-100 transition hover:bg-white/10'>Pause</button>
                </form>
                <form method='post' action='/action'>
                  <input type='hidden' name='repo' value='{repo_name}'>
                  {auth_fields}
                  <button type='submit' name='command' value='resume' class='w-full rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-left text-xs text-slate-100 transition hover:bg-white/10'>Resume</button>
                </form>
                <form method='post' action='/action'>
                  <input type='hidden' name='repo' value='{repo_name}'>
                  {auth_fields}
                  <button type='submit' name='command' value='once' class='w-full rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-3 py-2 text-left text-xs text-cyan-100 transition hover:bg-cyan-400/15'>Run once</button>
                </form>
                <form method='post' action='/action' class='rounded-2xl border border-white/10 bg-white/5 px-3 py-2'>
                  <input type='hidden' name='repo' value='{repo_name}'>
                  {auth_fields}
                  <div class='flex items-center justify-between gap-2'>
                    <button type='submit' name='command' value='scan' class='text-left text-xs text-slate-100'>Scan</button>
                    <label class='flex items-center gap-1 text-[11px] uppercase tracking-[0.2em] text-slate-400'>
                      <input type='checkbox' name='dry_run' value='true' class='rounded border-white/10 bg-white/10'>
                      dry
                    </label>
                  </div>
                </form>
              </div>
            </div>
            """
        )
    return "".join(cards)


def _normalize_command_activity_rows(
    command_rows: list[dict[str, Any]],
    *,
    repo_slug_by_name: dict[str, str],
) -> list[dict[str, Any]]:
    activity: list[dict[str, Any]] = []
    for row in command_rows:
        status = str(row.get("status") or "").strip().lower()
        repo_name = str(row.get("repo_name") or "").strip()
        signal = "failure" if status in {"failed", "error"} else "running" if status in {"received", "running", "pending"} else "ok"
        parsed_command = str(row.get("parsed_command") or "").strip()
        raw_command = str(row.get("raw_command") or "").strip()
        error_text = str(row.get("error_text") or "").strip()
        result = row.get("result")
        summary = parsed_command or raw_command or "Control command"
        raw_text_parts = [raw_command or summary]
        if result:
            raw_text_parts.append(json.dumps(result, indent=2, default=str))
        if error_text:
            raw_text_parts.append(error_text)
        activity.append(
            {
                "id": str(row.get("command_id") or f"command:{repo_name}:{parsed_command}"),
                "kind": "command",
                "timestamp": str(row.get("created_at") or row.get("updated_at") or ""),
                "repo": repo_name,
                "issue_id": "",
                "pr_id": "",
                "attempt_id": "",
                "branch": "",
                "subsystem": str(row.get("source") or "control"),
                "summary": _truncate_text(summary, 160),
                "message": parsed_command or raw_command,
                "raw_text": "\n\n".join(part for part in raw_text_parts if part),
                "status": status or "unknown",
                "signal": signal,
                "level": status.upper() if status else "",
                "source_file": "control_commands",
                "jump_urls": _github_jump_urls(repo_slug_by_name.get(repo_name, ""), issue_id="", pr_id=""),
            }
        )
    return activity


def _web_request_is_authorized(
    config: AppConfig,
    *,
    headers: dict[str, str],
    params: dict[str, str],
) -> tuple[bool, int, str]:
    auth_mode = str(getattr(config.control.web, "auth_mode", "none") or "none").strip().lower()
    if auth_mode != "token":
        return True, 200, ""

    env_name = str(getattr(config.control.web, "auth_token_env", "FLOW_HEALER_WEB_TOKEN") or "FLOW_HEALER_WEB_TOKEN")
    expected_token = os.getenv(env_name, "").strip()
    if not expected_token:
        return False, 503, f"Web auth token is not configured in {env_name}."

    form_token = str(params.get("auth_token") or "").strip()
    header_token = _extract_bearer_token(headers)
    candidate = form_token or header_token
    if candidate and secrets.compare_digest(candidate, expected_token):
        return True, 200, ""
    return False, 401, "Web auth token required."


def _extract_bearer_token(headers: dict[str, str]) -> str:
    authorization = ""
    for key, value in headers.items():
        if str(key).lower() == "authorization":
            authorization = str(value or "").strip()
            break
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _resolve_dashboard_artifact_path(config: AppConfig, raw_path: str) -> Path | None:
    text = str(raw_path or "").strip()
    if not text:
        return None
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        return None
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    for root in _allowed_dashboard_artifact_roots(config):
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    return None


def _resolve_dashboard_static_path(raw_path: str) -> Path | None:
    path_text = str(raw_path or "").strip()
    if not path_text.startswith("/assets/"):
        return None
    relative = path_text.lstrip("/")
    if not relative:
        return None
    static_root = Path(__file__).resolve().parent / "dashboard_static"
    candidate = (static_root / relative).resolve()
    try:
        candidate.relative_to(static_root.resolve())
    except ValueError:
        return None
    return candidate


def _allowed_dashboard_artifact_roots(config: AppConfig) -> list[Path]:
    roots = [Path(config.service.state_root).expanduser().resolve()]
    temp_root = Path(tempfile.gettempdir()).resolve()
    roots.append(temp_root / "flow-healer-browser")
    roots.append(temp_root / "flow-healer-live-verify")
    for repo in config.repos:
        repo_parent = Path(repo.healer_repo_path).expanduser().resolve().parent
        roots.append(repo_parent / ".flow-healer-artifacts")
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _normalize_attempt_activity_rows(
    status_rows: list[dict[str, Any]],
    *,
    repo_slug_by_name: dict[str, str],
) -> list[dict[str, Any]]:
    activity: list[dict[str, Any]] = []
    for repo_row in status_rows:
        repo_name = str(repo_row.get("repo") or "").strip()
        repo_slug = repo_slug_by_name.get(repo_name, "")
        for attempt in repo_row.get("recent_attempts") or []:
            state = str(attempt.get("state") or "").strip().lower()
            signal = "failure" if state in {"failed", "blocked"} else "running" if state in {"running", "claimed", "verify_pending"} else "ok"
            issue_id = str(attempt.get("issue_id") or "").strip()
            summary = str(attempt.get("failure_reason") or "").strip() or str(attempt.get("default_action") or "").strip() or f"Attempt {state or 'update'}"
            raw_text_parts = [summary]
            proposer_excerpt = str(attempt.get("proposer_output_excerpt") or "").strip()
            if proposer_excerpt:
                raw_text_parts.append(proposer_excerpt)
            test_summary = attempt.get("test_summary") or {}
            if test_summary:
                raw_text_parts.append(json.dumps(test_summary, indent=2, default=str))
            activity.append(
                {
                    "id": str(attempt.get("attempt_id") or f"attempt:{repo_name}:{issue_id}:{attempt.get('attempt_no') or ''}"),
                    "kind": "attempt",
                    "timestamp": str(attempt.get("finished_at") or attempt.get("started_at") or ""),
                    "repo": repo_name,
                    "issue_id": issue_id,
                    "pr_id": "",
                    "attempt_id": str(attempt.get("attempt_id") or ""),
                    "branch": "",
                    "subsystem": "healer attempt",
                    "summary": _truncate_text(summary, 180),
                    "message": str(attempt.get("failure_class") or state or "").strip(),
                    "raw_text": "\n\n".join(part for part in raw_text_parts if part),
                    "status": state or "unknown",
                    "signal": signal,
                    "level": str(attempt.get("failure_class") or "").upper(),
                    "source_file": "recent_attempts",
                    "jump_urls": _github_jump_urls(repo_slug, issue_id=issue_id, pr_id=""),
                }
            )
    return activity


def _normalize_event_activity_rows(
    event_rows: list[dict[str, Any]],
    *,
    repo_slug_by_name: dict[str, str],
) -> list[dict[str, Any]]:
    activity: list[dict[str, Any]] = []
    for row in event_rows:
        repo_name = str(row.get("repo_name") or "").strip()
        repo_slug = repo_slug_by_name.get(repo_name, "")
        event_type = str(row.get("event_type") or "").strip().lower()
        level = str(row.get("level") or "").strip().lower()
        message = str(row.get("message") or "").strip() or event_type.replace("_", " ")
        payload = row.get("payload") or {}
        is_swarm_event = event_type.startswith("swarm_")
        signal = "failure" if level in {"error", "warning"} else "running" if event_type == "worker_pulse" or is_swarm_event else "ok"
        raw_text_parts = [message]
        if payload:
            raw_text_parts.append(json.dumps(payload, indent=2, default=str))
        activity.append(
            {
                "id": str(row.get("event_id") or f"event:{repo_name}:{event_type}:{row.get('created_at') or ''}"),
                "kind": "event",
                "timestamp": str(row.get("created_at") or ""),
                "repo": repo_name,
                "issue_id": str(row.get("issue_id") or "").strip(),
                "pr_id": "",
                "attempt_id": str(row.get("attempt_id") or "").strip(),
                "branch": "",
                "subsystem": "healer runtime" if event_type == "worker_pulse" else ("healer swarm" if is_swarm_event else (event_type or "healer event")),
                "summary": _truncate_text(message, 180),
                "message": event_type or "event",
                "raw_text": "\n\n".join(part for part in raw_text_parts if part),
                "status": level or "info",
                "signal": signal,
                "level": level.upper() if level else "",
                "source_file": "healer_events",
                "jump_urls": _github_jump_urls(
                    repo_slug,
                    issue_id=str(row.get("issue_id") or "").strip(),
                    pr_id="",
                ),
            }
        )
    return activity


def _normalize_log_activity_rows(
    lines: list[str],
    *,
    repo_slug_by_name: dict[str, str],
) -> list[dict[str, Any]]:
    activity: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        row = _parse_log_activity_row(line, index=index, repo_slug_by_name=repo_slug_by_name)
        activity.append(row)
    return activity


def _parse_log_activity_row(
    line: str,
    *,
    index: int,
    repo_slug_by_name: dict[str, str],
) -> dict[str, Any]:
    raw_line = str(line or "")
    source_file = ""
    line_text = raw_line
    file_match = re.match(r"^\[(?P<source_file>[^\]]+)\]\s+(?P<rest>.*)$", raw_line)
    if file_match:
        source_file = str(file_match.group("source_file") or "")
        line_text = str(file_match.group("rest") or "")
    parsed = _LOG_LINE_RE.match(line_text)
    timestamp = ""
    level = ""
    subsystem = source_file or "runtime log"
    message = line_text
    if parsed:
        timestamp = str(parsed.group("timestamp") or "")
        level = str(parsed.group("level") or "")
        subsystem = str(parsed.group("subsystem") or subsystem)
        message = str(parsed.group("message") or "")
    issue_id = _extract_match(_ISSUE_ID_RE, message, "issue_id")
    pr_id = _extract_match(_PR_ID_RE, message, "pr_id")
    attempt_id = _extract_match(_ATTEMPT_ID_RE, message, "attempt_id")
    branch = _extract_match(_BRANCH_RE, message, "branch")
    repo_name = _extract_repo_name(message)
    signal = "failure" if level in {"ERROR", "CRITICAL"} or "failed" in message.lower() else "running" if level in {"WARNING"} or "running" in message.lower() else "ok"
    return {
        "id": f"log:{source_file or 'runtime'}:{timestamp}:{index}",
        "kind": "log",
        "timestamp": timestamp,
        "repo": repo_name,
        "issue_id": issue_id,
        "pr_id": pr_id,
        "attempt_id": attempt_id,
        "branch": branch,
        "subsystem": subsystem,
        "summary": _truncate_text(message, 180),
        "message": message,
        "raw_text": raw_line,
        "status": level.lower() if level else "",
        "signal": signal,
        "level": level,
        "source_file": source_file,
        "jump_urls": _github_jump_urls(repo_slug_by_name.get(repo_name, ""), issue_id=issue_id, pr_id=pr_id),
    }


def _github_jump_urls(repo_slug: str, *, issue_id: str, pr_id: str) -> list[dict[str, str]]:
    slug = str(repo_slug or "").strip()
    if not slug:
        return []
    links: list[dict[str, str]] = []
    if issue_id:
        links.append({"label": f"Open issue #{issue_id}", "url": f"https://github.com/{slug}/issues/{issue_id}"})
    if pr_id:
        links.append({"label": f"Open PR #{pr_id}", "url": f"https://github.com/{slug}/pull/{pr_id}"})
    return links


def _extract_match(pattern: re.Pattern[str], text: str, group: str) -> str:
    match = pattern.search(str(text or ""))
    return str(match.group(group) or "").strip() if match else ""


def _extract_repo_name(message: str) -> str:
    repo_match = re.search(r"repo(?:=|\s)(?P<repo>[A-Za-z0-9._\-]+)", str(message or ""))
    if repo_match:
        return str(repo_match.group("repo") or "").strip()
    path_match = re.search(r"/code/(?P<repo>[A-Za-z0-9._\-]+)/?", str(message or ""))
    if path_match:
        return str(path_match.group("repo") or "").strip()
    return ""


def _truncate_text(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


from .dashboard_cockpit import issue_detail_payload as _issue_detail_payload
from .dashboard_cockpit import queue_payload as _queue_payload
from .dashboard_cockpit import render_dashboard as _render_dashboard
