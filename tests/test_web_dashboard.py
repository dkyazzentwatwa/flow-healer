from __future__ import annotations

from pathlib import Path

from flow_healer.config import AppConfig, RelaySettings, ServiceSettings
from flow_healer.service import FlowHealerService
from flow_healer.web_dashboard import (
    _collect_activity,
    _collect_recent_logs,
    _overview_payload,
    _parse_log_activity_row,
    _render_repo_action_cards,
    _render_dashboard,
    _tail_file_lines,
    _web_request_is_authorized,
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
    assert "scoreboard" in payload
    assert "score_explainer" in payload
    assert "chart_series" in payload
    assert "generated_at" in payload
    assert isinstance(payload["logs"]["lines"], list)
    assert isinstance(payload["activity"], list)


def test_overview_payload_includes_real_scoreboard_and_chart_series(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)
    store_path = config.repo_db_path("demo")

    from flow_healer.store import SQLiteStore

    store = SQLiteStore(store_path)
    store.bootstrap()
    for issue_id in ("7001", "7002", "7003"):
        store.upsert_healer_issue(
            issue_id=issue_id,
            repo="owner/repo",
            title=f"Issue {issue_id}",
            body="body",
            author="alice",
            labels=["healer:ready"],
            priority=1,
        )

    store.set_healer_issue_state(issue_id="7001", state="pr_open")
    store.set_healer_issue_state(issue_id="7002", state="failed")
    store.set_healer_issue_state(issue_id="7003", state="queued")
    conn = store._connect()
    conn.execute("UPDATE healer_issues SET updated_at = ? WHERE issue_id = ?", ("2026-03-10 09:00:00", "7001"))
    conn.execute("UPDATE healer_issues SET updated_at = ? WHERE issue_id = ?", ("2026-03-10 08:00:00", "7002"))
    conn.execute("UPDATE healer_issues SET updated_at = ? WHERE issue_id = ?", ("2026-03-10 07:00:00", "7003"))

    store.create_healer_attempt(
        attempt_id="ha_7001_1",
        issue_id="7001",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="ha_7001_1",
        state="pr_open",
        actual_diff_set=[],
        test_summary={"execution_root_source": "issue"},
        verifier_summary={},
    )
    conn.execute(
        "UPDATE healer_attempts SET started_at = ?, finished_at = ? WHERE attempt_id = ?",
        ("2026-03-10 08:50:00", "2026-03-10 09:00:00", "ha_7001_1"),
    )

    store.create_healer_attempt(
        attempt_id="ha_7002_1",
        issue_id="7002",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="ha_7002_1",
        state="failed",
        actual_diff_set=[],
        test_summary={"execution_root_source": "fallback"},
        verifier_summary={},
        failure_class="no_patch",
        failure_reason="no patch",
    )
    conn.execute(
        "UPDATE healer_attempts SET started_at = ?, finished_at = ? WHERE attempt_id = ?",
        ("2026-03-10 07:50:00", "2026-03-10 08:00:00", "ha_7002_1"),
    )
    conn.commit()
    store.close()

    payload = _overview_payload(config, service)

    scoreboard = payload["scoreboard"]
    assert scoreboard["issue_successes"] == 1
    assert scoreboard["issue_failures"] == 1
    assert scoreboard["active_issues"] == 1
    assert scoreboard["current_success_streak"] == 1
    assert scoreboard["win_rate"] == 0.5
    assert scoreboard["first_pass_success_rate"] == 0.5
    assert scoreboard["no_op_rate"] == 0.5
    assert scoreboard["wrong_root_rate"] == 0.5
    assert scoreboard["agent_points"] > 0
    assert payload["score_explainer"]["formula_rows"]
    assert payload["chart_series"]["reliability"]
    assert payload["chart_series"]["issue_outcomes"]


def test_overview_payload_reuses_single_status_snapshot(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)
    calls = 0

    def fake_cached_status_rows(repo_name=None, *, force_refresh=False, probe_connector=False):
        nonlocal calls
        calls += 1
        return [
            {
                "repo": "demo",
                "recent_attempts": [],
            }
        ]

    service.cached_status_rows = fake_cached_status_rows  # type: ignore[method-assign]

    payload = _overview_payload(config, service)

    assert calls == 1
    assert payload["rows"][0]["repo"] == "demo"


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


def test_collect_activity_includes_commands_events_attempts_and_logs(tmp_path: Path) -> None:
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
    store.create_healer_event(
        event_type="worker_pulse",
        message="Worker pulse: idle.",
        payload={"status": "idle"},
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

    assert {"command", "event", "attempt", "log"}.issubset(kinds)


def test_collect_activity_marks_swarm_events_as_running(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)
    store_path = config.repo_db_path("demo")

    from flow_healer.store import SQLiteStore

    store = SQLiteStore(store_path)
    store.bootstrap()
    store.create_healer_event(
        event_type="swarm_started",
        message="Swarm recovery started for failure tests_failed.",
        issue_id="612",
        attempt_id="hat_612",
        payload={"strategy": "repair", "failure_class": "tests_failed"},
    )
    store.close()

    activity = _collect_activity(config, service)
    swarm_event = next(row for row in activity if row["kind"] == "event" and row["message"] == "swarm_started")

    assert swarm_event["signal"] == "running"
    assert swarm_event["subsystem"] == "healer swarm"
    assert swarm_event["issue_id"] == "612"
    assert swarm_event["attempt_id"] == "hat_612"


def test_render_dashboard_includes_activity_console_and_inspector(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="")

    assert "Flow Healer Activity Console" in html
    assert "Activity Table" in html
    assert "openInspector(item.id)" in html
    assert "Copy full text" in html
    assert "/api/activity" not in html


def test_render_dashboard_uses_dedicated_log_feed_for_logs_tab(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="")

    assert "logEvents: []" in html
    assert "if (this.kindFilter === 'log')" in html
    assert "this.logEvents" in html


def test_render_dashboard_embeds_raw_json_in_initial_data_script(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="")

    assert "<script id='initial-data' type='application/json'>{&quot;" not in html
    assert "<script id='initial-data' type='application/json'>{\"" in html


def test_render_dashboard_activity_rows_counter_binds_to_activity(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="")

    assert "x-text='activity.length'" in html


def test_render_dashboard_includes_reliability_and_domain_metric_cards(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="")

    assert "Canary First Pass" in html
    assert "Canary No-op" in html
    assert "Canary Wrong Root" in html
    assert "Canary Mean TTVP" in html
    assert "Swarm Domain Skips" in html
    assert "Native Recovery" in html
    assert "Needs Clarification" in html
    assert "Failure Domain Infra" in html
    assert "Failure Domain Contract" in html
    assert "Retry Playbook Runs" in html
    assert "Retry Hotspot" in html
    assert "7d First-pass Delta" in html
    assert "get canaryFirstPassRate()" in html
    assert "get nativeRecoveryRate()" in html
    assert "get retryPlaybookRuns()" in html
    assert "get retryPlaybookHotspot()" in html
    assert "get firstPassTrend7d()" in html
    assert "x-text='activities.length'" not in html


def test_render_dashboard_includes_gamification_cards_and_getters(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="")

    assert "Flow Healer Progress" in html
    assert "Agent Level" in html
    assert "First-Pass Success" in html
    assert "Current Success Streak" in html
    assert "How points work" in html
    assert "scoreboard.agent_points" in html
    assert "scoreboard.current_success_streak" in html


def test_render_dashboard_includes_collapsible_telemetry_trends_and_svg_charts(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="")

    assert "Telemetry Trends" in html
    assert "showTelemetryCharts" in html
    assert "First-pass vs Drift" in html
    assert "Issue Outcomes" in html
    assert "<svg" in html


def test_render_dashboard_includes_collapsible_infra_ops_deep_dive(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="")

    assert "Infra/Ops Deep Dive" in html
    assert "showAdvancedMetrics" in html
    assert "@click='showAdvancedMetrics = !showAdvancedMetrics'" in html


def test_render_dashboard_includes_dark_light_theme_toggle_and_persistence(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="")

    assert "Dark / Light" in html
    assert "themeMode: 'dark'" in html
    assert "toggleTheme()" in html
    assert "initTheme()" in html
    assert "localStorage.setItem('flow-healer-theme'" in html
    assert "document.documentElement.setAttribute('data-theme', this.themeMode)" in html


def test_render_dashboard_includes_mobile_activity_cards(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="")

    assert "lg:hidden" in html
    assert "Activity Cards" in html
    assert "Tap any card for full context." in html


def test_render_repo_action_cards_include_auth_field_when_token_mode_enabled(tmp_path: Path) -> None:
    config, _service = _make_service(tmp_path)

    html = _render_repo_action_cards(config)

    assert "name='auth_token'" in html
    assert "FLOW_HEALER_WEB_TOKEN" in html


def test_web_request_is_authorized_accepts_form_token(tmp_path: Path, monkeypatch) -> None:
    config, _service = _make_service(tmp_path)
    monkeypatch.setenv("FLOW_HEALER_WEB_TOKEN", "demo-token")

    allowed, status, reason = _web_request_is_authorized(
        config,
        headers={},
        params={"auth_token": "demo-token"},
    )

    assert allowed is True
    assert status == 200
    assert reason == ""


def test_web_request_is_authorized_rejects_missing_token(tmp_path: Path, monkeypatch) -> None:
    config, _service = _make_service(tmp_path)
    monkeypatch.setenv("FLOW_HEALER_WEB_TOKEN", "demo-token")

    allowed, status, reason = _web_request_is_authorized(
        config,
        headers={},
        params={},
    )

    assert allowed is False
    assert status == 401
    assert "token" in reason.lower()
