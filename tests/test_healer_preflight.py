from __future__ import annotations

from pathlib import Path

from flow_healer.healer_preflight import (
    HealerPreflight,
    PreflightReport,
    list_cached_preflight_reports,
    preflight_cache_key,
)
from flow_healer.store import SQLiteStore


class _FakeRunner:
    def __init__(self) -> None:
        self.test_gate_mode = "local_only"
        self.local_gate_policy = "auto"
        self.calls: list[tuple[Path, str]] = []

    def validate_workspace(self, workspace: Path, *, task_spec, targeted_tests, mode=None, local_gate_policy=None):
        self.calls.append((workspace, task_spec.execution_root))
        return {"failed_tests": 0, "docker_full_status": "passed", "docker_full_output_tail": "all green"}


def test_preflight_refresh_all_caches_reports_for_supported_languages(tmp_path) -> None:
    for relative in (
        "e2e-smoke/python",
        "e2e-smoke/node",
        "e2e-smoke/swift",
    ):
        (tmp_path / relative).mkdir(parents=True)

    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    runner = _FakeRunner()
    preflight = HealerPreflight(store=store, runner=runner, repo_path=tmp_path)

    reports = preflight.refresh_all(force=True)

    assert len(reports) == 3
    assert all(report.status == "ready" for report in reports)
    cached = list_cached_preflight_reports(store=store, gate_mode=runner.test_gate_mode)
    assert [report.language for report in cached] == [
        "python",
        "node",
        "swift",
    ]
    assert len(runner.calls) == 3


def test_preflight_uses_fresh_cache_before_rerunning(tmp_path) -> None:
    (tmp_path / "e2e-smoke" / "node").mkdir(parents=True)
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    runner = _FakeRunner()
    preflight = HealerPreflight(store=store, runner=runner, repo_path=tmp_path)
    cached = PreflightReport(
        language="node",
        execution_root="e2e-smoke/node",
        gate_mode=runner.test_gate_mode,
        status="ready",
        failure_class="",
        summary="cached",
        output_tail="",
        checked_at="2099-01-01 00:00:00",
        test_summary={"failed_tests": 0},
    )
    store.set_state(preflight_cache_key(gate_mode=runner.test_gate_mode, language="node"), cached.to_state_value())

    report = preflight.ensure_language_ready(language="node", execution_root="e2e-smoke/node")

    assert report.summary == "cached"
    assert runner.calls == []


def test_preflight_reports_unsupported_docker_only_mode_for_swift(tmp_path) -> None:
    (tmp_path / "e2e-smoke" / "swift").mkdir(parents=True)
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    runner = _FakeRunner()
    runner.test_gate_mode = "docker_only"
    preflight = HealerPreflight(store=store, runner=runner, repo_path=tmp_path)

    report = preflight.ensure_language_ready(language="swift", execution_root="e2e-smoke/swift", force=True)

    assert report.status == "failed"
    assert report.failure_class == "unsupported_gate_mode"
    assert runner.calls == []


def test_preflight_treats_baseline_test_failures_as_ready(tmp_path) -> None:
    (tmp_path / "e2e-smoke" / "swift").mkdir(parents=True)
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    runner = _FakeRunner()
    runner.test_gate_mode = "local_then_docker"
    runner.validate_workspace = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "failed_tests": 1,
        "local_full_status": "failed",
        "local_full_output_tail": "XCTAssertEqual failed",
    }
    preflight = HealerPreflight(store=store, runner=runner, repo_path=tmp_path)

    report = preflight.ensure_language_ready(language="swift", execution_root="e2e-smoke/swift", force=True)

    assert report.status == "ready"
    assert report.failure_class == ""
    assert "baseline tests currently fail" in report.summary


def test_preflight_still_blocks_environment_gate_failures(tmp_path) -> None:
    (tmp_path / "e2e-smoke" / "swift").mkdir(parents=True)
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    runner = _FakeRunner()
    runner.test_gate_mode = "local_then_docker"
    runner.validate_workspace = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "failed_tests": 1,
        "local_full_status": "failed",
        "local_full_reason": "tool_missing",
        "local_full_output_tail": "swift toolchain missing",
    }
    preflight = HealerPreflight(store=store, runner=runner, repo_path=tmp_path)

    report = preflight.ensure_language_ready(language="swift", execution_root="e2e-smoke/swift", force=True)

    assert report.status == "failed"
    assert report.failure_class == "validation_failed"
