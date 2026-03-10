from __future__ import annotations

import subprocess

from flow_healer.reliability_canary import (
    CanaryEvaluation,
    evaluate_canary_report,
    render_markdown_summary,
    run_canary_suite,
)


def test_run_canary_suite_builds_summary_from_group_results() -> None:
    def fake_runner(command: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        if "tests/docs.py::test_ok" in command:
            return subprocess.CompletedProcess(command, 0, stdout="2 passed in 0.02s", stderr="")
        return subprocess.CompletedProcess(command, 1, stdout="1 failed, 1 passed in 0.03s", stderr="")

    report = run_canary_suite(
        groups={
            "docs": ("tests/docs.py::test_ok",),
            "code": ("tests/code.py::test_fail",),
        },
        run_command=fake_runner,
    )

    summary = report["summary"]
    assert summary["total_groups"] == 2
    assert summary["passed_groups"] == 1
    assert summary["failed_groups"] == 1
    assert summary["first_pass_success_rate"] == 0.5
    groups = report["groups"]
    assert groups["docs"]["passed"] is True
    assert groups["docs"]["tests_passed"] == 2
    assert groups["code"]["passed"] is False
    assert groups["code"]["tests_failed"] == 1


def test_evaluate_canary_report_checks_thresholds_and_required_groups() -> None:
    report = {
        "groups": {
            "docs": {"passed": True, "duration_seconds": 12},
            "code": {"passed": False, "duration_seconds": 301},
        },
        "summary": {
            "first_pass_success_rate": 0.5,
            "no_op_rate": 0.2,
            "wrong_root_execution_rate": 0.2,
            "mean_time_to_valid_pr_minutes": 7.0,
            "total_groups": 2,
            "passed_groups": 1,
        },
    }
    policy = {
        "required_groups": ["docs", "code", "mixed"],
        "minimum_first_pass_success_rate": 1.0,
        "maximum_no_op_rate": 0.1,
        "maximum_wrong_root_execution_rate": 0.1,
        "maximum_mean_time_to_valid_pr_minutes": 6.0,
        "maximum_group_duration_seconds": {"code": 300},
    }

    evaluation = evaluate_canary_report(report=report, policy=policy)

    assert evaluation.passed is False
    assert any("Canary group failed: code" in item for item in evaluation.failures)
    assert any("Missing required canary group: mixed" in item for item in evaluation.failures)
    assert any("first_pass_success_rate below threshold" in item for item in evaluation.failures)
    assert any("no_op_rate above threshold" in item for item in evaluation.failures)
    assert any("wrong_root_execution_rate above threshold" in item for item in evaluation.failures)
    assert any("mean_time_to_valid_pr_minutes above threshold" in item for item in evaluation.failures)
    assert any("group duration above threshold for code" in item for item in evaluation.failures)


def test_evaluate_canary_report_checks_baseline_regression() -> None:
    report = {
        "groups": {
            "docs": {"passed": True, "duration_seconds": 12},
            "code": {"passed": True, "duration_seconds": 15},
            "mixed": {"passed": True, "duration_seconds": 14},
        },
        "summary": {
            "first_pass_success_rate": 0.9,
            "no_op_rate": 0.04,
            "wrong_root_execution_rate": 0.05,
            "mean_time_to_valid_pr_minutes": 2.7,
            "total_groups": 3,
            "passed_groups": 3,
        },
    }
    policy = {
        "required_groups": ["docs", "code", "mixed"],
        "minimum_first_pass_success_rate": 0.8,
        "maximum_no_op_rate": 0.2,
        "maximum_wrong_root_execution_rate": 0.2,
        "maximum_mean_time_to_valid_pr_minutes": 6.0,
        "baseline": {
            "first_pass_success_rate": 1.0,
            "no_op_rate": 0.0,
            "wrong_root_execution_rate": 0.0,
            "mean_time_to_valid_pr_minutes": 1.0,
        },
        "allowed_regression": {
            "first_pass_success_rate": 0.0,
            "no_op_rate": 0.05,
            "wrong_root_execution_rate": 0.05,
            "mean_time_to_valid_pr_minutes": 2.0,
        },
    }

    evaluation = evaluate_canary_report(report=report, policy=policy)

    assert evaluation.passed is False
    assert any("first_pass_success_rate regressed" in item for item in evaluation.failures)
    assert any("mean_time_to_valid_pr_minutes is above baseline but within allowance" in item for item in evaluation.warnings)


def test_render_markdown_summary_contains_failure_sections() -> None:
    markdown = render_markdown_summary(
        report={
            "summary": {
                "total_groups": 3,
                "passed_groups": 2,
                "first_pass_success_rate": 0.6667,
                "mean_time_to_valid_pr_minutes": 1.25,
                "wrong_root_execution_rate": 0.1,
                "no_op_rate": 0.0,
            }
        },
        evaluation=CanaryEvaluation(
            passed=False,
            failures=("Canary group failed: mixed",),
            warnings=("first_pass_success_rate is below baseline but within allowance",),
        ),
    )

    assert "## Reliability Canary" in markdown
    assert "### Failures" in markdown
    assert "### Warnings" in markdown
