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
        self.test_gate_mode = "docker_only"
        self.local_gate_policy = "auto"
        self.calls: list[tuple[Path, str]] = []

    def validate_workspace(self, workspace: Path, *, task_spec, targeted_tests, mode=None, local_gate_policy=None):
        self.calls.append((workspace, task_spec.execution_root))
        return {"failed_tests": 0, "docker_full_status": "passed", "docker_full_output_tail": "all green"}


def test_preflight_refresh_all_caches_reports_for_supported_languages(tmp_path) -> None:
    for relative in (
        "e2e-smoke/python",
        "e2e-smoke/node",
        "e2e-smoke/go",
        "e2e-smoke/rust",
        "e2e-smoke/java-maven",
        "e2e-smoke/java-gradle",
        "e2e-smoke/ruby",
    ):
        (tmp_path / relative).mkdir(parents=True)

    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    runner = _FakeRunner()
    preflight = HealerPreflight(store=store, runner=runner, repo_path=tmp_path)

    reports = preflight.refresh_all(force=True)

    assert len(reports) == 7
    assert all(report.status == "ready" for report in reports)
    cached = list_cached_preflight_reports(store=store, gate_mode="docker_only")
    assert [report.language for report in cached] == [
        "python",
        "node",
        "go",
        "rust",
        "java_maven",
        "java_gradle",
        "ruby",
    ]
    assert len(runner.calls) == 7


def test_preflight_uses_fresh_cache_before_rerunning(tmp_path) -> None:
    (tmp_path / "e2e-smoke" / "node").mkdir(parents=True)
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    runner = _FakeRunner()
    preflight = HealerPreflight(store=store, runner=runner, repo_path=tmp_path)
    cached = PreflightReport(
        language="node",
        execution_root="e2e-smoke/node",
        gate_mode="docker_only",
        status="ready",
        failure_class="",
        summary="cached",
        output_tail="",
        checked_at="2099-01-01 00:00:00",
        test_summary={"failed_tests": 0},
    )
    store.set_state(preflight_cache_key(gate_mode="docker_only", language="node"), cached.to_state_value())

    report = preflight.ensure_language_ready(language="node", execution_root="e2e-smoke/node")

    assert report.summary == "cached"
    assert runner.calls == []
