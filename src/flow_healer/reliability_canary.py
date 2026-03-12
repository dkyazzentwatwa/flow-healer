from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

_PASSED_RE = re.compile(r"(?P<count>\d+)\s+passed")
_FAILED_RE = re.compile(r"(?P<count>\d+)\s+failed")
STALE_PROFILE_DAYS = 7
ACTIVE_RUNTIME_PROFILES = ("node-next-web", "ruby-rails-web", "java-spring-web")

DEFAULT_CANARY_GROUPS: dict[str, tuple[str, ...]] = {
    "docs": (
        "tests/test_healer_task_spec.py::test_compile_task_spec_defaults_research_issue_to_docs_artifact",
        "tests/test_healer_runner.py::test_validate_artifact_outputs_passes_valid_relative_links",
    ),
    "code": (
        "tests/test_healer_runner.py::test_build_proposer_prompt_adds_native_multi_agent_guidance_for_code_tasks",
        "tests/test_healer_loop.py::test_process_claimed_issue_allows_advisory_verifier_failure_by_default",
    ),
    "mixed": (
        "tests/test_service.py::test_status_rows_report_reliability_canary_metrics",
        "tests/test_web_dashboard.py::test_collect_activity_marks_swarm_events_as_running",
    ),
}


@dataclass(slots=True, frozen=True)
class CanaryEvaluation:
    passed: bool
    failures: tuple[str, ...]
    warnings: tuple[str, ...]


def run_canary_suite(
    *,
    groups: dict[str, tuple[str, ...]] | None = None,
    pytest_bin: str = "pytest",
    timeout_seconds: int = 900,
    run_command: Callable[[list[str], int], subprocess.CompletedProcess[str]] | None = None,
    profile_last_success: dict[str, str] | None = None,
) -> dict[str, object]:
    selected_groups = groups or DEFAULT_CANARY_GROUPS
    runner = run_command or _run_command
    known_profile_last_success = profile_last_success or {}
    report_groups: dict[str, dict[str, object]] = {}
    total_duration_seconds = 0.0
    passed_groups = 0
    failed_groups = 0
    for group_name, selectors in selected_groups.items():
        command = [pytest_bin, "-q", *selectors]
        started = time.monotonic()
        completed = runner(command, timeout_seconds)
        duration_seconds = round(max(0.0, time.monotonic() - started), 3)
        total_duration_seconds += duration_seconds
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        combined = "\n".join(part for part in (stdout, stderr) if part)
        passed = completed.returncode == 0
        if passed:
            passed_groups += 1
        else:
            failed_groups += 1
        report_groups[group_name] = {
            "passed": passed,
            "duration_seconds": duration_seconds,
            "return_code": int(completed.returncode),
            "selectors": list(selectors),
            "command": command,
            "tests_passed": _extract_counter(_PASSED_RE, combined),
            "tests_failed": _extract_counter(_FAILED_RE, combined),
            "output_tail": _output_tail(combined, lines=30),
        }
    total_groups = len(report_groups)
    first_pass_success_rate = round(float(passed_groups) / float(max(1, total_groups)), 4)
    summary = {
        "total_groups": total_groups,
        "passed_groups": passed_groups,
        "failed_groups": failed_groups,
        "first_pass_success_rate": first_pass_success_rate,
        "retries_per_success": 0.0,
        "wrong_root_execution_rate": 0.0,
        "no_op_rate": 0.0,
        "mean_time_to_valid_pr_minutes": round(total_duration_seconds / 60.0, 4),
        "total_duration_seconds": round(total_duration_seconds, 3),
        "runtime_profiles": {
            profile: check_profile_freshness(known_profile_last_success.get(profile))
            for profile in ACTIVE_RUNTIME_PROFILES
        },
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "version": "1",
        "groups": report_groups,
        "summary": summary,
    }


def load_policy(path: str | Path) -> dict[str, object]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Reliability canary policy must be a JSON object.")
    return raw


def evaluate_canary_report(*, report: dict[str, object], policy: dict[str, object]) -> CanaryEvaluation:
    failures: list[str] = []
    warnings: list[str] = []
    groups = report.get("groups")
    summary = report.get("summary")
    if not isinstance(groups, dict):
        return CanaryEvaluation(False, ("Report is missing 'groups' object.",), ())
    if not isinstance(summary, dict):
        return CanaryEvaluation(False, ("Report is missing 'summary' object.",), ())

    required_groups = [str(entry).strip() for entry in (policy.get("required_groups") or []) if str(entry).strip()]
    for group_name in required_groups:
        group = groups.get(group_name)
        if not isinstance(group, dict):
            failures.append(f"Missing required canary group: {group_name}")
            continue
        if not bool(group.get("passed", False)):
            failures.append(f"Canary group failed: {group_name}")

    minimum_first_pass_success_rate = _as_float(policy.get("minimum_first_pass_success_rate"), default=0.0)
    if _as_float(summary.get("first_pass_success_rate"), default=0.0) < minimum_first_pass_success_rate:
        failures.append(
            "first_pass_success_rate below threshold: "
            f"{summary.get('first_pass_success_rate')} < {minimum_first_pass_success_rate}"
        )

    maximum_no_op_rate = _as_float(policy.get("maximum_no_op_rate"), default=1.0)
    if _as_float(summary.get("no_op_rate"), default=0.0) > maximum_no_op_rate:
        failures.append(f"no_op_rate above threshold: {summary.get('no_op_rate')} > {maximum_no_op_rate}")

    maximum_wrong_root_execution_rate = _as_float(policy.get("maximum_wrong_root_execution_rate"), default=1.0)
    if _as_float(summary.get("wrong_root_execution_rate"), default=0.0) > maximum_wrong_root_execution_rate:
        failures.append(
            "wrong_root_execution_rate above threshold: "
            f"{summary.get('wrong_root_execution_rate')} > {maximum_wrong_root_execution_rate}"
        )

    maximum_mean_time_to_valid_pr_minutes = _as_float(
        policy.get("maximum_mean_time_to_valid_pr_minutes"),
        default=1_000_000.0,
    )
    if _as_float(summary.get("mean_time_to_valid_pr_minutes"), default=0.0) > maximum_mean_time_to_valid_pr_minutes:
        failures.append(
            "mean_time_to_valid_pr_minutes above threshold: "
            f"{summary.get('mean_time_to_valid_pr_minutes')} > {maximum_mean_time_to_valid_pr_minutes}"
        )

    max_group_duration = policy.get("maximum_group_duration_seconds")
    if isinstance(max_group_duration, dict):
        for group_name, threshold in max_group_duration.items():
            group = groups.get(str(group_name))
            if not isinstance(group, dict):
                continue
            duration = _as_float(group.get("duration_seconds"), default=0.0)
            threshold_seconds = _as_float(threshold, default=0.0)
            if threshold_seconds > 0 and duration > threshold_seconds:
                failures.append(
                    f"group duration above threshold for {group_name}: {duration} > {threshold_seconds}"
                )

    baseline = policy.get("baseline")
    allowed_regression = policy.get("allowed_regression")
    if isinstance(baseline, dict):
        regressions = allowed_regression if isinstance(allowed_regression, dict) else {}
        _evaluate_baseline_regression(
            summary=summary,
            baseline=baseline,
            allowed_regression=regressions,
            failures=failures,
            warnings=warnings,
        )

    runtime_profiles = summary.get("runtime_profiles")
    if isinstance(runtime_profiles, dict):
        stale_profiles = [
            str(profile_name)
            for profile_name, freshness in runtime_profiles.items()
            if isinstance(freshness, dict) and bool(freshness.get("stale"))
        ]
        if stale_profiles:
            warnings.append(f"stale_runtime_profiles: {', '.join(sorted(stale_profiles))}")

    return CanaryEvaluation(passed=not failures, failures=tuple(failures), warnings=tuple(warnings))


def render_markdown_summary(*, report: dict[str, object], evaluation: CanaryEvaluation) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "## Reliability Canary",
        "",
        f"- Passed: `{'yes' if evaluation.passed else 'no'}`",
        f"- Groups: `{summary.get('passed_groups', 0)}` / `{summary.get('total_groups', 0)}`",
        f"- First-pass success rate: `{summary.get('first_pass_success_rate', 0.0)}`",
        f"- Mean time to valid PR (minutes): `{summary.get('mean_time_to_valid_pr_minutes', 0.0)}`",
        f"- Wrong-root execution rate: `{summary.get('wrong_root_execution_rate', 0.0)}`",
        f"- No-op rate: `{summary.get('no_op_rate', 0.0)}`",
    ]
    if evaluation.failures:
        lines.append("")
        lines.append("### Failures")
        lines.extend(f"- {item}" for item in evaluation.failures)
    if evaluation.warnings:
        lines.append("")
        lines.append("### Warnings")
        lines.extend(f"- {item}" for item in evaluation.warnings)
    return "\n".join(lines) + "\n"


def _evaluate_baseline_regression(
    *,
    summary: dict[str, object],
    baseline: dict[str, object],
    allowed_regression: dict[str, object],
    failures: list[str],
    warnings: list[str],
) -> None:
    higher_is_better = {"first_pass_success_rate"}
    lower_is_better = {
        "mean_time_to_valid_pr_minutes",
        "wrong_root_execution_rate",
        "no_op_rate",
    }
    for metric_name in sorted(set(higher_is_better | lower_is_better)):
        if metric_name not in baseline:
            continue
        current_value = _as_float(summary.get(metric_name), default=0.0)
        baseline_value = _as_float(baseline.get(metric_name), default=0.0)
        allowed = _as_float(allowed_regression.get(metric_name), default=0.0)
        if metric_name in higher_is_better:
            floor = baseline_value - max(0.0, allowed)
            if current_value < floor:
                failures.append(
                    f"{metric_name} regressed below baseline allowance: {current_value} < {floor}"
                )
            elif current_value < baseline_value:
                warnings.append(
                    f"{metric_name} is below baseline but within allowance: {current_value} < {baseline_value}"
                )
            continue
        ceiling = baseline_value + max(0.0, allowed)
        if current_value > ceiling:
            failures.append(
                f"{metric_name} regressed above baseline allowance: {current_value} > {ceiling}"
            )
        elif current_value > baseline_value:
            warnings.append(
                f"{metric_name} is above baseline but within allowance: {current_value} > {baseline_value}"
            )


def _extract_counter(pattern: re.Pattern[str], text: str) -> int:
    match = pattern.search(text or "")
    if not match:
        return 0
    try:
        return int(match.group("count"))
    except (TypeError, ValueError):
        return 0


def load_profile_last_success_from_config(
    config_path: str | Path | None = None,
    *,
    repo_name: str | None = None,
) -> dict[str, str]:
    from .config import AppConfig
    from .store import SQLiteStore

    config_target = Path(config_path).expanduser() if config_path is not None else None
    if config_target is not None and not config_target.exists():
        return {}

    app_config = AppConfig.load(config_target)
    selected_repos = app_config.select_repos(repo_name)
    if not selected_repos:
        return {}

    profile_last_success: dict[str, str] = {}
    for repo in selected_repos:
        db_path = app_config.repo_db_path(repo.repo_name)
        if not db_path.exists():
            continue
        store = SQLiteStore(db_path)
        try:
            for profile in ACTIVE_RUNTIME_PROFILES:
                last_success = str(store.get_state(f"healer_app_runtime_canary_last_success_at:{profile}") or "").strip()
                if not last_success:
                    continue
                existing = profile_last_success.get(profile, "")
                if not existing or existing < last_success:
                    profile_last_success[profile] = last_success
        finally:
            store.close()
    return profile_last_success


def check_profile_freshness(last_success_at: str | None, max_age_days: int = STALE_PROFILE_DAYS) -> dict[str, object]:
    checked_at = _parse_timestamp(last_success_at)
    if checked_at is None:
        return {
            "stale": True,
            "days_since_success": None,
            "within_window": False,
        }
    now = datetime.now(UTC)
    days_since_success = round(max(0.0, (now - checked_at).total_seconds()) / 86400.0, 4)
    within_window = days_since_success <= float(max_age_days)
    return {
        "stale": not within_window,
        "days_since_success": days_since_success,
        "within_window": within_window,
    }


def _run_command(command: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=max(30, int(timeout_seconds)),
    )


def _parse_timestamp(raw: str | None) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    candidates = (value, value.replace("Z", "+00:00"))
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    for fmt in ("%Y-%m-%d %H:%M:%S",):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _as_float(value: object, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _output_tail(text: str, *, lines: int) -> str:
    raw = (text or "").splitlines()
    if len(raw) <= lines:
        return "\n".join(raw)
    return "\n".join(raw[-lines:])
