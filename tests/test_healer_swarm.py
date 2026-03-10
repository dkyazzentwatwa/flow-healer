from __future__ import annotations

import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock

from flow_healer.healer_runner import HealerRunner
from flow_healer.healer_swarm import (
    ConnectorSubagentBackend,
    HealerSwarm,
    SubagentBackendAdapter,
    SubagentRequest,
    SubagentResult,
)
from flow_healer.healer_task_spec import HealerTaskSpec
from flow_healer.swarm_markers import SWARM_PROCESS_MARKER


class _Backend(SubagentBackendAdapter):
    def __init__(self, workspace: Path, *, quarantine: bool = False) -> None:
        self.workspace = workspace
        self.quarantine = quarantine
        self.roles: list[str] = []

    def run(self, request: SubagentRequest, *, issue_id: str) -> SubagentResult:
        del issue_id
        self.roles.append(request.role)
        if request.role == "recovery-manager":
            if self.quarantine:
                parsed = {
                    "strategy": "quarantine",
                    "summary": "Scope guard blocked direct repair.",
                    "root_cause": "unsafe scope",
                    "edit_scope": [],
                    "targeted_tests": [],
                    "validation_focus": [],
                }
            else:
                parsed = {
                    "strategy": "repair",
                    "summary": "Repair the demo module directly.",
                    "root_cause": "broken return value",
                    "edit_scope": ["src/demo.py"],
                    "targeted_tests": ["tests/test_demo.py"],
                    "validation_focus": ["demo"],
                }
            return SubagentResult(role=request.role, raw="{}", parsed=parsed, success=True)
        if request.role == "repair-executor":
            target = self.workspace / "src" / "demo.py"
            target.write_text("def demo():\n    return 'fixed'\n", encoding="utf-8")
            return SubagentResult(role=request.role, raw="edited demo", parsed={}, success=True)
        raise AssertionError(f"unexpected role: {request.role}")

    def run_parallel(
        self,
        requests: list[SubagentRequest],
        *,
        issue_id: str,
        max_parallel: int,
        on_result=None,
        overall_timeout_seconds=None,
    ) -> list[SubagentResult]:
        del issue_id, max_parallel, overall_timeout_seconds
        results: list[SubagentResult] = []
        for request in requests:
            self.roles.append(request.role)
            if request.role == "scope-guard" and self.quarantine:
                parsed = {
                    "allow_repair": False,
                    "edit_scope": [],
                    "should_quarantine": True,
                    "reason": "Would widen beyond safe scope.",
                }
            else:
                parsed = {
                    "allow_repair": True,
                    "edit_scope": ["src/demo.py"],
                    "likely_paths": ["src/demo.py"],
                    "targeted_tests": ["tests/test_demo.py"],
                    "failing_surfaces": ["demo"],
                    "reason": f"{request.role} analyzed the failure.",
                }
            result = SubagentResult(role=request.role, raw="{}", parsed=parsed, success=True)
            if on_result is not None:
                on_result(result)
            results.append(result)
        return results


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)
    (repo / "src" / "demo.py").write_text("def demo():\n    return 'broken'\n", encoding="utf-8")
    (repo / "tests" / "test_demo.py").write_text("def test_demo():\n    assert True\n", encoding="utf-8")
    _git(tmp_path, "init", str(repo))
    _git(repo, "config", "user.email", "demo@example.com")
    _git(repo, "config", "user.name", "Demo")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_healer_swarm_recovers_with_repair_plan(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    runner = HealerRunner(connector=MagicMock(), timeout_seconds=30, test_gate_mode="local_only")
    monkeypatch.setattr(
        runner,
        "validate_workspace",
        lambda workspace, *, task_spec, targeted_tests, timeout_seconds=None, mode=None, local_gate_policy=None: {
            "failed_tests": 0,
            "targeted_tests": list(targeted_tests),
            "mode": "local_only",
            "execution_root": "",
        },
    )
    swarm = HealerSwarm(_Backend(repo))
    outcome = swarm.recover(
        issue_id="1",
        issue_title="Fix demo",
        issue_body="Fix src/demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("src/demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        learned_context="",
        feedback_context="",
        failure_class="tests_failed",
        failure_reason="demo failed",
        proposer_output="first try",
        test_summary={"failed_tests": 1},
        verifier_summary={},
        workspace_status={},
        workspace=repo,
        runner=runner,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=["tests/test_demo.py"],
    )

    assert outcome.recovered is True
    assert outcome.run_result is not None
    assert outcome.run_result.diff_paths == ["src/demo.py"]
    assert outcome.plan.strategy == "repair"
    summary = outcome.as_summary()
    assert summary["strategy"] == "repair"
    assert summary["roles"]


def test_healer_swarm_respects_quarantine_plan(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    swarm = HealerSwarm(_Backend(repo, quarantine=True))
    outcome = swarm.recover(
        issue_id="2",
        issue_title="Fix demo",
        issue_body="Fix src/demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("src/demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        learned_context="",
        feedback_context="",
        failure_class="scope_violation",
        failure_reason="unsafe",
        proposer_output="first try",
        test_summary={"failed_tests": 1},
        verifier_summary={},
        workspace_status={},
        workspace=repo,
        runner=MagicMock(),
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert outcome.recovered is False
    assert outcome.strategy == "quarantine"
    assert outcome.failure_reason == "Scope guard blocked direct repair."


def test_healer_swarm_emits_telemetry_callbacks(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    runner = HealerRunner(connector=MagicMock(), timeout_seconds=30, test_gate_mode="local_only")
    monkeypatch.setattr(
        runner,
        "validate_workspace",
        lambda workspace, *, task_spec, targeted_tests, timeout_seconds=None, mode=None, local_gate_policy=None: {
            "failed_tests": 0,
            "targeted_tests": list(targeted_tests),
            "mode": "local_only",
            "execution_root": "",
        },
    )
    events: list[tuple[str, dict[str, object]]] = []
    swarm = HealerSwarm(_Backend(repo))

    outcome = swarm.recover(
        issue_id="telemetry-1",
        issue_title="Fix demo",
        issue_body="Fix src/demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("src/demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        learned_context="",
        feedback_context="",
        failure_class="tests_failed",
        failure_reason="demo failed",
        proposer_output="first try",
        test_summary={"failed_tests": 1},
        verifier_summary={},
        workspace_status={},
        workspace=repo,
        runner=runner,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=["tests/test_demo.py"],
        telemetry_callback=lambda event_type, payload: events.append((event_type, payload)),
    )

    event_types = [event_type for event_type, _ in events]

    assert outcome.recovered is True
    assert event_types[0] == "swarm_started"
    assert "swarm_plan_ready" in event_types
    assert event_types[-1] == "swarm_finished"
    role_events = [payload for event_type, payload in events if event_type == "swarm_role_completed"]
    role_names = {str(payload.get("role") or "") for payload in role_events}
    assert {"failure-triager", "patch-critic", "scope-guard", "test-forensics", "recovery-manager", "repair-executor"}.issubset(role_names)


def test_connector_subagent_backend_run_parallel_marks_timed_out_roles() -> None:
    class _FakeConnector:
        def reset_thread(self, sender: str) -> str:
            return sender

        def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
            del prompt, timeout_seconds
            if ":slow:" in thread_id:
                time.sleep(0.20)
            return '{"summary":"ok"}'

        def shutdown(self) -> None:
            return None

    backend = ConnectorSubagentBackend(
        connector=_FakeConnector(),
        connector_factory=lambda: _FakeConnector(),
    )
    seen: list[SubagentResult] = []
    results = backend.run_parallel(
        [
            SubagentRequest(role="slow", prompt="slow", timeout_seconds=30),
            SubagentRequest(role="fast", prompt="fast", timeout_seconds=30),
        ],
        issue_id="timeout-case",
        max_parallel=2,
        overall_timeout_seconds=0.05,
        on_result=seen.append,
    )

    by_role = {result.role: result for result in results}
    assert set(by_role.keys()) == {"fast", "slow"}
    assert by_role["fast"].success is True
    assert by_role["slow"].success is False
    assert "Timed out waiting for subagent result" in by_role["slow"].error
    assert any(result.role == "slow" and not result.success for result in seen)


def test_healer_swarm_emits_timeout_telemetry_for_timed_out_analysis_role(tmp_path) -> None:
    class _TimeoutBackend(SubagentBackendAdapter):
        def run(self, request: SubagentRequest, *, issue_id: str) -> SubagentResult:
            del issue_id
            if request.role == "recovery-manager":
                return SubagentResult(
                    role="recovery-manager",
                    raw="{}",
                    parsed={
                        "strategy": "quarantine",
                        "summary": "Timed-out analyzer; skip repair.",
                        "root_cause": "timeout",
                        "edit_scope": [],
                        "targeted_tests": [],
                        "validation_focus": [],
                    },
                    success=True,
                )
            raise AssertionError("unexpected direct run role")

        def run_parallel(
            self,
            requests: list[SubagentRequest],
            *,
            issue_id: str,
            max_parallel: int,
            on_result=None,
            overall_timeout_seconds=None,
        ) -> list[SubagentResult]:
            del issue_id, max_parallel, overall_timeout_seconds
            results: list[SubagentResult] = []
            for request in requests:
                if request.role == "test-forensics":
                    result = SubagentResult(
                        role=request.role,
                        raw="",
                        parsed={},
                        success=False,
                        error="Timed out waiting for subagent result after 42s.",
                    )
                else:
                    result = SubagentResult(
                        role=request.role,
                        raw="{}",
                        parsed={"reason": "ok"},
                        success=True,
                    )
                if on_result is not None:
                    on_result(result)
                results.append(result)
            return results

    events: list[tuple[str, dict[str, object]]] = []
    swarm = HealerSwarm(_TimeoutBackend())
    outcome = swarm.recover(
        issue_id="timeout-telemetry",
        issue_title="Fix demo",
        issue_body="Fix src/demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("src/demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        learned_context="",
        feedback_context="",
        failure_class="tests_failed",
        failure_reason="demo failed",
        proposer_output="first try",
        test_summary={"failed_tests": 1},
        verifier_summary={},
        workspace_status={},
        workspace=tmp_path,
        runner=MagicMock(),
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
        telemetry_callback=lambda event_type, payload: events.append((event_type, payload)),
    )

    event_types = [event_type for event_type, _ in events]
    assert outcome.recovered is False
    assert "swarm_role_timeout" in event_types
    assert event_types[-1] == "swarm_finished"


def test_healer_swarm_emits_timeout_telemetry_for_timed_out_planning_role(tmp_path) -> None:
    class _PlanningTimeoutBackend(SubagentBackendAdapter):
        def run(self, request: SubagentRequest, *, issue_id: str) -> SubagentResult:
            del issue_id
            if request.role != "recovery-manager":
                raise AssertionError("unexpected direct run role")
            assert SWARM_PROCESS_MARKER in request.prompt
            return SubagentResult(
                role=request.role,
                raw="",
                parsed={},
                success=False,
                error="Timed out waiting for subagent result after 33s.",
            )

        def run_parallel(
            self,
            requests: list[SubagentRequest],
            *,
            issue_id: str,
            max_parallel: int,
            on_result=None,
            overall_timeout_seconds=None,
        ) -> list[SubagentResult]:
            del issue_id, max_parallel, overall_timeout_seconds
            results: list[SubagentResult] = []
            for request in requests:
                assert SWARM_PROCESS_MARKER in request.prompt
                result = SubagentResult(
                    role=request.role,
                    raw="{}",
                    parsed={"reason": "ok"},
                    success=True,
                )
                if on_result is not None:
                    on_result(result)
                results.append(result)
            return results

    events: list[tuple[str, dict[str, object]]] = []
    runner = MagicMock()
    swarm = HealerSwarm(_PlanningTimeoutBackend())
    outcome = swarm.recover(
        issue_id="timeout-planning",
        issue_title="Fix demo",
        issue_body="Fix src/demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("src/demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        learned_context="",
        feedback_context="",
        failure_class="tests_failed",
        failure_reason="demo failed",
        proposer_output="first try",
        test_summary={"failed_tests": 1},
        verifier_summary={},
        workspace_status={},
        workspace=tmp_path,
        runner=runner,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
        telemetry_callback=lambda event_type, payload: events.append((event_type, payload)),
    )

    event_types = [event_type for event_type, _ in events]
    assert outcome.recovered is False
    assert outcome.failure_class == "swarm_timeout"
    assert "swarm_role_timeout" in event_types
    assert "swarm_recovery_timeout" in event_types
    assert event_types[-1] == "swarm_finished"
    runner.evaluate_existing_workspace.assert_not_called()


def test_healer_swarm_emits_timeout_telemetry_for_timed_out_repair_role(tmp_path) -> None:
    class _RepairTimeoutBackend(SubagentBackendAdapter):
        def __init__(self) -> None:
            self.seen_manager_prompt = ""
            self.seen_repair_prompt = ""

        def run(self, request: SubagentRequest, *, issue_id: str) -> SubagentResult:
            del issue_id
            if request.role == "recovery-manager":
                self.seen_manager_prompt = request.prompt
                return SubagentResult(
                    role=request.role,
                    raw="{}",
                    parsed={
                        "strategy": "repair",
                        "summary": "Proceed with repair.",
                        "root_cause": "timeout",
                        "edit_scope": ["src/demo.py"],
                        "targeted_tests": [],
                        "validation_focus": [],
                    },
                    success=True,
                )
            if request.role == "repair-executor":
                self.seen_repair_prompt = request.prompt
                return SubagentResult(
                    role=request.role,
                    raw="",
                    parsed={},
                    success=False,
                    error="Timed out waiting for subagent result after 44s.",
                )
            raise AssertionError("unexpected direct run role")

        def run_parallel(
            self,
            requests: list[SubagentRequest],
            *,
            issue_id: str,
            max_parallel: int,
            on_result=None,
            overall_timeout_seconds=None,
        ) -> list[SubagentResult]:
            del issue_id, max_parallel, overall_timeout_seconds
            results: list[SubagentResult] = []
            for request in requests:
                assert SWARM_PROCESS_MARKER in request.prompt
                result = SubagentResult(
                    role=request.role,
                    raw="{}",
                    parsed={"reason": "ok"},
                    success=True,
                )
                if on_result is not None:
                    on_result(result)
                results.append(result)
            return results

    events: list[tuple[str, dict[str, object]]] = []
    backend = _RepairTimeoutBackend()
    runner = MagicMock()
    runner.code_change_turn_timeout_seconds = 60
    runner.timeout_seconds = 60
    swarm = HealerSwarm(backend)
    outcome = swarm.recover(
        issue_id="timeout-repair",
        issue_title="Fix demo",
        issue_body="Fix src/demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("src/demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        learned_context="",
        feedback_context="",
        failure_class="tests_failed",
        failure_reason="demo failed",
        proposer_output="first try",
        test_summary={"failed_tests": 1},
        verifier_summary={},
        workspace_status={},
        workspace=tmp_path,
        runner=runner,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
        telemetry_callback=lambda event_type, payload: events.append((event_type, payload)),
    )

    event_types = [event_type for event_type, _ in events]
    assert outcome.recovered is False
    assert outcome.failure_class == "swarm_timeout"
    assert "swarm_role_timeout" in event_types
    assert "swarm_recovery_timeout" in event_types
    assert event_types[-1] == "swarm_finished"
    assert SWARM_PROCESS_MARKER in backend.seen_manager_prompt
    assert SWARM_PROCESS_MARKER in backend.seen_repair_prompt
    runner.evaluate_existing_workspace.assert_not_called()
