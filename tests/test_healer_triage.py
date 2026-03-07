from __future__ import annotations

from flow_healer.healer_triage import classify_issue_route


def test_classify_issue_route_sends_connector_failures_to_debug_skill() -> None:
    route = classify_issue_route(
        {"state": "failed", "last_failure_class": "connector_unavailable", "last_failure_reason": ""},
        None,
    )

    assert route.diagnosis == "connector_or_patch_generation"
    assert route.recommended_skill == "flow-healer-connector-debug"
    assert "connector-debug" in route.default_action
    assert route.stop_recommended is True
    assert route.stop_reason.startswith("Stop before another live run")
    assert route.connector_debug_focus == "command_resolution"


def test_classify_issue_route_detects_fixture_setup_failures() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {"failure_class": "tests_failed", "failure_reason": "ImportError: No module named tests.helpers"},
    )

    assert route.diagnosis == "repo_fixture_or_setup"
    assert route.recommended_skill == "flow-healer-preflight"
    assert route.stop_recommended is True
    assert route.connector_debug_focus == ""


def test_classify_issue_route_maps_diff_contract_failures_to_connector_focus() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {"failure_class": "diff_limit_exceeded", "failure_reason": "Malformed diff fence from proposer"},
    )

    assert route.diagnosis == "connector_or_patch_generation"
    assert route.connector_debug_focus == "diff_fence"


def test_classify_issue_route_maps_runtime_connector_failures_to_runtime_crash_focus() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {"failure_class": "connector_runtime_error", "failure_reason": "ConnectorRuntimeError: Codex CLI timed out after 300s"},
    )

    assert route.diagnosis == "connector_or_patch_generation"
    assert route.recommended_skill == "flow-healer-connector-debug"
    assert route.connector_debug_focus == "runtime_crash"


def test_classify_issue_route_maps_docs_only_code_change_failures_to_contract_comparison() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {
            "failure_class": "no_code_diff",
            "failure_reason": "Code-change task produced only docs/artifact edits.",
        },
    )

    assert route.diagnosis == "connector_or_patch_generation"
    assert route.recommended_skill == "flow-healer-connector-debug"
    assert route.connector_debug_focus == "contract_comparison"
