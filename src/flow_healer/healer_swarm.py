from __future__ import annotations

import json
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol
from uuid import uuid4

from .healer_runner import HealerRunResult, HealerRunner, _build_proposer_prompt
from .healer_task_spec import HealerTaskSpec, task_spec_to_prompt_block
from .protocols import ConnectorProtocol
from .swarm_markers import SWARM_PROCESS_MARKER


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
        overall_timeout_seconds: float | None = None,
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
        overall_timeout_seconds: float | None = None,
    ) -> list[SubagentResult]:
        if not requests:
            return []
        deadline = _deadline(overall_timeout_seconds)
        results_by_role: dict[str, SubagentResult] = {}

        def _record(result: SubagentResult) -> None:
            existing = results_by_role.get(result.role)
            if existing is None:
                results_by_role[result.role] = result
            elif _is_timeout_result(result) and not _is_timeout_result(existing):
                results_by_role[result.role] = result
            if on_result is not None:
                on_result(result)

        if self.connector_factory is None or max_parallel <= 1 or len(requests) == 1:
            for request in requests:
                if _deadline_expired(deadline):
                    _record(
                        _timed_out_result(
                            role=request.role,
                            timeout_seconds=overall_timeout_seconds,
                        )
                    )
                    continue
                _record(self.run(request, issue_id=issue_id))
            return sorted(results_by_role.values(), key=lambda item: item.role)
        executor = ThreadPoolExecutor(max_workers=min(max_parallel, len(requests)))
        futures: dict[Future[SubagentResult], str] = {
            executor.submit(self.run, request, issue_id=issue_id): request.role
            for request in requests
        }
        pending: set[Future[SubagentResult]] = set(futures.keys())
        try:
            while pending:
                remaining = _deadline_remaining(deadline)
                if remaining == 0.0:
                    break
                done, pending = wait(
                    pending,
                    timeout=remaining,
                    return_when=FIRST_COMPLETED,
                )
                if not done:
                    break
                for future in done:
                    role = futures.get(future, "")
                    try:
                        _record(future.result())
                    except Exception as exc:
                        _record(
                            SubagentResult(
                                role=role,
                                raw="",
                                parsed={},
                                success=False,
                                error=str(exc),
                            )
                        )
            if pending:
                for future in pending:
                    role = futures.get(future, "")
                    _record(
                        _timed_out_result(
                            role=role,
                            timeout_seconds=overall_timeout_seconds,
                        )
                    )
                    future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                pending.clear()
            else:
                executor.shutdown(wait=True, cancel_futures=False)
        finally:
            if pending:
                for future in pending:
                    future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
        for request in requests:
            if request.role in results_by_role:
                continue
            _record(
                _timed_out_result(
                    role=request.role,
                    timeout_seconds=overall_timeout_seconds,
                )
            )
        return sorted(results_by_role.values(), key=lambda item: item.role)


def _deadline(overall_timeout_seconds: float | None) -> float | None:
    if overall_timeout_seconds is None:
        return None
    timeout = float(overall_timeout_seconds)
    if timeout <= 0:
        return time.monotonic()
    return time.monotonic() + timeout


def _deadline_remaining(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return 0.0
    return remaining


def _deadline_expired(deadline: float | None) -> bool:
    if deadline is None:
        return False
    return _deadline_remaining(deadline) == 0.0


def _min_timeout(primary: float | None, secondary: float | None) -> float | None:
    if primary is None:
        return secondary
    if secondary is None:
        return primary
    return min(primary, secondary)


def _timed_out_result(*, role: str, timeout_seconds: float | None) -> SubagentResult:
    timeout = int(max(1, round(float(timeout_seconds or 1.0))))
    return SubagentResult(
        role=role,
        raw="",
        parsed={},
        success=False,
        error=f"Timed out waiting for subagent result after {timeout}s.",
    )


def _is_timeout_result(result: SubagentResult) -> bool:
    return "timed out" in str(result.error or "").strip().lower()


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
        analysis_timeout_seconds: int = 240,
        recovery_timeout_seconds: int = 420,
    ) -> None:
        self.backend = backend
        self.max_parallel_agents = max(1, int(max_parallel_agents))
        self.max_repair_cycles_per_attempt = max(1, int(max_repair_cycles_per_attempt))
        self.analysis_timeout_seconds = max(30, int(analysis_timeout_seconds))
        self.recovery_timeout_seconds = max(60, int(recovery_timeout_seconds))

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
        recovery_deadline = _deadline(float(self.recovery_timeout_seconds))
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
                "analysis_timeout_seconds": self.analysis_timeout_seconds,
                "recovery_timeout_seconds": self.recovery_timeout_seconds,
            },
        )

        def _timeout_outcome(*, stage: str, reason: str = "", analyzer_results: tuple[SubagentResult, ...] = ()) -> SwarmRecoveryOutcome:
            timeout_reason = reason.strip() or f"Swarm recovery timed out during {stage}."
            fallback_plan = _fallback_recovery_plan(analyzer_results)
            quarantine_plan = SwarmRecoveryPlan(
                strategy="quarantine",
                summary=timeout_reason,
                root_cause=fallback_plan.root_cause,
                edit_scope=fallback_plan.edit_scope,
                targeted_tests=fallback_plan.targeted_tests,
                validation_focus=fallback_plan.validation_focus,
            )
            outcome = SwarmRecoveryOutcome(
                recovered=False,
                strategy="quarantine",
                summary=timeout_reason,
                analyzer_results=analyzer_results,
                plan=quarantine_plan,
                failure_class="swarm_timeout",
                failure_reason=timeout_reason,
            )
            _emit_telemetry(
                telemetry_callback,
                "swarm_recovery_timeout",
                {
                    "stage": stage,
                    "summary": timeout_reason,
                    "recovery_timeout_seconds": self.recovery_timeout_seconds,
                },
            )
            _emit_telemetry(telemetry_callback, "swarm_finished", _outcome_payload(outcome))
            return outcome

        analysis_timeout = _min_timeout(
            float(self.analysis_timeout_seconds),
            _deadline_remaining(recovery_deadline),
        )
        if analysis_timeout is not None and analysis_timeout <= 0:
            return _timeout_outcome(stage="analysis", reason="Swarm recovery timed out before analyzer fanout started.")

        def _analysis_on_result(result: SubagentResult) -> None:
            _emit_telemetry(
                telemetry_callback,
                "swarm_role_completed",
                _role_payload(result=result, stage="analysis"),
            )
            if _is_timeout_result(result):
                _emit_telemetry(
                    telemetry_callback,
                    "swarm_role_timeout",
                    {
                        "stage": "analysis",
                        "role": result.role,
                        "error": result.error,
                    },
                )

        analyzer_results = tuple(
            self.backend.run_parallel(
                analyzer_requests,
                issue_id=issue_id,
                max_parallel=self.max_parallel_agents,
                on_result=_analysis_on_result,
                overall_timeout_seconds=analysis_timeout,
            )
        )
        if any(_is_timeout_result(result) for result in analyzer_results):
            return _timeout_outcome(
                stage="analysis",
                reason="Swarm analysis exceeded its timeout budget; quarantining recovery for this issue.",
                analyzer_results=analyzer_results,
            )
        if _deadline_expired(recovery_deadline):
            return _timeout_outcome(stage="analysis", analyzer_results=analyzer_results)
        manager_timeout = _min_timeout(180.0, _deadline_remaining(recovery_deadline))
        if manager_timeout is not None and manager_timeout <= 0:
            return _timeout_outcome(stage="planning", analyzer_results=analyzer_results)
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
            manager_timeout_seconds=max(1, int(round(manager_timeout or 180.0))),
        )
        _emit_telemetry(
            telemetry_callback,
            "swarm_role_completed",
            _role_payload(result=manager_result, stage="planning"),
        )
        if _is_timeout_result(manager_result):
            _emit_telemetry(
                telemetry_callback,
                "swarm_role_timeout",
                {
                    "stage": "planning",
                    "role": manager_result.role,
                    "error": manager_result.error,
                },
            )
            return _timeout_outcome(stage="planning", analyzer_results=analyzer_results)
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

        remaining_before_repair = _deadline_remaining(recovery_deadline)
        if remaining_before_repair is not None and remaining_before_repair < 30.0:
            return _timeout_outcome(
                stage="repair",
                reason="Swarm recovery timed out before repair execution started.",
                analyzer_results=analyzer_results,
            )
        repair_timeout = max(runner.code_change_turn_timeout_seconds, runner.timeout_seconds)
        repair_timeout = int(max(30, round(_min_timeout(float(repair_timeout), remaining_before_repair) or repair_timeout)))
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
            timeout_seconds=repair_timeout,
            expect_json=False,
        )
        repair_result = self.backend.run(repair_request, issue_id=issue_id)
        _emit_telemetry(
            telemetry_callback,
            "swarm_role_completed",
            _role_payload(result=repair_result, stage="repair"),
        )
        if _is_timeout_result(repair_result):
            _emit_telemetry(
                telemetry_callback,
                "swarm_role_timeout",
                {
                    "stage": "repair",
                    "role": repair_result.role,
                    "error": repair_result.error,
                },
            )
            return _timeout_outcome(stage="repair", analyzer_results=analyzer_results)
        if _deadline_expired(recovery_deadline):
            return _timeout_outcome(stage="repair", analyzer_results=analyzer_results)
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
        manager_timeout_seconds: int = 180,
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
                timeout_seconds=max(1, int(manager_timeout_seconds)),
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
                f"Process marker: {SWARM_PROCESS_MARKER}\n"
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
        f"Process marker: {SWARM_PROCESS_MARKER}\n"
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
        f"- Process marker: {SWARM_PROCESS_MARKER}\n"
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
