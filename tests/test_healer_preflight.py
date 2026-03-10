from __future__ import annotations

from pathlib import Path

from flow_healer.healer_preflight import (
    HealerPreflight,
    PreflightReport,
    _probe_monorepo_layout,
    _probe_node_toolchain,
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
