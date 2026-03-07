from __future__ import annotations

from pathlib import Path

from flow_healer.skill_contracts import (
    audit_skill_contracts,
    diagnosis_route_catalog,
    default_action_for_diagnosis,
    expected_skill_contracts,
    next_skill_in_graph,
    operator_skill_graph,
    previous_skill_in_graph,
    recommended_skill_for_diagnosis,
    skill_stage_position,
)


def test_recommended_skill_for_diagnosis_routes_connector_failures_to_debug_skill() -> None:
    assert recommended_skill_for_diagnosis("connector_or_patch_generation") == "flow-healer-connector-debug"
    assert recommended_skill_for_diagnosis("repo_fixture_or_setup") == "flow-healer-preflight"
    assert default_action_for_diagnosis("external_service_or_github").startswith("Pause live mutation")


def test_operator_skill_graph_exposes_stage_order() -> None:
    assert operator_skill_graph() == (
        "flow-healer-local-validation",
        "flow-healer-preflight",
        "flow-healer-live-smoke",
        "flow-healer-triage",
        "flow-healer-pr-followup",
        "flow-healer-connector-debug",
    )
    assert skill_stage_position("flow-healer-triage") == 4
    assert previous_skill_in_graph("flow-healer-triage") == "flow-healer-live-smoke"
    assert next_skill_in_graph("flow-healer-triage") == "flow-healer-pr-followup"
    assert next_skill_in_graph("flow-healer-connector-debug") == ""


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
    diagnosis_playbooks = audit["diagnosis_playbooks"]
    diagnosis_routes = audit["diagnosis_routes"]
    assert recommended["connector_or_patch_generation"] == "flow-healer-connector-debug"
    assert recommended["operator_or_environment"] == "flow-healer-local-validation"
    assert "connector-debug" in default_actions["connector_or_patch_generation"]
    connector_playbook = diagnosis_playbooks["connector_or_patch_generation"]
    assert connector_playbook["skill"] == "flow-healer-connector-debug"
    assert "flow-healer-connector-debug/SKILL.md" in connector_playbook["relative_path"]
    assert "Patch-apply outcome" in connector_playbook["key_output_fields"]
    assert connector_playbook["next_step_preview"]
    assert connector_playbook["graph_position"] == 6
    assert connector_playbook["previous_skill"] == "flow-healer-pr-followup"
    assert connector_playbook["next_skill"] == ""
    connector_route = diagnosis_routes["connector_or_patch_generation"]
    assert connector_route["recommended_skill"] == "flow-healer-connector-debug"
    assert connector_route["default_action"].startswith("Hand off to flow-healer-connector-debug")
    assert connector_route["graph_position"] == 6
    assert connector_route["previous_skill"] == "flow-healer-pr-followup"
    assert connector_route["next_skill"] == ""
    assert connector_route["skill_relative_path"].endswith("skills/flow-healer-connector-debug/SKILL.md")
    assert connector_route["runnable_from_skill_doc"] is True

    skills = {skill["skill"]: skill for skill in audit["skills"]}
    triage = skills["flow-healer-triage"]
    preflight = skills["flow-healer-preflight"]
    assert triage["has_script"] is True
    assert triage["script_output_alignment"] is True
    assert triage["sections_complete"] is True
    assert triage["documented_output_fields"] == ["issue", "latest_attempt", "diagnosis"]
    assert "recommended_skill" in triage["script_output_fields"]
    assert "diagnosis" in triage["key_output_fields"]
    assert triage["key_output_alignment"] is True
    assert triage["next_step_preview"].startswith("`operator_or_environment`")
    assert triage["has_default_command"] is True
    assert triage["default_command_preview"]
    assert triage["graph_position"] == 4
    assert triage["previous_skill"] == "flow-healer-live-smoke"
    assert triage["next_skill"] == "flow-healer-pr-followup"
    assert triage["has_stop_conditions"] is False
    assert triage["stop_condition_preview"] == ""
    assert triage["has_operator_stop_guidance"] is True
    assert triage["operator_stop_guidance_preview"].startswith("If the issue row is missing")
    assert triage["runnable_from_skill_doc"] is True
    assert preflight["has_stop_conditions"] is True
    assert preflight["stop_condition_preview"]
    assert preflight["has_operator_stop_guidance"] is True
    assert preflight["runnable_from_skill_doc"] is True


def test_diagnosis_route_catalog_exposes_graph_and_playbook_details() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    routes = diagnosis_route_catalog(repo_root)

    assert routes["operator_or_environment"]["recommended_skill"] == "flow-healer-local-validation"
    assert routes["operator_or_environment"]["graph_position"] == 1
    assert routes["repo_fixture_or_setup"]["next_skill"] == "flow-healer-live-smoke"
    assert routes["connector_or_patch_generation"]["key_output_fields"] == [
        "Connector command resolution",
        "Diff fence validity",
        "Empty diff detection",
        "Verifier JSON validity",
        "Patch-apply outcome",
    ]


def test_audit_skill_contracts_flags_output_mismatch_for_scripted_skill(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "flow-healer-local-validation"
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "local_validation.py").write_text(
        "import json\nreport = {'repo_root': '.'}\nprint(json.dumps(report))\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "# Flow Healer Local Validation",
                "## Inputs",
                "- `repo_root`",
                "## Outputs",
                "- `repo_root`",
                "- `checks`",
                "## Key Output Fields",
                "- `repo_root`",
                "- `checks[*].exit_code`",
                "- `checks[*].output_tail`",
                "## Success Criteria",
                "- pass",
                "## Failure Handling",
                "- fail",
                "## Next Step",
                "- next",
            ]
        ),
        encoding="utf-8",
    )

    for contract in expected_skill_contracts()[1:]:
        other_skill_path = tmp_path / contract.relative_path
        other_skill_path.parent.mkdir(parents=True, exist_ok=True)
        other_skill_path.write_text("\n".join(contract.required_snippets), encoding="utf-8")

    audit = audit_skill_contracts(tmp_path)

    issue = next(item for item in audit["issues"] if item["skill"] == "flow-healer-local-validation")
    assert issue["problem"] == "script_output_mismatch"
    assert issue["details"] == ["checks"]


def test_audit_skill_contracts_requires_default_command_for_scripted_skills(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "flow-healer-local-validation"
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "local_validation.py").write_text(
        "import json\nreport = {'repo_root': '.', 'checks': []}\nprint(json.dumps(report))\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "# Flow Healer Local Validation",
                "## Inputs",
                "- `repo_root`",
                "## Outputs",
                "- `repo_root`",
                "- `checks`",
                "## Key Output Fields",
                "- `repo_root`",
                "- `checks[*].exit_code`",
                "- `checks[*].output_tail`",
                "## Success Criteria",
                "- pass",
                "## Failure Handling",
                "- Stop and repair the environment before another live run.",
                "## Next Step",
                "- rerun preflight",
            ]
        ),
        encoding="utf-8",
    )

    for contract in expected_skill_contracts()[1:]:
        other_skill_path = tmp_path / contract.relative_path
        other_skill_path.parent.mkdir(parents=True, exist_ok=True)
        other_skill_path.write_text("\n".join(contract.required_snippets), encoding="utf-8")

    audit = audit_skill_contracts(tmp_path)

    issue = next(item for item in audit["issues"] if item["skill"] == "flow-healer-local-validation")
    assert issue["problem"] == "not_runnable_from_skill_doc"
    assert issue["details"] == ["Missing `## Default Command` content for a scripted skill."]


def test_audit_skill_contracts_flags_key_output_field_mismatch(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "flow-healer-local-validation"
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "local_validation.py").write_text(
        "import json\nreport = {'repo_root': '.', 'checks': []}\nprint(json.dumps(report))\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "# Flow Healer Local Validation",
                "## Inputs",
                "- `repo_root`",
                "## Outputs",
                "- `repo_root`",
                "- `checks`",
                "## Key Output Fields",
                "- `repo_root`",
                "- `checks[*].exit_code`",
                "- `checks[*].output_tail`",
                "- `missing_field`",
                "## Success Criteria",
                "- pass",
                "## Failure Handling",
                "- Stop and repair the environment before another live run.",
                "## Next Step",
                "- rerun preflight",
                "## Default Command",
                "- `python scripts/local_validation.py`",
            ]
        ),
        encoding="utf-8",
    )

    for contract in expected_skill_contracts()[1:]:
        other_skill_path = tmp_path / contract.relative_path
        other_skill_path.parent.mkdir(parents=True, exist_ok=True)
        other_skill_path.write_text("\n".join(contract.required_snippets), encoding="utf-8")

    audit = audit_skill_contracts(tmp_path)

    issue = next(item for item in audit["issues"] if item["skill"] == "flow-healer-local-validation")
    assert issue["problem"] == "key_output_mismatch"
    assert issue["details"] == ["missing_field"]
