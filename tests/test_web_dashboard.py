from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import urlopen

from flow_healer.config import AppConfig, RelaySettings, ServiceSettings
from flow_healer.service import FlowHealerService
from flow_healer.web_dashboard import (
    DashboardServer,
    _collect_activity,
    _collect_recent_logs,
    _issue_detail_payload,
    _overview_payload,
    _queue_payload,
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


def test_overview_payload_preserves_repo_trust_rows(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    def fake_cached_status_rows(repo_name=None, *, force_refresh=False, probe_connector=False):
        return [
            {
                "repo": "demo",
                "recent_attempts": [],
                "trust": {
                    "state": "quarantined",
                    "score": 12,
                    "summary": "Circuit breaker is open after repeated failures.",
                    "why_runnable": "",
                    "why_blocked": "Healing is suspended until the repo stabilizes.",
                    "recommended_operator_action": "inspect_circuit_breaker",
                    "dominant_failure_domain": "infra",
                    "evidence": {"circuit_breaker_open": True},
                },
            }
        ]

    service.cached_status_rows = fake_cached_status_rows  # type: ignore[method-assign]

    payload = _overview_payload(config, service)

    assert payload["rows"][0]["trust"]["state"] == "quarantined"
    assert payload["rows"][0]["trust"]["recommended_operator_action"] == "inspect_circuit_breaker"


def test_overview_and_issue_detail_payloads_surface_harness_health(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)
    store_path = config.repo_db_path("demo")

    from flow_healer.store import SQLiteStore

    store = SQLiteStore(store_path)
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="913",
        repo="owner/repo",
        title="Harness issue",
        body="Validation:\n- pytest",
        author="alice",
        labels=["healer:ready"],
        priority=1,
    )
    store.close()

    harness_health = {
        "artifact_publish": {"failures": 2, "capture_failures": 1},
        "browser_failure_families": {"counts": {"runtime_boot": 1}},
        "stale_runtime_profiles": {"count": 1, "profiles": ["web"]},
        "orphan_cleanup": {
            "app_runtimes_reaped": 3,
            "artifact_roots_cleaned": 4,
            "browser_sessions_cleaned": 1,
            "tracked_browser_sessions": 1,
        },
        "browser_sessions": {"tracked": 1, "existing_roots": 1, "stale_roots": 0},
        "runtime_profiles": [
            {
                "profile": "web",
                "configured": True,
                "status": "stale",
                "stale": True,
                "last_seen_at": "2026-03-10 12:30:00",
                "last_canary_at": "2026-03-10 12:00:00",
            }
        ],
        "canary_profiles": {
            "failures": 1,
            "profiles": [
                {
                    "profile": "web",
                    "status": "stale",
                    "last_seen_at": "2026-03-10 12:30:00",
                    "last_canary_at": "2026-03-10 12:00:00",
                }
            ],
        },
    }

    def fake_cached_status_rows(repo_name=None, *, force_refresh=False, probe_connector=False):
        return [
            {
                "repo": "demo",
                "path": "/tmp/demo",
                "paused": False,
                "issues_total": 1,
                "recent_attempts": [],
                "issue_explanations": [
                    {
                        "issue_id": "913",
                        "summary": "Harness checks failed on the last attempt.",
                        "recommended_action": "inspect_recent_failure",
                    }
                ],
                "trust": {"state": "degraded", "summary": "Repo needs harness attention."},
                "policy": {"summary": "Inspect harness health before retrying."},
                "harness_health": harness_health,
                "reliability_daily_rollups": [
                    {
                        "day": "2026-03-10",
                        "sample_size": 2,
                        "issue_count": 1,
                        "first_pass_success_rate": 0.0,
                        "retries_per_success": 0.0,
                        "wrong_root_execution_rate": 0.0,
                        "no_op_rate": 0.0,
                        "mean_time_to_valid_pr_minutes": 0.0,
                        "harness": {
                            "artifact_publish_failures": 1,
                            "artifact_capture_failures": 0,
                            "browser_failure_families": {"runtime_boot": 1},
                        },
                    }
                ],
            }
        ]

    service.cached_status_rows = fake_cached_status_rows  # type: ignore[method-assign]

    overview = _overview_payload(config, service)
    detail = _issue_detail_payload(config, service, repo_name="demo", issue_id="913")

    assert overview["rows"][0]["harness_health"]["artifact_publish"]["failures"] == 2
    assert overview["chart_series"]["harness"][0]["artifact_publish_failures"] == 1
    assert overview["chart_series"]["harness"][0]["browser_failure_total"] == 1
    assert detail["repo"]["harness_health"]["stale_runtime_profiles"]["profiles"] == ["web"]
    assert detail["repo"]["harness_health"]["canary_profiles"]["profiles"][0]["profile"] == "web"


def test_queue_payload_builds_saved_views_and_issue_rows(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)
    store_path = config.repo_db_path("demo")

    from flow_healer.store import SQLiteStore

    store = SQLiteStore(store_path)
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="810",
        repo="owner/repo",
        title="Queued issue",
        body="Required code outputs:\n- src/add.py",
        author="alice",
        labels=["healer:ready"],
        priority=1,
    )
    store.upsert_healer_issue(
        issue_id="811",
        repo="owner/repo",
        title="Running issue",
        body="Running body",
        author="alice",
        labels=["healer:ready"],
        priority=2,
    )
    store.upsert_healer_issue(
        issue_id="812",
        repo="owner/repo",
        title="Blocked issue",
        body="Blocked body",
        author="alice",
        labels=["healer:ready"],
        priority=3,
    )
    store.upsert_healer_issue(
        issue_id="813",
        repo="owner/repo",
        title="PR issue",
        body="PR body",
        author="alice",
        labels=["healer:ready"],
        priority=4,
    )
    store.set_healer_issue_state(issue_id="811", state="running")
    store.set_healer_issue_state(
        issue_id="812",
        state="blocked",
        last_failure_class="no_patch",
        last_failure_reason="Patch generation failed twice.",
    )
    store.set_healer_issue_state(issue_id="813", state="pr_open", pr_number=88, pr_state="open")
    store.close()

    def fake_cached_status_rows(repo_name=None, *, force_refresh=False, probe_connector=False):
        return [
            {
                "repo": "demo",
                "path": "/tmp/demo",
                "paused": False,
                "issues_total": 4,
                "recent_attempts": [],
                "issue_explanations": [
                    {
                        "issue_id": "812",
                        "state": "blocked",
                        "reason_code": "last_attempt_failed",
                        "summary": "Repeated no-patch failures mean this issue needs operator review.",
                        "recommended_action": "inspect_issue_contract",
                        "blocking": True,
                        "evidence": {},
                    }
                ],
                "trust": {
                    "state": "degraded",
                    "score": 62,
                    "summary": "Repo is runnable but recent failures need attention.",
                    "why_runnable": "Most issues remain eligible for healing.",
                    "why_blocked": "",
                    "recommended_operator_action": "observe_repo",
                    "dominant_failure_domain": "contract",
                    "evidence": {},
                },
                "policy": {
                    "outcome": "retry",
                    "recommendation": "observe_repo",
                    "summary": "Autonomous healing can continue.",
                    "reason_code": "continue_autonomous_healing",
                    "evidence": {},
                },
            }
        ]

    service.cached_status_rows = fake_cached_status_rows  # type: ignore[method-assign]

    payload = _queue_payload(config, service)

    assert payload["summary"]["total"] == 4
    assert payload["summary"]["running"] == 1
    assert payload["summary"]["blocked"] == 1
    assert payload["summary"]["pr_open"] == 1
    assert [view["id"] for view in payload["views"]] == [
        "all",
        "queued",
        "running",
        "blocked",
        "pr_open",
        "needs_review",
    ]
    blocked = next(row for row in payload["rows"] if row["issue_id"] == "812")
    assert blocked["failure_summary"] == "Patch generation failed twice."
    assert blocked["recommended_action"] == "inspect_issue_contract"
    assert blocked["repo_trust_state"] == "degraded"
    pr_open = next(row for row in payload["rows"] if row["issue_id"] == "813")
    assert pr_open["pr_badge"] == "#88"


def test_issue_detail_payload_includes_issue_attempts_and_related_activity(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)
    state_root = Path(config.service.state_root).expanduser().resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "flow-healer.log").write_text(
        "2026-03-11 09:47:23 ERROR apple_flow.healer_loop: Issue #910 failed in repo demo on healer/issue-910-test PR #411\n",
        encoding="utf-8",
    )
    store_path = config.repo_db_path("demo")

    from flow_healer.store import SQLiteStore

    store = SQLiteStore(store_path)
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="910",
        repo="owner/repo",
        title="Node sandbox regression",
        body="Required code outputs:\n- e2e-smoke/node/src/add.js\n\nValidation:\n- cd e2e-smoke/node && npm test",
        author="alice",
        labels=["healer:ready"],
        priority=1,
    )
    store.set_healer_issue_state(
        issue_id="910",
        state="blocked",
        last_failure_class="tests_failed",
        last_failure_reason="Targeted node validation failed.",
        feedback_context="Focus on e2e-smoke/node validation.",
    )
    store.create_healer_attempt(
        attempt_id="ha_910_1",
        issue_id="910",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
        task_kind="code",
        output_targets=["e2e-smoke/node/src/add.js"],
    )
    store.finish_healer_attempt(
        attempt_id="ha_910_1",
        state="failed",
        actual_diff_set=["e2e-smoke/node/src/add.js"],
        test_summary={
            "failed_tests": 1,
            "validation_commands": ["npm test"],
            "judgment_summary": {
                "reason_code": "product_ambiguity",
                "summary": "The issue needs a human product decision.",
            },
            "escalation_packet": {
                "reason_code": "product_ambiguity",
                "decision_needed": "Choose whether the dashboard should preserve the old copy or adopt the new wording.",
            },
        },
        verifier_summary={"status": "failed"},
        artifact_bundle={
            "status": "captured",
            "artifact_root": str((state_root / "artifacts" / "910").resolve()),
        },
        artifact_links=[
            {
                "label": "failure_screenshot",
                "path": str((state_root / "artifacts" / "910" / "failure.png").resolve()),
            }
        ],
        ci_status_summary={
            "overall_state": "failure",
            "failing_contexts": ["CI"],
        },
        failure_class="tests_failed",
        failure_reason="Expected 4 to equal 5",
    )
    store.close()
    (state_root / "artifacts" / "910").mkdir(parents=True, exist_ok=True)
    (state_root / "artifacts" / "910" / "failure.png").write_bytes(b"pngdata")

    def fake_cached_status_rows(repo_name=None, *, force_refresh=False, probe_connector=False):
        return [
            {
                "repo": "demo",
                "path": "/tmp/demo",
                "paused": False,
                "issues_total": 1,
                "recent_attempts": [],
                "issue_explanations": [
                    {
                        "issue_id": "910",
                        "state": "blocked",
                        "reason_code": "last_attempt_failed",
                        "summary": "Targeted validation failed on the last attempt.",
                        "recommended_action": "inspect_issue_contract",
                        "blocking": True,
                        "evidence": {},
                    }
                ],
                "trust": {
                    "state": "degraded",
                    "score": 51,
                    "summary": "Repo is runnable but waiting on a fix for the current blocked issue.",
                    "why_runnable": "Only one issue is blocked.",
                    "why_blocked": "Issue #910 is blocked on tests.",
                    "recommended_operator_action": "inspect_issue_contract",
                    "dominant_failure_domain": "tests",
                    "evidence": {},
                },
                "policy": {
                    "outcome": "review",
                    "recommendation": "inspect_issue_contract",
                    "summary": "Review the blocked issue before retrying.",
                    "reason_code": "last_attempt_failed",
                    "evidence": {},
                },
            }
        ]

    service.cached_status_rows = fake_cached_status_rows  # type: ignore[method-assign]

    payload = _issue_detail_payload(config, service, repo_name="demo", issue_id="910")

    assert payload["found"] is True
    assert payload["issue"]["issue_id"] == "910"
    assert "e2e-smoke/node/src/add.js" in payload["issue"]["body"]
    assert payload["issue"]["failure_summary"] == "Targeted node validation failed."
    assert payload["issue"]["recommended_action"] == "inspect_issue_contract"
    assert len(payload["attempts"]) == 1
    assert payload["attempts"][0]["attempt_id"] == "ha_910_1"
    assert payload["attempts"][0]["test_summary"]["validation_commands"] == ["npm test"]
    assert payload["attempts"][0]["artifact_bundle"]["artifact_root"].endswith("artifacts/910")
    assert payload["attempts"][0]["artifact_links"][0]["label"] == "failure_screenshot"
    assert payload["attempts"][0]["artifact_links"][0]["web_href"].startswith("/artifact?path=")
    assert payload["attempts"][0]["ci_status_summary"]["overall_state"] == "failure"
    assert payload["attempts"][0]["judgment_summary"]["reason_code"] == "product_ambiguity"
    assert payload["attempts"][0]["escalation_packet"]["decision_needed"].startswith("Choose whether the dashboard")
    assert payload["issue"]["promotion_state"] == "merge_blocked"
    assert any(item["issue_id"] == "910" for item in payload["activity"])
    assert payload["repo"]["trust"]["state"] == "degraded"


def test_dashboard_server_serves_queue_endpoint(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)
    store_path = config.repo_db_path("demo")

    from flow_healer.store import SQLiteStore

    store = SQLiteStore(store_path)
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="1201",
        repo="owner/repo",
        title="Queued issue",
        body="Required code outputs:\n- src/add.py",
        author="alice",
        labels=["healer:ready"],
        priority=1,
    )
    store.close()

    service.cached_status_rows = lambda *args, **kwargs: [  # type: ignore[method-assign]
        {
            "repo": "demo",
            "path": "/tmp/demo",
            "paused": False,
            "issues_total": 1,
            "recent_attempts": [],
            "issue_explanations": [],
            "trust": {"state": "ready", "summary": "Ready for healing."},
            "policy": {"summary": "Continue autonomous healing."},
        }
    ]

    class DummyRouter:
        def execute(self, **kwargs):  # pragma: no cover - GET-only test stub
            return {"ok": True}

    server = DashboardServer(config=config, service=service, router=DummyRouter(), host="127.0.0.1", port=0)
    server.start()
    try:
        port = server._httpd.server_address[1]  # type: ignore[union-attr]
        with urlopen(f"http://127.0.0.1:{port}/api/queue", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.stop()

    assert response.status == 200
    assert payload["summary"]["total"] == 1
    assert payload["rows"][0]["issue_id"] == "1201"
    assert payload["views"][0]["id"] == "all"


def test_dashboard_server_serves_issue_detail_endpoint(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)
    store_path = config.repo_db_path("demo")

    from flow_healer.store import SQLiteStore

    store = SQLiteStore(store_path)
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="1202",
        repo="owner/repo",
        title="Blocked issue",
        body="Validation:\n- pytest",
        author="alice",
        labels=["healer:ready"],
        priority=1,
    )
    store.set_healer_issue_state(
        issue_id="1202",
        state="blocked",
        last_failure_class="tests_failed",
        last_failure_reason="Pytest failed.",
    )
    store.create_healer_attempt(
        attempt_id="ha_1202_1",
        issue_id="1202",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="ha_1202_1",
        state="failed",
        actual_diff_set=[],
        test_summary={"failed_tests": 1},
        verifier_summary={"status": "failed"},
        failure_class="tests_failed",
        failure_reason="Assertion failed",
    )
    store.close()

    service.cached_status_rows = lambda *args, **kwargs: [  # type: ignore[method-assign]
        {
            "repo": "demo",
            "path": "/tmp/demo",
            "paused": False,
            "issues_total": 1,
            "recent_attempts": [],
            "issue_explanations": [
                {
                    "issue_id": "1202",
                    "summary": "Validation failed on the last attempt.",
                    "recommended_action": "inspect_issue_contract",
                }
            ],
            "trust": {"state": "degraded", "summary": "Repo needs review."},
            "policy": {"summary": "Inspect before retrying."},
        }
    ]

    class DummyRouter:
        def execute(self, **kwargs):  # pragma: no cover - GET-only test stub
            return {"ok": True}

    server = DashboardServer(config=config, service=service, router=DummyRouter(), host="127.0.0.1", port=0)
    server.start()
    try:
        port = server._httpd.server_address[1]  # type: ignore[union-attr]
        with urlopen(f"http://127.0.0.1:{port}/api/issue-detail?repo=demo&issue_id=1202", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.stop()

    assert response.status == 200
    assert payload["found"] is True
    assert payload["issue"]["issue_id"] == "1202"
    assert payload["attempts"][0]["attempt_id"] == "ha_1202_1"
    assert payload["repo"]["name"] == "demo"


def test_dashboard_server_serves_local_artifact_endpoint(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)
    state_root = Path(config.service.state_root).expanduser().resolve()
    artifact_path = state_root / "artifacts" / "sample.png"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"pngdata")

    class DummyRouter:
        def execute(self, **kwargs):  # pragma: no cover - GET-only test stub
            return {"ok": True}

    server = DashboardServer(config=config, service=service, router=DummyRouter(), host="127.0.0.1", port=0)
    server.start()
    try:
        port = server._httpd.server_address[1]  # type: ignore[union-attr]
        with urlopen(f"http://127.0.0.1:{port}/artifact?path={quote_plus(str(artifact_path))}", timeout=5) as response:
            payload = response.read()
            content_type = response.headers.get("Content-Type")
    finally:
        server.stop()

    assert payload == b"pngdata"
    assert content_type == "image/png"


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


def test_render_dashboard_returns_minimal_api_landing_page(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="")

    assert "<title>Flow Healer API Server</title>" in html
    assert "flow-healer export" in html
    assert "flow-healer tui" in html
    assert "/api/queue" in html
    assert "/api/issue-detail" in html


def test_render_dashboard_does_not_embed_any_frontend_app_assets(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="")

    assert "/assets/dashboard.css" not in html
    assert "/assets/dashboard.js" not in html
    assert "window.__FLOW_HEALER_BOOTSTRAP__" not in html


def test_render_dashboard_surfaces_notice_without_bootstrap_script(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    html = _render_dashboard(config, service, notice="scan completed")

    assert "scan completed" in html
    assert "window.__FLOW_HEALER_BOOTSTRAP__" not in html


def test_dashboard_server_does_not_serve_removed_dashboard_assets(tmp_path: Path) -> None:
    config, service = _make_service(tmp_path)

    class DummyRouter:
        def execute(self, **kwargs):  # pragma: no cover - asset-only test stub
            return {"ok": True}

    server = DashboardServer(config=config, service=service, router=DummyRouter(), host="127.0.0.1", port=0)
    server.start()
    try:
        port = server._httpd.server_address[1]  # type: ignore[union-attr]
        try:
            urlopen(f"http://127.0.0.1:{port}/assets/dashboard.css", timeout=5)
        except Exception as exc:
            error = exc
        else:  # pragma: no cover - regression guard
            error = None
    finally:
        server.stop()

    assert error is not None
    assert "404" in str(error)


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
