from __future__ import annotations

from pathlib import Path

from flow_healer.skill_contracts import (
    audit_skill_contracts,
    default_action_for_diagnosis,
    expected_skill_contracts,
    recommended_skill_for_diagnosis,
)


def test_recommended_skill_for_diagnosis_routes_connector_failures_to_debug_skill() -> None:
    assert recommended_skill_for_diagnosis("connector_or_patch_generation") == "flow-healer-connector-debug"
    assert recommended_skill_for_diagnosis("repo_fixture_or_setup") == "flow-healer-preflight"
    assert default_action_for_diagnosis("external_service_or_github").startswith("Pause live mutation")


def test_audit_skill_contracts_reports_missing_skill_files(tmp_path: Path) -> None:
    audit = audit_skill_contracts(tmp_path)

    assert audit["contracts_ok"] is False
    assert audit["healthy_skills"] == 0
    assert audit["expected_skills"] == len(expected_skill_contracts())
    issues = audit["issues"]
    assert any(issue["skill"] == "flow-healer-connector-debug" for issue in issues)


def test_audit_skill_contracts_passes_for_repo_skill_docs() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    audit = audit_skill_contracts(repo_root)

    assert audit["contracts_ok"] is True
    assert audit["healthy_skills"] == audit["expected_skills"]
    recommended = audit["recommended_skill_by_diagnosis"]
    default_actions = audit["default_action_by_diagnosis"]
    assert recommended["connector_or_patch_generation"] == "flow-healer-connector-debug"
    assert recommended["operator_or_environment"] == "flow-healer-local-validation"
    assert "connector-debug" in default_actions["connector_or_patch_generation"]

    skills = {skill["skill"]: skill for skill in audit["skills"]}
    triage = skills["flow-healer-triage"]
    assert triage["has_script"] is True
    assert triage["sections_complete"] is True
    assert "diagnosis" in triage["key_output_fields"]
    assert triage["next_step_preview"].startswith("`operator_or_environment`")
