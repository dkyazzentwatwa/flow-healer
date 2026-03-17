from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .healer_task_spec import HealerTaskSpec
from .protocols import ConnectorProtocol

logger = logging.getLogger("apple_flow.healer_planner")

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON_RE = re.compile(r"(\{[^{}]*\"files_to_touch\"[^{}]*\})", re.DOTALL)

_PLAN_SYSTEM_PREAMBLE = """\
You are the planning phase of an automated repair harness.
Your job is to analyse the issue and produce a JSON plan ONLY.
Do not edit any files. Do not output code patches.
Output exactly one JSON object wrapped in a ```json ... ``` block.
"""

_PLAN_SCHEMA_DESCRIPTION = """\
Required JSON schema:
{
  "approach": "<one sentence: what change fixes this issue>",
  "files_to_touch": ["<repo-relative path>", ...],
  "validation_commands": ["<command to verify the fix>", ...],
  "scope_summary": "<one sentence: what is in and out of scope>"
}
All paths must be relative to the repo root (no leading slash or ../).
"""


@dataclass(slots=True, frozen=True)
class PlanResult:
    passed: bool
    plan: dict[str, Any]
    failure_class: str
    failure_reason: str
    raw_output: str


class HealerPlanner:
    """Elicits a structured plan from the provider and validates it against the task spec
    before any code edits are allowed.

    The plan gate catches scope violations, ambiguous targets, and infra
    issues before a full run_attempt burns its timeout budget.
    """

    def __init__(
        self,
        connector: ConnectorProtocol,
        *,
        timeout_seconds: int = 120,
        strict_scope: bool = True,
    ) -> None:
        self.connector = connector
        self.timeout_seconds = max(30, int(timeout_seconds))
        self.strict_scope = bool(strict_scope)

    def run_plan(
        self,
        *,
        issue_id: str,
        issue_title: str,
        issue_body: str,
        task_spec: HealerTaskSpec,
        workspace: Path,
        feedback_context: str = "",
    ) -> PlanResult:
        """Produce and validate a plan.  Returns PlanResult.passed=True only if
        the plan is well-formed and respects the declared task spec scope."""
        prompt = _build_planning_prompt(
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            feedback_context=feedback_context,
        )
        thread_id = self.connector.get_or_create_thread(f"planner:{issue_id}")
        try:
            raw = self.connector.run_turn(
                thread_id, prompt, timeout_seconds=self.timeout_seconds
            )
        except Exception as exc:
            return PlanResult(
                passed=False,
                plan={},
                failure_class="connector_unavailable",
                failure_reason=f"Planner connector error: {exc}",
                raw_output="",
            )

        if str(raw or "").startswith(("ConnectorUnavailable:", "ConnectorRuntimeError:")):
            return PlanResult(
                passed=False,
                plan={},
                failure_class="connector_unavailable",
                failure_reason=(raw or "")[:500],
                raw_output=raw or "",
            )

        plan = _parse_plan_json(raw)
        if plan is None:
            logger.warning(
                "Planner for issue #%s returned unparseable output (len=%d).",
                issue_id,
                len(raw or ""),
            )
            return PlanResult(
                passed=False,
                plan={},
                failure_class="plan_unparseable",
                failure_reason=(
                    "Planner output did not contain a valid JSON plan block. "
                    "The provider must emit exactly one ```json {...}``` block with "
                    "files_to_touch, approach, validation_commands, and scope_summary."
                ),
                raw_output=raw or "",
            )

        if self.strict_scope:
            violation = _validate_plan_scope(
                plan=plan, task_spec=task_spec, workspace=workspace
            )
            if violation:
                return PlanResult(
                    passed=False,
                    plan=plan,
                    failure_class="plan_scope_violation",
                    failure_reason=violation,
                    raw_output=raw or "",
                )

        return PlanResult(
            passed=True,
            plan=plan,
            failure_class="",
            failure_reason="",
            raw_output=raw or "",
        )


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_planning_prompt(
    *,
    issue_title: str,
    issue_body: str,
    task_spec: HealerTaskSpec,
    feedback_context: str = "",
) -> str:
    parts: list[str] = [_PLAN_SYSTEM_PREAMBLE, ""]

    parts.append(f"## Issue\n**Title:** {issue_title}\n")
    if issue_body.strip():
        trimmed_body = issue_body.strip()[:3000]
        parts.append(f"**Body:**\n{trimmed_body}\n")

    if task_spec.output_targets:
        targets = "\n".join(f"- {t}" for t in task_spec.output_targets)
        parts.append(f"## Declared output targets (you MUST stay within these)\n{targets}\n")

    if task_spec.execution_root:
        parts.append(f"## Execution root\n`{task_spec.execution_root}`\n")

    if task_spec.validation_commands:
        cmds = "\n".join(f"- `{c}`" for c in task_spec.validation_commands)
        parts.append(f"## Declared validation commands\n{cmds}\n")

    if task_spec.input_context_paths:
        ctx = "\n".join(f"- {p}" for p in task_spec.input_context_paths)
        parts.append(f"## Input context (read-only, do not touch)\n{ctx}\n")

    if feedback_context.strip():
        trimmed_fb = feedback_context.strip()[:1000]
        parts.append(f"## Prior attempt feedback\n{trimmed_fb}\n")

    parts.append(_PLAN_SCHEMA_DESCRIPTION)
    parts.append(
        "Now emit the JSON plan block. Nothing else.\n"
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------


def _parse_plan_json(raw: str) -> dict[str, Any] | None:
    """Extract the first valid plan JSON object from raw connector output."""
    text = str(raw or "").strip()
    if not text:
        return None

    # Try fenced JSON block first
    m = _JSON_BLOCK_RE.search(text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and "files_to_touch" in obj:
                return obj
        except (json.JSONDecodeError, ValueError):
            pass

    # Try bare JSON object containing the expected key
    m2 = _BARE_JSON_RE.search(text)
    if m2:
        try:
            obj = json.loads(m2.group(1))
            if isinstance(obj, dict) and "files_to_touch" in obj:
                return obj
        except (json.JSONDecodeError, ValueError):
            pass

    return None


# ---------------------------------------------------------------------------
# Scope validation
# ---------------------------------------------------------------------------


def _normalize_plan_path(raw: str) -> str:
    p = str(raw or "").strip().strip("/")
    # Remove leading ./
    while p.startswith("./"):
        p = p[2:]
    try:
        return PurePosixPath(p).as_posix()
    except Exception:
        return p


def _validate_plan_scope(
    *,
    plan: dict[str, Any],
    task_spec: HealerTaskSpec,
    workspace: Path,
) -> str:
    """Return a non-empty violation message if the plan violates task spec scope,
    or empty string if the plan is within scope."""
    files_raw = plan.get("files_to_touch")
    if not isinstance(files_raw, list):
        return "Plan field 'files_to_touch' must be a list."

    planned: list[str] = [
        _normalize_plan_path(f) for f in files_raw if str(f or "").strip()
    ]
    if not planned:
        # Empty plan is not a scope violation; runner will catch empty diffs.
        return ""

    # Check each planned path against declared output_targets (if set)
    declared_targets = {
        _normalize_plan_path(t) for t in (task_spec.output_targets or ())
    }
    if declared_targets:
        out_of_scope = [p for p in planned if p not in declared_targets]
        if out_of_scope:
            listed = ", ".join(f"`{p}`" for p in out_of_scope[:5])
            return (
                f"Plan references file(s) outside declared output_targets: {listed}. "
                f"Declared targets: {', '.join(sorted(declared_targets))}."
            )

    # Check each planned path stays within execution_root (if set)
    exec_root = _normalize_plan_path(str(task_spec.execution_root or "").strip())
    if exec_root and exec_root != ".":
        outside_root = [
            p
            for p in planned
            if not (p == exec_root or p.startswith(f"{exec_root}/"))
        ]
        if outside_root and not declared_targets:
            # Only enforce root boundary when output_targets didn't already constrain
            listed = ", ".join(f"`{p}`" for p in outside_root[:5])
            return (
                f"Plan references file(s) outside execution_root `{exec_root}`: {listed}."
            )

    # Check no path escapes the workspace
    for p in planned:
        if ".." in p.split("/"):
            return f"Plan contains path traversal in `{p}`."

    return ""
