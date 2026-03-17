from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

import pytest

from flow_healer.healer_planner import (
    HealerPlanner,
    PlanResult,
    _build_planning_prompt,
    _parse_plan_json,
    _validate_plan_scope,
)
from flow_healer.healer_task_spec import HealerTaskSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task_spec(
    output_targets: tuple[str, ...] = (),
    execution_root: str = "",
    validation_commands: tuple[str, ...] = (),
    input_context_paths: tuple[str, ...] = (),
) -> HealerTaskSpec:
    return HealerTaskSpec(
        task_kind="fix",
        output_mode="patch",
        output_targets=output_targets,
        tool_policy="repo_only",
        validation_profile="code_change",
        execution_root=execution_root,
        validation_commands=validation_commands,
        input_context_paths=input_context_paths,
    )


def _plan_json(**extra: Any) -> str:
    obj = {
        "approach": "Fix the off-by-one error in loop counter.",
        "files_to_touch": ["src/counter.py"],
        "validation_commands": ["pytest tests/test_counter.py"],
        "scope_summary": "Only src/counter.py is changed.",
        **extra,
    }
    return f"```json\n{json.dumps(obj)}\n```"


@dataclass
class _StubConnector:
    """Minimal stub: returns canned output from run_turn."""

    output: str = ""
    threads: list[str] = field(default_factory=list)

    def get_or_create_thread(self, sender: str) -> str:
        self.threads.append(sender)
        return f"thread_{sender}"

    def reset_thread(self, sender: str) -> str:
        return f"reset_{sender}"

    def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
        return self.output

    def ensure_started(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


# ---------------------------------------------------------------------------
# _parse_plan_json
# ---------------------------------------------------------------------------


def test_parse_plan_json_fenced_block():
    raw = _plan_json()
    result = _parse_plan_json(raw)
    assert result is not None
    assert result["files_to_touch"] == ["src/counter.py"]
    assert "approach" in result


def test_parse_plan_json_bare_json():
    obj = {
        "approach": "Fix bug",
        "files_to_touch": ["src/mod.py"],
        "validation_commands": ["pytest"],
        "scope_summary": "narrow",
    }
    result = _parse_plan_json(json.dumps(obj))
    assert result is not None
    assert result["files_to_touch"] == ["src/mod.py"]


def test_parse_plan_json_returns_none_on_empty():
    assert _parse_plan_json("") is None
    assert _parse_plan_json("   ") is None


def test_parse_plan_json_returns_none_on_missing_key():
    obj = {"approach": "fix", "scope_summary": "narrow"}
    assert _parse_plan_json(f"```json\n{json.dumps(obj)}\n```") is None


def test_parse_plan_json_returns_none_on_garbage():
    assert _parse_plan_json("not json at all") is None


# ---------------------------------------------------------------------------
# _validate_plan_scope
# ---------------------------------------------------------------------------


def test_validate_plan_scope_within_targets(tmp_path):
    task_spec = _make_task_spec(output_targets=("src/counter.py", "tests/test_counter.py"))
    plan = {"files_to_touch": ["src/counter.py"]}
    assert _validate_plan_scope(plan=plan, task_spec=task_spec, workspace=tmp_path) == ""


def test_validate_plan_scope_out_of_targets(tmp_path):
    task_spec = _make_task_spec(output_targets=("src/counter.py",))
    plan = {"files_to_touch": ["src/counter.py", "README.md"]}
    msg = _validate_plan_scope(plan=plan, task_spec=task_spec, workspace=tmp_path)
    assert msg
    assert "README.md" in msg
    assert "output_targets" in msg


def test_validate_plan_scope_within_execution_root(tmp_path):
    task_spec = _make_task_spec(execution_root="src")
    plan = {"files_to_touch": ["src/counter.py", "src/utils.py"]}
    assert _validate_plan_scope(plan=plan, task_spec=task_spec, workspace=tmp_path) == ""


def test_validate_plan_scope_outside_execution_root(tmp_path):
    task_spec = _make_task_spec(execution_root="src")
    plan = {"files_to_touch": ["src/counter.py", "infra/deploy.sh"]}
    msg = _validate_plan_scope(plan=plan, task_spec=task_spec, workspace=tmp_path)
    assert msg
    assert "infra/deploy.sh" in msg


def test_validate_plan_scope_path_traversal(tmp_path):
    task_spec = _make_task_spec()
    plan = {"files_to_touch": ["../secrets/token.txt"]}
    msg = _validate_plan_scope(plan=plan, task_spec=task_spec, workspace=tmp_path)
    assert msg
    assert "traversal" in msg.lower() or ".." in msg


def test_validate_plan_scope_empty_files_is_ok(tmp_path):
    task_spec = _make_task_spec(output_targets=("src/counter.py",))
    plan = {"files_to_touch": []}
    assert _validate_plan_scope(plan=plan, task_spec=task_spec, workspace=tmp_path) == ""


def test_validate_plan_scope_non_list_files(tmp_path):
    task_spec = _make_task_spec()
    plan = {"files_to_touch": "src/counter.py"}  # string, not list
    msg = _validate_plan_scope(plan=plan, task_spec=task_spec, workspace=tmp_path)
    assert msg
    assert "list" in msg.lower()


def test_validate_plan_scope_dot_prefix_normalized(tmp_path):
    task_spec = _make_task_spec(output_targets=("src/counter.py",))
    plan = {"files_to_touch": ["./src/counter.py"]}
    assert _validate_plan_scope(plan=plan, task_spec=task_spec, workspace=tmp_path) == ""


# ---------------------------------------------------------------------------
# HealerPlanner.run_plan — happy path
# ---------------------------------------------------------------------------


def test_run_plan_passes_valid_plan(tmp_path):
    task_spec = _make_task_spec(output_targets=("src/counter.py",))
    connector = _StubConnector(output=_plan_json(files_to_touch=["src/counter.py"]))
    planner = HealerPlanner(connector=connector, timeout_seconds=30)

    result = planner.run_plan(
        issue_id="42",
        issue_title="Off-by-one error",
        issue_body="Counter is wrong.",
        task_spec=task_spec,
        workspace=tmp_path,
    )

    assert result.passed
    assert result.failure_class == ""
    assert result.plan["files_to_touch"] == ["src/counter.py"]
    assert len(connector.threads) == 1
    assert "planner:42" in connector.threads[0]


def test_run_plan_fails_on_scope_violation(tmp_path):
    task_spec = _make_task_spec(output_targets=("src/counter.py",))
    connector = _StubConnector(
        output=_plan_json(files_to_touch=["src/counter.py", "pyproject.toml"])
    )
    planner = HealerPlanner(connector=connector, strict_scope=True)

    result = planner.run_plan(
        issue_id="43",
        issue_title="Test",
        issue_body="Body",
        task_spec=task_spec,
        workspace=tmp_path,
    )

    assert not result.passed
    assert result.failure_class == "plan_scope_violation"
    assert "pyproject.toml" in result.failure_reason


def test_run_plan_fails_on_unparseable_output(tmp_path):
    task_spec = _make_task_spec()
    connector = _StubConnector(output="I cannot produce a plan right now.")
    planner = HealerPlanner(connector=connector)

    result = planner.run_plan(
        issue_id="44",
        issue_title="Test",
        issue_body="Body",
        task_spec=task_spec,
        workspace=tmp_path,
    )

    assert not result.passed
    assert result.failure_class == "plan_unparseable"


def test_run_plan_connector_unavailable_returns_failure(tmp_path):
    task_spec = _make_task_spec()
    connector = _StubConnector(output="ConnectorUnavailable: codex not found")
    planner = HealerPlanner(connector=connector)

    result = planner.run_plan(
        issue_id="45",
        issue_title="Test",
        issue_body="Body",
        task_spec=task_spec,
        workspace=tmp_path,
    )

    assert not result.passed
    assert result.failure_class == "connector_unavailable"


def test_run_plan_strict_scope_false_skips_scope_check(tmp_path):
    task_spec = _make_task_spec(output_targets=("src/counter.py",))
    connector = _StubConnector(
        output=_plan_json(files_to_touch=["src/counter.py", "Makefile"])
    )
    planner = HealerPlanner(connector=connector, strict_scope=False)

    result = planner.run_plan(
        issue_id="46",
        issue_title="Test",
        issue_body="Body",
        task_spec=task_spec,
        workspace=tmp_path,
    )

    # With strict_scope=False the scope violation is not checked
    assert result.passed


# ---------------------------------------------------------------------------
# _build_planning_prompt — content checks
# ---------------------------------------------------------------------------


def test_build_planning_prompt_includes_targets():
    task_spec = _make_task_spec(
        output_targets=("src/a.py", "tests/test_a.py"),
        execution_root="src",
        validation_commands=("pytest tests/",),
    )
    prompt = _build_planning_prompt(
        issue_title="Fix bug",
        issue_body="The function returns None.",
        task_spec=task_spec,
    )
    assert "src/a.py" in prompt
    assert "tests/test_a.py" in prompt
    assert "execution root" in prompt.lower()
    assert "pytest tests/" in prompt
    assert "files_to_touch" in prompt


def test_build_planning_prompt_includes_feedback():
    task_spec = _make_task_spec()
    prompt = _build_planning_prompt(
        issue_title="Fix",
        issue_body="Body",
        task_spec=task_spec,
        feedback_context="Last run: tests failed on line 42.",
    )
    assert "Last run: tests failed on line 42." in prompt


def test_build_planning_prompt_excludes_context_paths():
    task_spec = _make_task_spec(input_context_paths=("docs/spec.md",))
    prompt = _build_planning_prompt(
        issue_title="Fix",
        issue_body="Body",
        task_spec=task_spec,
    )
    assert "docs/spec.md" in prompt
    assert "read-only" in prompt.lower() or "do not touch" in prompt.lower()
