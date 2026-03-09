from __future__ import annotations

from pathlib import Path

from flow_healer.config import AppConfig, RelaySettings, ServiceSettings
from flow_healer.service import FlowHealerService
from flow_healer.web_dashboard import (
    _collect_activity,
    _collect_recent_logs,
    _overview_payload,
    _parse_log_activity_row,
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
    assert "activity" in payload
    assert "generated_at" in payload
    assert isinstance(payload["logs"]["lines"], list)
    assert isinstance(payload["activity"], list)


def test_parse_log_activity_row_extracts_issue_and_attempt_metadata() -> None:
    row = _parse_log_activity_row(
        "[flow-healer.log] 2026-03-09 09:47:23 INFO apple_flow.healer_loop: Issue #576 attempt hat_d7008df1de failed in repo flow-healer on healer/issue-576-demo PR #580",
        index=0,
        repo_slug_by_name={"flow-healer": "owner/repo"},
    )

    assert row["kind"] == "log"
    assert row["timestamp"] == "2026-03-09 09:47:23"
    assert row["issue_id"] == "576"
    assert row["pr_id"] == "580"
    assert row["attempt_id"] == "hat_d7008df1de"
    assert row["repo"] == "flow-healer"
    assert row["jump_urls"][0]["url"].endswith("/issues/576")


def test_collect_activity_includes_commands_attempts_and_logs(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)
    store_path = config.repo_db_path("demo")
    state_root = Path(config.service.state_root).expanduser().resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "flow-healer.log").write_text(
        "[flow-healer.log] 2026-03-09 09:47:23 ERROR apple_flow.healer_loop: Issue #576 failed in repo demo\n",
        encoding="utf-8",
    )

    from flow_healer.store import SQLiteStore

    store = SQLiteStore(store_path)
    store.bootstrap()
    store.create_control_command(
        source="web",
        external_id="web:1",
        sender="web-ui",
        repo_name="demo",
        raw_command="FH: pause repo=demo",
        parsed_command="pause",
        status="succeeded",
    )
    store.upsert_healer_issue(
        issue_id="576",
        repo="owner/repo",
        title="Issue 576",
        body="body",
        author="alice",
        labels=["healer:ready"],
        priority=1,
    )
    store.create_healer_attempt(
        attempt_id="hat_demo123",
        issue_id="576",
        attempt_no=1,
        state="failed",
        prediction_source="path_level",
        predicted_lock_set=["path:a"],
    )
    store.finish_healer_attempt(
        attempt_id="hat_demo123",
        state="failed",
        actual_diff_set=[],
        test_summary={},
        verifier_summary={},
        failure_class="tests_failed",
        failure_reason="boom",
    )
    store.close()

    activity = _collect_activity(config, service)
    kinds = {row["kind"] for row in activity}

    assert {"command", "attempt", "log"}.issubset(kinds)


def test_render_dashboard_includes_activity_console_and_inspector(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="")

    assert "Flow Healer Activity Console" in html
    assert "Activity Table" in html
    assert "openInspector(item.id)" in html
    assert "Copy full text" in html
    assert "/api/activity" not in html
