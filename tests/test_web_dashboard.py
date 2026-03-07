from __future__ import annotations

from pathlib import Path

from flow_healer.config import AppConfig, RelaySettings, ServiceSettings
from flow_healer.service import FlowHealerService
from flow_healer.web_dashboard import (
    _collect_recent_logs,
    _overview_payload,
    _render_dashboard,
    _tail_file_lines,
)


def _make_service(tmp_path: Path) -> tuple[AppConfig, FlowHealerService]:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    config = AppConfig(
        service=ServiceSettings(state_root=str(tmp_path / "state")),
        repos=[
            RelaySettings(
                repo_name="demo",
                healer_repo_path=str(repo_path),
                healer_repo_slug="owner/repo",
            )
        ],
    )
    return config, FlowHealerService(config)


def test_tail_file_lines_reads_recent_tail(tmp_path: Path) -> None:
    log_path = tmp_path / "x.log"
    log_path.write_text("\n".join([f"line-{i}" for i in range(1, 11)]) + "\n", encoding="utf-8")

    lines = _tail_file_lines(log_path, 3)

    assert lines == ["line-8", "line-9", "line-10"]


def test_collect_recent_logs_prefixes_file_names(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True)
    (state_root / "flow-healer.log").write_text("a\nb\n", encoding="utf-8")
    (state_root / "serve-web.log").write_text("c\nd\n", encoding="utf-8")

    config = AppConfig(
        service=ServiceSettings(state_root=str(state_root)),
        repos=[],
    )
    payload = _collect_recent_logs(config, max_lines=10)

    assert payload["files"] == ["flow-healer.log", "serve-web.log"]
    assert payload["lines"][0].startswith("[flow-healer.log] ")
    assert payload["lines"][-1].startswith("[serve-web.log] ")


def test_overview_payload_includes_rows_commands_and_logs(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)
    state_root = Path(config.service.state_root).expanduser().resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "flow-healer.log").write_text("hello\n", encoding="utf-8")

    payload = _overview_payload(config, service)

    assert "rows" in payload
    assert "commands" in payload
    assert "logs" in payload
    assert "generated_at" in payload
    assert isinstance(payload["logs"]["lines"], list)


def test_render_dashboard_escapes_log_join_newline(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="")

    assert "lines.join('\\n')" in html
    assert "lines.join('\n')" not in html
