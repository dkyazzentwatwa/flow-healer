from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol
from uuid import uuid4

from .healer_runner import HealerRunResult, HealerRunner, _build_proposer_prompt
from .healer_task_spec import HealerTaskSpec, task_spec_to_prompt_block
from .protocols import ConnectorProtocol


@dataclass(slots=True, frozen=True)
class SubagentRequest:
    role: str
    prompt: str
    timeout_seconds: int
    expect_json: bool = True


@dataclass(slots=True, frozen=True)
class SubagentResult:
    role: str
    raw: str
    parsed: dict[str, Any]
    success: bool
    error: str = ""


@dataclass(slots=True, frozen=True)
class SwarmRecoveryPlan:
    strategy: str
    summary: str
    root_cause: str
    edit_scope: tuple[str, ...]
    targeted_tests: tuple[str, ...]
    validation_focus: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class SwarmRecoveryOutcome:
    recovered: bool
    strategy: str
    summary: str
    analyzer_results: tuple[SubagentResult, ...]
    plan: SwarmRecoveryPlan
    repair_output: str = ""
    failure_class: str = ""
    failure_reason: str = ""
    run_result: HealerRunResult | None = None

    def as_summary(self) -> dict[str, Any]:
        return {
            "recovered": self.recovered,
            "strategy": self.strategy,
            "summary": self.summary,
            "failure_class": self.failure_class,
            "failure_reason": self.failure_reason,
            "roles": [
                {
                    "role": result.role,
                    "success": result.success,
                    "error": result.error,
                    "parsed": result.parsed,
                }
                for result in self.analyzer_results
            ],
            "plan": {
                "strategy": self.plan.strategy,
                "summary": self.plan.summary,
                "root_cause": self.plan.root_cause,
                "edit_scope": list(self.plan.edit_scope),
                "targeted_tests": list(self.plan.targeted_tests),
                "validation_focus": list(self.plan.validation_focus),
            },
        }


class SubagentBackendAdapter(Protocol):
    def run(self, request: SubagentRequest, *, issue_id: str) -> SubagentResult: ...

    def run_parallel(
        self,
        requests: list[SubagentRequest],
        *,
        issue_id: str,
        max_parallel: int,
        on_result: Callable[[SubagentResult], None] | None = None,
    ) -> list[SubagentResult]: ...


class ConnectorSubagentBackend:
    def __init__(
        self,
        connector: ConnectorProtocol,
        *,
        connector_factory: Callable[[], ConnectorProtocol] | None = None,
    ) -> None:
        self.connector = connector
        self.connector_factory = connector_factory

    def run(self, request: SubagentRequest, *, issue_id: str) -> SubagentResult:
        connector = self.connector_factory() if self.connector_factory is not None else self.connector
        sender = f"healer-swarm:{issue_id}:{request.role}:{uuid4().hex[:8]}"
        raw = ""
        try:
            thread_id = connector.reset_thread(sender)
            raw = connector.run_turn(thread_id, request.prompt, timeout_seconds=request.timeout_seconds)
            parsed = _parse_json_object(raw) if request.expect_json else {}
            return SubagentResult(
                role=request.role,
                raw=(raw or "").strip(),
                parsed=parsed,
                success=not request.expect_json or bool(parsed),
            )
        except Exception as exc:
            return SubagentResult(
                role=request.role,
                raw=(raw or "").strip(),
                parsed={},
                success=False,
                error=str(exc),
            )
        finally:
            if connector is not self.connector and hasattr(connector, "shutdown"):
                try:
                    connector.shutdown()
                except Exception:
                    pass

    def run_parallel(
        self,
        requests: list[SubagentRequest],
        *,
        issue_id: str,
        max_parallel: int,
        on_result: Callable[[SubagentResult], None] | None = None,
    ) -> list[SubagentResult]:
        if not requests:
            return []
        if self.connector_factory is None or max_parallel <= 1 or len(requests) == 1:
            results: list[SubagentResult] = []
            for request in requests:
                result = self.run(request, issue_id=issue_id)
                if on_result is not None:
                    on_result(result)
                results.append(result)
            return results
        results: list[SubagentResult] = []
        with ThreadPoolExecutor(max_workers=min(max_parallel, len(requests))) as executor:
            futures = {
                executor.submit(self.run, request, issue_id=issue_id): request.role
                for request in requests
            }
            for future in as_completed(futures):
                result = future.result()
                if on_result is not None:
                    on_result(result)
                results.append(result)
        results.sort(key=lambda item: item.role)
        return results


def build_connector_subagent_backend(connector: ConnectorProtocol) -> ConnectorSubagentBackend:
    return ConnectorSubagentBackend(
        connector=connector,
        connector_factory=_connector_clone_factory(connector),
    )


class HealerSwarm:
    def __init__(
        self,
        backend: SubagentBackendAdapter,
        *,
        max_parallel_agents: int = 4,
        max_repair_cycles_per_attempt: int = 1,
    ) -> None:
        self.backend = backend
        self.max_parallel_agents = max(1, int(max_parallel_agents))
        self.max_repair_cycles_per_attempt = max(1, int(max_repair_cycles_per_attempt))

    def recover(
        self,
        *,
        issue_id: str,
        issue_title: str,
        issue_body: str,
        task_spec: HealerTaskSpec,
        learned_context: str,
        feedback_context: str,
        failure_class: str,
        failure_reason: str,
        proposer_output: str,
        test_summary: dict[str, Any],
        verifier_summary: dict[str, Any],
        workspace_status: dict[str, Any],
        workspace: Path,
        runner: HealerRunner,
        max_diff_files: int,
        max_diff_lines: int,
        max_failed_tests_allowed: int,
        targeted_tests: list[str],
        telemetry_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> SwarmRecoveryOutcome:
        analyzer_requests = _build_analyzer_requests(
            issue_id=issue_id,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            learned_context=learned_context,
            feedback_context=feedback_context,
            failure_class=failure_class,
            failure_reason=failure_reason,
            proposer_output=proposer_output,
            test_summary=test_summary,
            verifier_summary=verifier_summary,
            workspace_status=workspace_status,
        )
        _emit_telemetry(
            telemetry_callback,
            "swarm_started",
            {
                "failure_class": failure_class,
                "failure_reason": failure_reason,
                "roles": [request.role for request in analyzer_requests],
                "max_parallel_agents": self.max_parallel_agents,
            },
        )
        analyzer_results = tuple(
            self.backend.run_parallel(
                analyzer_requests,
                issue_id=issue_id,
                max_parallel=self.max_parallel_agents,
                on_result=lambda result: _emit_telemetry(
                    telemetry_callback,
                    "swarm_role_completed",
                    _role_payload(result=result, stage="analysis"),
                ),
            )
        )
        plan, manager_result = self._build_recovery_plan(
            issue_id=issue_id,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            failure_class=failure_class,
            failure_reason=failure_reason,
            proposer_output=proposer_output,
            test_summary=test_summary,
            verifier_summary=verifier_summary,
            analyzer_results=analyzer_results,
        )
        _emit_telemetry(
            telemetry_callback,
            "swarm_role_completed",
            _role_payload(result=manager_result, stage="planning"),
        )
        _emit_telemetry(
            telemetry_callback,
            "swarm_plan_ready",
            {
                "strategy": plan.strategy,
                "summary": plan.summary,
                "root_cause": plan.root_cause,
                "edit_scope": list(plan.edit_scope),
                "targeted_tests": list(plan.targeted_tests),
                "validation_focus": list(plan.validation_focus),
            },
        )
        if plan.strategy != "repair":
            summary = plan.summary or "Swarm declined direct repair for this failure."
            outcome = SwarmRecoveryOutcome(
                recovered=False,
                strategy=plan.strategy,
                summary=summary,
                analyzer_results=analyzer_results,
                plan=plan,
                failure_class=failure_class,
                failure_reason=summary,
            )
            _emit_telemetry(telemetry_callback, "swarm_finished", _outcome_payload(outcome))
            return outcome

        repair_request = SubagentRequest(
            role="repair-executor",
            prompt=_build_repair_prompt(
                issue_id=issue_id,
                issue_title=issue_title,
                issue_body=issue_body,
                task_spec=task_spec,
                learned_context=learned_context,
                feedback_context=feedback_context,
                failure_class=failure_class,
                failure_reason=failure_reason,
                analyzer_results=analyzer_results,
                plan=plan,
                workspace=workspace,
            ),
            timeout_seconds=max(runner.code_change_turn_timeout_seconds, runner.timeout_seconds),
            expect_json=False,
        )
        repair_result = self.backend.run(repair_request, issue_id=issue_id)
        _emit_telemetry(
            telemetry_callback,
            "swarm_role_completed",
            _role_payload(result=repair_result, stage="repair"),
        )
        run_result = runner.evaluate_existing_workspace(
            workspace=workspace,
            issue_id=issue_id,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            targeted_tests=_merge_targeted_tests(targeted_tests, plan.targeted_tests),
            max_diff_files=max_diff_files,
            max_diff_lines=max_diff_lines,
            max_failed_tests_allowed=max_failed_tests_allowed,
            proposer_output=repair_result.raw,
            workspace_status=_merge_workspace_status(
                workspace_status=workspace_status,
                strategy=plan.strategy,
                summary=plan.summary,
            ),
        )
        summary = plan.summary or "Swarm repair executed."
        outcome = SwarmRecoveryOutcome(
            recovered=run_result.success,
            strategy=plan.strategy,
            summary=summary,
            analyzer_results=analyzer_results,
            plan=plan,
            repair_output=repair_result.raw,
            failure_class="" if run_result.success else run_result.failure_class,
            failure_reason="" if run_result.success else run_result.failure_reason,
            run_result=run_result,
        )
        _emit_telemetry(telemetry_callback, "swarm_finished", _outcome_payload(outcome))
        return outcome

    def _build_recovery_plan(
        self,
        *,
        issue_id: str,
        issue_title: str,
        issue_body: str,
        task_spec: HealerTaskSpec,
        failure_class: str,
        failure_reason: str,
        proposer_output: str,
        test_summary: dict[str, Any],
        verifier_summary: dict[str, Any],
        analyzer_results: tuple[SubagentResult, ...],
    ) -> tuple[SwarmRecoveryPlan, SubagentResult]:
        prompt = _build_manager_prompt(
            issue_id=issue_id,
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            failure_class=failure_class,
            failure_reason=failure_reason,
            proposer_output=proposer_output,
            test_summary=test_summary,
            verifier_summary=verifier_summary,
            analyzer_results=analyzer_results,
        )
        result = self.backend.run(
            SubagentRequest(
                role="recovery-manager",
                prompt=prompt,
                timeout_seconds=180,
                expect_json=True,
            ),
            issue_id=issue_id,
        )
        if result.success and result.parsed:
            return _coerce_recovery_plan(result.parsed), result
        return _fallback_recovery_plan(analyzer_results), result


def _emit_telemetry(
    callback: Callable[[str, dict[str, Any]], None] | None,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    if callback is None:
        return
    callback(event_type, payload)


def _role_payload(*, result: SubagentResult, stage: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "stage": stage,
        "role": result.role,
        "success": result.success,
        "error": result.error,
    }
    summary = _result_summary(result)
    if summary:
        payload["summary"] = summary
    if result.parsed:
        payload["parsed_keys"] = sorted(str(key) for key in result.parsed.keys())
    raw_excerpt = (result.raw or "").strip()
    if raw_excerpt:
        payload["raw_excerpt"] = raw_excerpt[:240]
    return payload


def _result_summary(result: SubagentResult) -> str:
    if result.error:
        return result.error[:240]
    if not result.parsed:
        return ""
    for key in ("summary", "reason", "root_cause", "missed_root_cause"):
        value = str(result.parsed.get(key) or "").strip()
        if value:
            return value[:240]
    return ""


def _outcome_payload(outcome: SwarmRecoveryOutcome) -> dict[str, Any]:
    return {
        "recovered": outcome.recovered,
        "strategy": outcome.strategy,
        "summary": outcome.summary,
        "failure_class": outcome.failure_class,
        "failure_reason": outcome.failure_reason,
    }


def _connector_clone_factory(connector: ConnectorProtocol) -> Callable[[], ConnectorProtocol] | None:
    cls = connector.__class__
    required = ("workspace", "codex_command", "timeout", "model", "reasoning_effort")
    if not all(hasattr(connector, name) for name in required):
        return None

    def _factory() -> ConnectorProtocol:
        return cls(
            workspace=str(getattr(connector, "workspace")),
            codex_command=str(getattr(connector, "codex_command")),
            timeout=float(getattr(connector, "timeout")),
            model=str(getattr(connector, "model")),
            reasoning_effort=str(getattr(connector, "reasoning_effort")),
        )

    return _factory


def _build_analyzer_requests(
    *,
    issue_id: str,
    issue_title: str,
    issue_body: str,
    task_spec: HealerTaskSpec,
    learned_context: str,
    feedback_context: str,
    failure_class: str,
    failure_reason: str,
    proposer_output: str,
    test_summary: dict[str, Any],
    verifier_summary: dict[str, Any],
    workspace_status: dict[str, Any],
) -> list[SubagentRequest]:
    context = _shared_failure_context(
        issue_id=issue_id,
        issue_title=issue_title,
        issue_body=issue_body,
        task_spec=task_spec,
        learned_context=learned_context,
        feedback_context=feedback_context,
        failure_class=failure_class,
        failure_reason=failure_reason,
        proposer_output=proposer_output,
        test_summary=test_summary,
        verifier_summary=verifier_summary,
        workspace_status=workspace_status,
    )
    role_instructions = {
        "failure-triager": (
            "You classify autonomous repair failures. Return strict JSON with keys "
            "`root_cause`, `repair_lane`, `confidence`, `likely_paths`, and `reason`."
        ),
        "test-forensics": (
            "You inspect failing tests and runtime evidence. Return strict JSON with keys "
            "`failing_surfaces`, `targeted_tests`, `likely_paths`, and `reason`."
        ),
        "patch-critic": (
            "You critique why the previous attempt failed or missed. Return strict JSON with keys "
            "`missed_root_cause`, `anti_patterns`, `likely_paths`, and `reason`."
        ),
        "scope-guard": (
            "You enforce issue scope and workspace safety. Return strict JSON with keys "
            "`allow_repair`, `edit_scope`, `should_quarantine`, and `reason`."
        ),
    }
    return [
        SubagentRequest(
            role=role,
            prompt=(
                f"You are the `{role}` subagent for Flow Healer.\n"
                "Use the repo and failure context below. Do not edit files. Return strict JSON only.\n\n"
                f"{instructions}\n\n"
                f"{context}"
            ),
            timeout_seconds=180,
            expect_json=True,
        )
        for role, instructions in role_instructions.items()
    ]


def _shared_failure_context(
    *,
    issue_id: str,
    issue_title: str,
    issue_body: str,
    task_spec: HealerTaskSpec,
    learned_context: str,
    feedback_context: str,
    failure_class: str,
    failure_reason: str,
    proposer_output: str,
    test_summary: dict[str, Any],
    verifier_summary: dict[str, Any],
    workspace_status: dict[str, Any],
) -> str:
    parts = [
        (learned_context or "").strip(),
        f"Issue #{issue_id}: {issue_title}\n\n{issue_body}",
        task_spec_to_prompt_block(task_spec),
        "Failure digest:\n"
        + json.dumps(
            {
                "failure_class": failure_class,
                "failure_reason": failure_reason,
                "test_summary": test_summary,
                "verifier_summary": verifier_summary,
                "workspace_status": workspace_status,
            },
            ensure_ascii=True,
        ),
        f"Feedback context:\n{feedback_context.strip()}" if feedback_context.strip() else "",
        f"Previous proposer output (truncated):\n{proposer_output[:6000]}",
    ]
    return "\n\n".join(part for part in parts if part)


def _build_manager_prompt(
    *,
    issue_id: str,
    issue_title: str,
    issue_body: str,
    task_spec: HealerTaskSpec,
    failure_class: str,
    failure_reason: str,
    proposer_output: str,
    test_summary: dict[str, Any],
    verifier_summary: dict[str, Any],
    analyzer_results: tuple[SubagentResult, ...],
) -> str:
    rendered_results = json.dumps(
        [
            {
                "role": result.role,
                "success": result.success,
                "error": result.error,
                "parsed": result.parsed,
            }
            for result in analyzer_results
        ],
        ensure_ascii=True,
    )
    return (
        "You are the `recovery-manager` for Flow Healer.\n"
        "Choose the safest next action for an autonomous repair attempt.\n"
        "Return strict JSON only with keys "
        "`strategy`, `summary`, `root_cause`, `edit_scope`, `targeted_tests`, and `validation_focus`.\n"
        "Valid strategies are `repair`, `retry_prompt_only`, `quarantine`, and `infra_pause`.\n\n"
        f"Issue #{issue_id}: {issue_title}\n\n"
        f"{issue_body}\n\n"
        f"{task_spec_to_prompt_block(task_spec)}\n\n"
        f"Failure class: {failure_class}\n"
        f"Failure reason: {failure_reason}\n\n"
        f"Test summary: {json.dumps(test_summary, ensure_ascii=True)}\n"
        f"Verifier summary: {json.dumps(verifier_summary, ensure_ascii=True)}\n\n"
        f"Previous proposer output (truncated):\n{proposer_output[:6000]}\n\n"
        f"Analyzer results:\n{rendered_results}"
    )


def _build_repair_prompt(
    *,
    issue_id: str,
    issue_title: str,
    issue_body: str,
    task_spec: HealerTaskSpec,
    learned_context: str,
    feedback_context: str,
    failure_class: str,
    failure_reason: str,
    analyzer_results: tuple[SubagentResult, ...],
    plan: SwarmRecoveryPlan,
    workspace: Path,
) -> str:
    base_prompt = _build_proposer_prompt(
        issue_id=issue_id,
        issue_title=issue_title,
        issue_body=issue_body,
        task_spec=task_spec,
        workspace=workspace,
        learned_context=learned_context,
        feedback_context=feedback_context,
        language_hint="",
        prefer_workspace_edits=True,
    )
    findings = json.dumps(
        [
            {"role": result.role, "parsed": result.parsed, "error": result.error}
            for result in analyzer_results
        ],
        ensure_ascii=True,
    )
    return (
        f"{base_prompt}\n\n"
        "### Swarm Failure Recovery\n"
        f"- Failure class: {failure_class}\n"
        f"- Failure reason: {failure_reason}\n"
        f"- Swarm summary: {plan.summary}\n"
        f"- Root cause: {plan.root_cause}\n"
        f"- Edit scope: {', '.join(plan.edit_scope) if plan.edit_scope else '(minimal safe scope)'}\n"
        f"- Targeted tests: {', '.join(plan.targeted_tests) if plan.targeted_tests else '(issue-scoped validation only)'}\n"
        f"- Validation focus: {', '.join(plan.validation_focus) if plan.validation_focus else '(respect task validation contract)'}\n\n"
        "### Swarm Findings\n"
        f"{findings}\n\n"
        "Edit files directly in the managed workspace now.\n"
        "Stay within the issue-scoped execution root, named output targets, and adjacent existing source/test/config files required for a safe fix.\n"
        "Do not widen scope, rebuild unrelated scaffolding, or return a plan.\n"
        "Run the issue-scoped validation after editing and end with a concise summary of the concrete changes."
    )


def _coerce_recovery_plan(data: dict[str, Any]) -> SwarmRecoveryPlan:
    strategy = str(data.get("strategy") or "repair").strip().lower() or "repair"
    if strategy not in {"repair", "retry_prompt_only", "quarantine", "infra_pause"}:
        strategy = "repair"
    return SwarmRecoveryPlan(
        strategy=strategy,
        summary=str(data.get("summary") or "").strip() or "Swarm recovery plan generated.",
        root_cause=str(data.get("root_cause") or "").strip(),
        edit_scope=tuple(_coerce_str_list(data.get("edit_scope"))),
        targeted_tests=tuple(_coerce_str_list(data.get("targeted_tests"))),
        validation_focus=tuple(_coerce_str_list(data.get("validation_focus"))),
    )


def _fallback_recovery_plan(analyzer_results: tuple[SubagentResult, ...]) -> SwarmRecoveryPlan:
    strategy = "repair"
    edit_scope: list[str] = []
    targeted_tests: list[str] = []
    validation_focus: list[str] = []
    root_cause_parts: list[str] = []
    for result in analyzer_results:
        parsed = result.parsed
        if result.role == "scope-guard":
            if parsed.get("should_quarantine") or parsed.get("allow_repair") is False:
                strategy = "quarantine"
            edit_scope.extend(_coerce_str_list(parsed.get("edit_scope")))
        else:
            edit_scope.extend(_coerce_str_list(parsed.get("likely_paths")))
        targeted_tests.extend(_coerce_str_list(parsed.get("targeted_tests")))
        validation_focus.extend(_coerce_str_list(parsed.get("failing_surfaces")))
        reason = str(parsed.get("reason") or parsed.get("missed_root_cause") or "").strip()
        if reason:
            root_cause_parts.append(reason)
    summary = (
        "Swarm synthesized a conservative repair plan."
        if strategy == "repair"
        else "Swarm found scope or safety evidence that argues against direct repair."
    )
    return SwarmRecoveryPlan(
        strategy=strategy,
        summary=summary,
        root_cause=" ".join(root_cause_parts[:2]).strip(),
        edit_scope=tuple(_unique_preserve_order(edit_scope)),
        targeted_tests=tuple(_unique_preserve_order(targeted_tests)),
        validation_focus=tuple(_unique_preserve_order(validation_focus)),
    )


def _merge_workspace_status(
    *,
    workspace_status: dict[str, Any],
    strategy: str,
    summary: str,
) -> dict[str, Any]:
    merged = dict(workspace_status or {})
    merged["swarm_strategy"] = strategy
    merged["swarm_summary"] = summary
    return merged


def _merge_targeted_tests(existing: list[str], additional: tuple[str, ...]) -> list[str]:
    return _unique_preserve_order([*existing, *additional])


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    if not stripped:
        return {}
    cleaned = _strip_fence(stripped)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = json.loads(_extract_first_json_object(cleaned))
    return parsed if isinstance(parsed, dict) else {}


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    if lines and lines[0].strip().lower() == "json":
        lines = lines[1:]
    return "\n".join(lines).strip()


def _extract_first_json_object(text: str) -> str:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return text[index:index + end]
    return "{}"


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        unique.append(cleaned)
    return unique
