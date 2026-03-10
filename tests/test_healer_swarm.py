from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from flow_healer.healer_runner import HealerRunner
from flow_healer.healer_swarm import (
    HealerSwarm,
    SubagentBackendAdapter,
    SubagentRequest,
    SubagentResult,
)
from flow_healer.healer_task_spec import HealerTaskSpec


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
    ) -> list[SubagentResult]:
        del issue_id, max_parallel
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
