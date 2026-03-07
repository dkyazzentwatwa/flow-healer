from __future__ import annotations

from html import escape
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import threading
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse
from uuid import uuid4

from .config import AppConfig
from .control_plane import ControlRouter, parse_command_subject
from .service import FlowHealerService


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
                # Keep stdlib server quiet; app-level logging already exists.
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
                    if result.get("ok"):
                        msg = f"{command} completed"
                    else:
                        msg = str(result.get("message") or "command failed")
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
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _write_html(self, html: str, status: int = 200) -> None:
                raw = html.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        return Handler


def _render_dashboard(config: AppConfig, service: FlowHealerService, notice: str) -> str:
    rows = service.status_rows(None)
    command_rows = service.control_command_rows(None, limit=80)

    repo_cards = []
    for row in rows:
        repo = str(row.get("repo") or "")
        paused = bool(row.get("paused"))
        counts = row.get("state_counts") or {}
        counts_text = ", ".join(f"{k}:{v}" for k, v in sorted(dict(counts).items())) if counts else "none"
        connector = row.get("connector") or {}
        breaker = row.get("circuit_breaker") or {}
        repo_cards.append(
            f"""
            <section class='card'>
              <h2>{escape(repo)}</h2>
              <p><b>Paused:</b> {'yes' if paused else 'no'}</p>
              <p><b>Issues:</b> {escape(str(row.get('issues_total') or 0))}</p>
              <p><b>States:</b> {escape(counts_text)}</p>
              <p><b>Connector:</b> {escape(str(connector.get('available') or False))}</p>
              <p><b>Circuit Breaker:</b> {escape(str(breaker.get('open') or False))}</p>
              <form method='post' action='/action' class='actions'>
                <input type='hidden' name='repo' value='{escape(repo)}'>
                <button name='command' value='status'>Status</button>
                <button name='command' value='doctor'>Doctor</button>
                <button name='command' value='pause'>Pause</button>
                <button name='command' value='resume'>Resume</button>
                <button name='command' value='once'>Run Once</button>
                <button name='command' value='scan'>Scan</button>
                <label><input type='checkbox' name='dry_run' value='true'> dry</label>
              </form>
            </section>
            """
        )

    history_rows = []
    for item in command_rows:
        history_rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('created_at') or ''))}</td>"
            f"<td>{escape(str(item.get('repo_name') or ''))}</td>"
            f"<td>{escape(str(item.get('source') or ''))}</td>"
            f"<td>{escape(str(item.get('parsed_command') or ''))}</td>"
            f"<td>{escape(str(item.get('status') or ''))}</td>"
            f"<td>{escape(str(item.get('error_text') or ''))}</td>"
            "</tr>"
        )

    notice_html = f"<div class='notice'>{escape(notice)}</div>" if notice else ""

    return f"""
<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Flow Healer Dashboard</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 0; background:#0d1117; color:#e6edf3; }}
    header {{ padding: 16px; background:#111a22; position: sticky; top:0; }}
    main {{ padding: 12px; max-width: 1100px; margin: 0 auto; }}
    .notice {{ background:#13202b; color:#f0b72f; padding:10px; margin-bottom:12px; border-radius:8px; }}
    .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:12px; }}
    .card {{ background:#111a22; border:1px solid #2f81f7; border-radius:10px; padding:12px; }}
    .card h2 {{ margin:0 0 8px 0; font-size: 1.1rem; }}
    .card p {{ margin:6px 0; font-size: 0.95rem; }}
    .actions {{ display:flex; gap:6px; flex-wrap:wrap; margin-top:10px; align-items:center; }}
    button {{ background:#13202b; color:#e6edf3; border:1px solid #2f81f7; border-radius:8px; padding:8px 10px; }}
    table {{ width:100%; border-collapse: collapse; margin-top: 12px; font-size:0.9rem; }}
    th, td {{ border-bottom: 1px solid #23303d; padding:8px; text-align:left; }}
  </style>
</head>
<body>
  <header>
    <h1>Flow Healer Dashboard</h1>
    <p>{escape(config.service.state_root)} • Repos: {len(config.repos)}</p>
  </header>
  <main>
    {notice_html}
    <div class='grid'>
      {''.join(repo_cards)}
    </div>
    <section class='card' style='margin-top:12px;'>
      <h2>Recent Commands</h2>
      <table>
        <thead><tr><th>Time</th><th>Repo</th><th>Source</th><th>Command</th><th>Status</th><th>Error</th></tr></thead>
        <tbody>{''.join(history_rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
