from __future__ import annotations

from flow_healer.healer_triage import classify_issue_route


def test_classify_issue_route_sends_connector_failures_to_debug_skill() -> None:
    route = classify_issue_route(
        {"state": "failed", "last_failure_class": "connector_unavailable", "last_failure_reason": ""},
        None,
    )

    assert route.diagnosis == "connector_or_patch_generation"
    assert route.failure_family == "connector_patch"
    assert route.recommended_skill == "flow-healer-connector-debug"
    assert "connector-debug" in route.default_action
    assert route.graph_position == 6
    assert route.previous_skill == "flow-healer-pr-followup"
    assert route.next_skill == ""
    assert route.skill_relative_path.endswith("skills/flow-healer-connector-debug/SKILL.md")
    assert "scripts/inspect_issue_state.py" not in route.default_command_preview
    assert "Diff fence validity" in route.key_output_fields
    assert route.stop_conditions == ()
    assert route.stop_recommended is True
    assert route.stop_reason.startswith("Stop before another live run")
    assert route.connector_debug_focus == "command_resolution"
    assert route.connector_debug_checks == (
        "Validate connector command resolution",
        "Confirm the configured binary or wrapper is executable",
        "Capture the resolved command and invocation path before retrying",
    )


def test_classify_issue_route_detects_fixture_setup_failures() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {"failure_class": "tests_failed", "failure_reason": "ImportError: No module named tests.helpers"},
    )

    assert route.diagnosis == "repo_fixture_or_setup"
    assert route.failure_family == "automation_process"
    assert route.recommended_skill == "flow-healer-preflight"
    assert route.graph_position == 2
    assert route.previous_skill == "flow-healer-local-validation"
    assert route.next_skill == "flow-healer-live-smoke"
    assert route.skill_relative_path.endswith("skills/flow-healer-preflight/SKILL.md")
    assert route.default_command_preview
    assert route.stop_conditions
    assert route.stop_recommended is True
    assert route.connector_debug_focus == ""


def test_classify_issue_route_maps_diff_contract_failures_to_connector_focus() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {"failure_class": "diff_limit_exceeded", "failure_reason": "Malformed diff fence from proposer"},
    )

    assert route.diagnosis == "connector_or_patch_generation"
    assert route.failure_family == "connector_patch"
    assert route.connector_debug_focus == "diff_fence"
    assert route.connector_debug_checks[0] == "Validate diff fence validity"


def test_classify_issue_route_maps_empty_diff_failures_to_empty_diff_focus() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {"failure_class": "empty_diff", "failure_reason": "Proposer returned an empty diff fenced block."},
    )

    assert route.diagnosis == "connector_or_patch_generation"
    assert route.failure_family == "connector_patch"
    assert route.connector_debug_focus == "empty_diff"


def test_classify_issue_route_maps_malformed_diff_failures_to_diff_fence_focus() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {
            "failure_class": "malformed_diff",
            "failure_reason": "Proposer returned a diff fence, but the contents were not a valid unified diff.",
        },
    )

    assert route.diagnosis == "connector_or_patch_generation"
    assert route.failure_family == "connector_patch"
    assert route.connector_debug_focus == "diff_fence"


def test_classify_issue_route_maps_runtime_connector_failures_to_runtime_crash_focus() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {"failure_class": "connector_runtime_error", "failure_reason": "ConnectorRuntimeError: Codex CLI timed out after 300s"},
    )

    assert route.diagnosis == "connector_or_patch_generation"
    assert route.failure_family == "connector_patch"
    assert route.recommended_skill == "flow-healer-connector-debug"
    assert route.connector_debug_focus == "runtime_crash"
    assert route.connector_debug_checks[0] == "Rerun the connector against a fixed prompt fixture"


def test_classify_issue_route_maps_docs_only_code_change_failures_to_contract_comparison() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {
            "failure_class": "no_code_diff",
            "failure_reason": "Code-change task produced only docs/artifact edits.",
        },
    )

    assert route.diagnosis == "connector_or_patch_generation"
    assert route.failure_family == "connector_patch"
    assert route.recommended_skill == "flow-healer-connector-debug"
    assert route.connector_debug_focus == "contract_comparison"
    assert route.connector_debug_checks[0] == "Compare proposer and verifier contracts"


def test_classify_issue_route_maps_verifier_payload_failures_to_json_checks() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {"failure_class": "verifier_failed", "failure_reason": "Invalid JSON payload: missing verdict field"},
    )

    assert route.diagnosis == "connector_or_patch_generation"
    assert route.failure_family == "connector_patch"
    assert route.connector_debug_focus == "verifier_payload"
    assert route.connector_debug_checks == (
        "Validate any verifier payload as JSON",
        "Confirm the expected verdict and summary fields are present",
        "Compare verifier output with the expected strict JSON contract",
    )


def test_classify_issue_route_treats_non_fast_forward_push_as_automation_process() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {
            "failure_class": "push_non_fast_forward",
            "failure_reason": "non-fast-forward push rejected for healer branch",
        },
    )

    assert route.diagnosis == "automation_or_process"
    assert route.failure_family == "automation_process"


def test_classify_issue_route_treats_plain_tests_failed_as_product_bug() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {"failure_class": "tests_failed", "failure_reason": "AssertionError: expected 200 got 500"},
    )

    assert route.diagnosis == "product_bug"
    assert route.failure_family == "product"


def test_classify_issue_route_treats_semantic_verifier_failure_as_product_bug() -> None:
    route = classify_issue_route(
        {"state": "failed"},
        {"failure_class": "verifier_failed", "failure_reason": "Patch is broader than the requested sandbox scope."},
    )

    assert route.diagnosis == "product_bug"
    assert route.failure_family == "product"
