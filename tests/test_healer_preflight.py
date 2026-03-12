from __future__ import annotations

from pathlib import Path

from flow_healer.healer_preflight import (
    HealerPreflight,
    PreflightReport,
    _probe_monorepo_layout,
    _probe_node_toolchain,
    _preflight_validation_commands,
    execution_root_for_language,
    language_for_execution_root,
    is_stably_ready,
    list_cached_preflight_reports,
    preflight_readiness_assessment,
    summarize_preflight_readiness,
)
from flow_healer.store import SQLiteStore


class _Runner:
    test_gate_mode = "local_only"


class _Connector:
    def ensure_started(self) -> None:
        pass

    def health_snapshot(self) -> dict[str, object]:
        return {
            "available": False,
            "availability_reason": "connector boot failed",
        }


class _BrowserHarness:
    def check_runtime_available(self) -> tuple[bool, str]:
        return False, "playwright runtime is not installed"


def test_probe_connector_respects_available_false_snapshot(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    preflight = HealerPreflight(
        store=store,
        runner=_Runner(),  # type: ignore[arg-type]
        repo_path=tmp_path,
    )

    ok, reason = preflight.probe_connector(_Connector())  # type: ignore[arg-type]

    assert ok is False
    assert reason == "connector boot failed"


def test_probe_browser_runtime_returns_harness_readiness(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    preflight = HealerPreflight(
        store=store,
        runner=_Runner(),  # type: ignore[arg-type]
        repo_path=tmp_path,
    )

    ok, reason = preflight.probe_browser_runtime(_BrowserHarness())  # type: ignore[arg-type]

    assert ok is False
    assert reason == "playwright runtime is not installed"


def test_probe_node_toolchain_detects_pnpm_lock(tmp_path: Path) -> None:
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    probe = _probe_node_toolchain(tmp_path)
    assert probe["required_tool"] == "pnpm"
    assert isinstance(probe["tool_available"], bool)


def test_probe_monorepo_layout_detects_workspace_markers(tmp_path: Path) -> None:
    (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n- apps/*\n", encoding="utf-8")
    probe = _probe_monorepo_layout(tmp_path)
    markers = probe["workspace_markers"]
    assert isinstance(markers, list)
    assert "pnpm-workspace.yaml" in markers


def test_preflight_readiness_assessment_ready_report() -> None:
    report = PreflightReport(
        language="node",
        execution_root="e2e-smoke/node",
        gate_mode="local_only",
        status="ready",
        failure_class="",
        summary="ok",
        output_tail="",
        checked_at="2026-03-10 20:00:00",
        test_summary={},
    )
    assessment = preflight_readiness_assessment(report)
    assert assessment["score"] == 100
    assert assessment["class"] == "ready"
    assert assessment["blocking"] is False


def test_summarize_preflight_readiness_with_blocked_and_missing_reports() -> None:
    reports = [
        PreflightReport(
            language="node",
            execution_root="e2e-smoke/node",
            gate_mode="local_only",
            status="ready",
            failure_class="",
            summary="ok",
            output_tail="",
            checked_at="2026-03-10 20:00:00",
            test_summary={},
        ),
        PreflightReport(
            language="python",
            execution_root="e2e-smoke/python",
            gate_mode="local_only",
            status="failed",
            failure_class="tool_missing",
            summary="no tool",
            output_tail="",
            checked_at="2026-03-10 20:00:00",
            test_summary={},
        ),
        PreflightReport(
            language="node",
            execution_root="e2e-smoke/js-next",
            gate_mode="local_only",
            status="missing",
            failure_class="not_checked",
            summary="not checked",
            output_tail="",
            checked_at="",
            test_summary={},
        ),
    ]
    summary = summarize_preflight_readiness(reports)
    assert summary["total"] == 3
    assert summary["ready"] == 1
    assert summary["blocked"] == 1
    assert summary["unknown"] == 1
    assert summary["overall_class"] == "blocked"
    assert summary["blocking_execution_roots"] == ["e2e-smoke/python"]


def test_preflight_validation_commands_cover_new_languages_and_app_targets() -> None:
    assert _preflight_validation_commands(
        execution_root="e2e-smoke/swift",
        language="swift",
    ) == ("cd e2e-smoke/swift && swift test",)
    assert _preflight_validation_commands(
        execution_root="e2e-smoke/go",
        language="go",
    ) == ("cd e2e-smoke/go && go test ./...",)
    assert _preflight_validation_commands(
        execution_root="e2e-smoke/rust",
        language="rust",
    ) == ("cd e2e-smoke/rust && cargo test",)
    assert _preflight_validation_commands(
        execution_root="e2e-smoke/java-gradle",
        language="java_gradle",
    ) == ("cd e2e-smoke/java-gradle && ./gradlew test --no-daemon",)
    assert _preflight_validation_commands(
        execution_root="e2e-smoke/ruby",
        language="ruby",
    ) == ("cd e2e-smoke/ruby && bundle exec rspec",)
    assert _preflight_validation_commands(
        execution_root="e2e-apps/ruby-rails-web",
        language="ruby",
        framework="rails",
    ) == ("cd e2e-apps/ruby-rails-web && bundle exec rspec",)
    assert _preflight_validation_commands(
        execution_root="e2e-apps/java-spring-web",
        language="java_gradle",
        framework="spring",
    ) == ("cd e2e-apps/java-spring-web && ./gradlew test --no-daemon",)


def test_execution_root_for_language_returns_new_smoke_roots() -> None:
    assert execution_root_for_language("swift") == "e2e-smoke/swift"
    assert execution_root_for_language("go") == "e2e-smoke/go"
    assert execution_root_for_language("rust") == "e2e-smoke/rust"
    assert execution_root_for_language("java_gradle") == "e2e-smoke/java-gradle"
    assert execution_root_for_language("ruby") == "e2e-smoke/ruby"


def test_language_for_execution_root_returns_supported_languages() -> None:
    assert language_for_execution_root("e2e-smoke/python") == "python"
    assert language_for_execution_root("e2e-apps/ruby-rails-web") == "ruby"
    assert language_for_execution_root("e2e-apps/java-spring-web") == "java_gradle"


def test_language_for_execution_root_returns_empty_for_unknown_root() -> None:
    assert language_for_execution_root("e2e-apps/unknown") == ""
    assert language_for_execution_root("") == ""


def test_cached_preflight_reports_include_new_smoke_and_app_targets(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()

    reports = list_cached_preflight_reports(store=store, gate_mode="local_only")
    execution_roots = {report.execution_root for report in reports}

    assert "e2e-smoke/swift" in execution_roots
    assert "e2e-smoke/go" in execution_roots
    assert "e2e-smoke/rust" in execution_roots
    assert "e2e-smoke/java-gradle" in execution_roots
    assert "e2e-smoke/ruby" in execution_roots
    assert "e2e-apps/ruby-rails-web" in execution_roots
    assert "e2e-apps/java-spring-web" in execution_roots


def test_is_stably_ready_requires_both_current_and_prior_ready() -> None:
    report = PreflightReport(
        language="node",
        execution_root="e2e-smoke/node",
        gate_mode="local_only",
        status="ready",
        prior_status="ready",
        prior_checked_at="2026-03-12 05:00:00",
        failure_class="",
        summary="ok",
        output_tail="",
        checked_at="2026-03-12 05:05:00",
        test_summary={},
    )

    assert is_stably_ready(report) is True


def test_is_stably_ready_returns_false_if_prior_missing() -> None:
    report = PreflightReport(
        language="node",
        execution_root="e2e-smoke/node",
        gate_mode="local_only",
        status="ready",
        failure_class="",
        summary="ok",
        output_tail="",
        checked_at="2026-03-12 05:05:00",
        test_summary={},
    )

    assert is_stably_ready(report) is False


def test_ensure_language_ready_preserves_prior_status_on_refresh(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    preflight = HealerPreflight(
        store=store,
        runner=_Runner(),  # type: ignore[arg-type]
        repo_path=tmp_path,
        ttl_seconds=60,
    )
    cached = PreflightReport(
        language="node",
        execution_root="e2e-smoke/node",
        gate_mode="local_only",
        status="ready",
        failure_class="",
        summary="ok",
        output_tail="",
        checked_at="2026-03-12 05:00:00",
        test_summary={},
    )
    store.set_state(
        "healer_preflight:local_only:node:e2e-smoke/node",
        cached.to_state_value(),
    )

    def _fake_run_preflight(*, language: str, framework: str, execution_root: str) -> PreflightReport:
        return PreflightReport(
            language=language,
            execution_root=execution_root,
            gate_mode="local_only",
            status="ready",
            failure_class="",
            summary="ok again",
            output_tail="",
            checked_at="2026-03-12 05:10:00",
            test_summary={},
        )

    preflight._run_preflight = _fake_run_preflight  # type: ignore[method-assign]

    report = preflight.ensure_language_ready(
        language="node",
        execution_root="e2e-smoke/node",
        force=True,
    )

    assert report.prior_status == "ready"
    assert report.prior_checked_at == "2026-03-12 05:00:00"


def test_summarize_preflight_readiness_includes_stably_ready_roots() -> None:
    reports = [
        PreflightReport(
            language="node",
            execution_root="e2e-smoke/node",
            gate_mode="local_only",
            status="ready",
            prior_status="ready",
            prior_checked_at="2026-03-12 05:00:00",
            failure_class="",
            summary="ok",
            output_tail="",
            checked_at="2026-03-12 05:05:00",
            test_summary={},
        ),
        PreflightReport(
            language="python",
            execution_root="e2e-smoke/python",
            gate_mode="local_only",
            status="ready",
            prior_status="failed",
            prior_checked_at="2026-03-12 05:00:00",
            failure_class="",
            summary="ok",
            output_tail="",
            checked_at="2026-03-12 05:05:00",
            test_summary={},
        ),
    ]

    summary = summarize_preflight_readiness(reports)

    assert summary["stably_ready_roots"] == ["e2e-smoke/node"]
