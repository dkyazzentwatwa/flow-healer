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


def test_classify_issue_route_detects_fixture_setup_failures() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {"failure_class": "tests_failed", "failure_reason": "ImportError: No module named tests.helpers"},
    )

    assert route.diagnosis == "repo_fixture_or_setup"
    assert route.recommended_skill == "flow-healer-preflight"
