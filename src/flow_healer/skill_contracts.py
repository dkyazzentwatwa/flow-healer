from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re


_COMMON_CONTRACT_SECTIONS = (
    "## Inputs",
    "## Outputs",
    "## Key Output Fields",
    "## Success Criteria",
    "## Failure Handling",
    "## Next Step",
)


@dataclass(slots=True, frozen=True)
class SkillContract:
    name: str
    relative_path: str
    required_snippets: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class SkillContractIssue:
    skill: str
    relative_path: str
    problem: str
    details: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class SkillContractSnapshot:
    skill: str
    relative_path: str
    skill_text: str
    has_script: bool
    scripts: tuple[str, ...]
    input_fields: tuple[str, ...]
    has_default_command: bool
    default_command_preview: str
    documented_output_fields: tuple[str, ...]
    script_output_fields: tuple[str, ...]
    script_output_alignment: bool
    key_output_fields: tuple[str, ...]
    key_output_alignment: bool
    next_step_preview: str
    has_stop_conditions: bool
    stop_condition_preview: str
    stop_conditions: tuple[str, ...]
    has_operator_stop_guidance: bool
    operator_stop_guidance_preview: str
    runnable_from_skill_doc: bool
    sections_complete: bool


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def expected_skill_contracts() -> tuple[SkillContract, ...]:
    return (
        SkillContract(
            name="flow-healer-local-validation",
            relative_path="skills/flow-healer-local-validation/SKILL.md",
            required_snippets=(
                *_COMMON_CONTRACT_SECTIONS,
                "`repo_root`",
                "`checks[*].exit_code`",
                "`checks[*].output_tail`",
            ),
        ),
        SkillContract(
            name="flow-healer-preflight",
            relative_path="skills/flow-healer-preflight/SKILL.md",
            required_snippets=(
                *_COMMON_CONTRACT_SECTIONS,
                "`required_checks.gh_auth_ok`",
                "`required_checks.repo_exists`",
                "`required_checks.git_repo`",
                "`required_checks.repo_clean_git`",
                "`required_checks.venv_ok`",
                "`required_checks.docker_ok`",
            ),
        ),
        SkillContract(
            name="flow-healer-live-smoke",
            relative_path="skills/flow-healer-live-smoke/SKILL.md",
            required_snippets=(
                *_COMMON_CONTRACT_SECTIONS,
                "`docs_scaffold`",
                "`docs_followup_note`",
                "`issue_id`",
                "`pr_id`",
                "`branch_name`",
                "`attempt_state`",
                "`verifier_summary`",
                "`test_summary`",
            ),
        ),
        SkillContract(
            name="flow-healer-triage",
            relative_path="skills/flow-healer-triage/SKILL.md",
            required_snippets=(
                *_COMMON_CONTRACT_SECTIONS,
                "`operator_or_environment`",
                "`repo_fixture_or_setup`",
                "`connector_or_patch_generation`",
                "`product_bug`",
                "`external_service_or_github`",
                "`flow-healer-connector-debug`",
            ),
        ),
        SkillContract(
            name="flow-healer-pr-followup",
            relative_path="skills/flow-healer-pr-followup/SKILL.md",
            required_snippets=(
                *_COMMON_CONTRACT_SECTIONS,
                "`issue.pr_number`",
                "`issue.last_issue_comment_id`",
                "`issue.feedback_context`",
                "`issue.state`",
                "`attempts[*].state`",
                "## Safe Resume Checklist",
            ),
        ),
        SkillContract(
            name="flow-healer-connector-debug",
            relative_path="skills/flow-healer-connector-debug/SKILL.md",
            required_snippets=(
                "# Flow Healer Connector Debug",
                "Use this skill when `flow-healer-triage` reports `connector_or_patch_generation`.",
                "Connector command resolution",
                "Diff fence validity",
                "Empty diff detection",
                "Verifier JSON validity",
                "Patch-apply outcome",
            ),
        ),
    )


def operator_skill_graph() -> tuple[str, ...]:
    return (
        "flow-healer-local-validation",
        "flow-healer-preflight",
        "flow-healer-live-smoke",
        "flow-healer-triage",
        "flow-healer-pr-followup",
        "flow-healer-connector-debug",
    )


def diagnosis_buckets() -> tuple[str, ...]:
    return (
        "operator_or_environment",
        "repo_fixture_or_setup",
        "connector_or_patch_generation",
        "product_bug",
        "external_service_or_github",
    )


def skill_stage_position(skill: str) -> int:
    target = str(skill or "").strip()
    if not target:
        return 0
    try:
        return operator_skill_graph().index(target) + 1
    except ValueError:
        return 0


def next_skill_in_graph(skill: str) -> str:
    position = skill_stage_position(skill)
    if position <= 0:
        return ""
    graph = operator_skill_graph()
    return graph[position] if position < len(graph) else ""


def previous_skill_in_graph(skill: str) -> str:
    position = skill_stage_position(skill)
    if position <= 1:
        return ""
    graph = operator_skill_graph()
    return graph[position - 2]


def recommended_skill_for_diagnosis(diagnosis: str) -> str:
    normalized = str(diagnosis or "").strip().lower()
    mapping = {
        "operator_or_environment": "flow-healer-local-validation",
        "repo_fixture_or_setup": "flow-healer-preflight",
        "connector_or_patch_generation": "flow-healer-connector-debug",
        "product_bug": "flow-healer-live-smoke",
        "external_service_or_github": "flow-healer-pr-followup",
    }
    return mapping.get(normalized, "")


def default_action_for_diagnosis(diagnosis: str) -> str:
    normalized = str(diagnosis or "").strip().lower()
    mapping = {
        "operator_or_environment": "Repair the environment, then rerun flow-healer-preflight before another live attempt.",
        "repo_fixture_or_setup": "Repair the repo or fixture setup, then rerun flow-healer-local-validation.",
        "connector_or_patch_generation": "Hand off to flow-healer-connector-debug and isolate the broken proposer or verifier contract.",
        "product_bug": "Capture evidence from the latest run and escalate as a product bug.",
        "external_service_or_github": "Pause live mutation, wait or retry later, and leave an operator note about the external dependency.",
    }
    return mapping.get(normalized, "")


def diagnosis_route_catalog(root: Path | None = None) -> dict[str, dict[str, object]]:
    base = (root or repo_root()).expanduser().resolve()
    catalog: dict[str, dict[str, object]] = {}
    for diagnosis in diagnosis_buckets():
        recommended = recommended_skill_for_diagnosis(diagnosis)
        playbook = skill_playbook(recommended, base)
        catalog[diagnosis] = {
            "diagnosis": diagnosis,
            "recommended_skill": recommended,
            "default_action": default_action_for_diagnosis(diagnosis),
            "graph_position": skill_stage_position(recommended),
            "previous_skill": previous_skill_in_graph(recommended),
            "next_skill": next_skill_in_graph(recommended),
            "skill_relative_path": str(playbook.get("relative_path") or ""),
            "default_command_preview": str(playbook.get("default_command_preview") or ""),
            "key_output_fields": list(playbook.get("key_output_fields") or []),
            "stop_conditions": list(playbook.get("stop_conditions") or []),
            "next_step_preview": str(playbook.get("next_step_preview") or ""),
            "runnable_from_skill_doc": bool(playbook.get("runnable_from_skill_doc")),
        }
    return catalog


def audit_skill_contracts(root: Path | None = None) -> dict[str, object]:
    base = (root or repo_root()).expanduser().resolve()
    issues: list[SkillContractIssue] = []
    healthy = 0
    snapshots: list[SkillContractSnapshot] = []

    for contract in expected_skill_contracts():
        skill_path = base / contract.relative_path
        if not skill_path.exists():
            issues.append(
                SkillContractIssue(
                    skill=contract.name,
                    relative_path=contract.relative_path,
                    problem="missing_file",
                    details=(),
                )
            )
            continue
        text = skill_path.read_text(encoding="utf-8")
        snapshot = _skill_snapshot(base=base, contract=contract, text=text)
        snapshots.append(snapshot)
        missing = tuple(snippet for snippet in contract.required_snippets if snippet not in text)
        if missing:
            issues.append(
                SkillContractIssue(
                    skill=contract.name,
                    relative_path=contract.relative_path,
                    problem="missing_snippets",
                    details=missing,
                )
            )
            continue
        if not snapshot.sections_complete:
            issues.append(
                SkillContractIssue(
                    skill=contract.name,
                    relative_path=contract.relative_path,
                    problem="incomplete_sections",
                    details=tuple(section for section in _COMMON_CONTRACT_SECTIONS if not _section_body(text, section)),
                )
            )
            continue
        if snapshot.has_script and not snapshot.script_output_alignment:
            issues.append(
                SkillContractIssue(
                    skill=contract.name,
                    relative_path=contract.relative_path,
                    problem="script_output_mismatch",
                    details=_missing_documented_outputs(snapshot),
                )
            )
            continue
        if not snapshot.key_output_alignment:
            issues.append(
                SkillContractIssue(
                    skill=contract.name,
                    relative_path=contract.relative_path,
                    problem="key_output_mismatch",
                    details=_missing_key_outputs(snapshot),
                )
            )
            continue
        if not snapshot.runnable_from_skill_doc:
            issues.append(
                SkillContractIssue(
                    skill=contract.name,
                    relative_path=contract.relative_path,
                    problem="not_runnable_from_skill_doc",
                    details=_runnable_from_skill_doc_problems(snapshot),
                )
            )
            continue
        healthy += 1

    diagnoses = diagnosis_buckets()
    recommended = {diagnosis: recommended_skill_for_diagnosis(diagnosis) for diagnosis in diagnoses}
    default_actions = {diagnosis: default_action_for_diagnosis(diagnosis) for diagnosis in diagnoses}
    diagnosis_playbooks = {
        diagnosis: skill_playbook(recommended.get(diagnosis, ""), base)
        for diagnosis in diagnoses
        if recommended.get(diagnosis, "")
    }
    diagnosis_routes = diagnosis_route_catalog(base)
    graph = list(operator_skill_graph())
    return {
        "repo_root": str(base),
        "expected_skills": len(expected_skill_contracts()),
        "healthy_skills": healthy,
        "issues": [
            {
                "skill": issue.skill,
                "relative_path": issue.relative_path,
                "problem": issue.problem,
                "details": list(issue.details),
            }
            for issue in issues
        ],
        "contracts_ok": not issues,
        "operator_graph": graph,
        "default_action_by_diagnosis": default_actions,
        "recommended_skill_by_diagnosis": recommended,
        "diagnosis_playbooks": diagnosis_playbooks,
        "diagnosis_routes": diagnosis_routes,
        "skills": [
            {
                "skill": snapshot.skill,
                "relative_path": snapshot.relative_path,
                "has_script": snapshot.has_script,
                "scripts": list(snapshot.scripts),
                "input_fields": list(snapshot.input_fields),
                "has_default_command": snapshot.has_default_command,
                "default_command_preview": snapshot.default_command_preview,
                "documented_output_fields": list(snapshot.documented_output_fields),
                "script_output_fields": list(snapshot.script_output_fields),
                "script_output_alignment": snapshot.script_output_alignment,
                "key_output_fields": list(snapshot.key_output_fields),
                "key_output_alignment": snapshot.key_output_alignment,
                "next_step_preview": snapshot.next_step_preview,
                "graph_position": skill_stage_position(snapshot.skill),
                "previous_skill": previous_skill_in_graph(snapshot.skill),
                "next_skill": next_skill_in_graph(snapshot.skill),
                "has_stop_conditions": snapshot.has_stop_conditions,
                "stop_condition_preview": snapshot.stop_condition_preview,
                "stop_conditions": list(snapshot.stop_conditions),
                "has_operator_stop_guidance": snapshot.has_operator_stop_guidance,
                "operator_stop_guidance_preview": snapshot.operator_stop_guidance_preview,
                "runnable_from_skill_doc": snapshot.runnable_from_skill_doc,
                "sections_complete": snapshot.sections_complete,
            }
            for snapshot in snapshots
        ],
    }


def skill_playbook(skill: str, root: Path | None = None) -> dict[str, object]:
    base = (root or repo_root()).expanduser().resolve()
    target = str(skill or "").strip()
    if not target:
        return {}
    for contract in expected_skill_contracts():
        if contract.name != target:
            continue
        skill_path = base / contract.relative_path
        if not skill_path.exists():
            return {}
        text = skill_path.read_text(encoding="utf-8")
        snapshot = _skill_snapshot(base=base, contract=contract, text=text)
        return {
            "skill": snapshot.skill,
            "relative_path": snapshot.relative_path,
            "has_script": snapshot.has_script,
            "scripts": list(snapshot.scripts),
            "input_fields": list(snapshot.input_fields),
            "documented_output_fields": list(snapshot.documented_output_fields),
            "script_output_fields": list(snapshot.script_output_fields),
            "key_output_fields": list(snapshot.key_output_fields),
            "key_output_alignment": snapshot.key_output_alignment,
            "has_default_command": snapshot.has_default_command,
            "default_command_preview": snapshot.default_command_preview,
            "next_step_preview": snapshot.next_step_preview,
            "graph_position": skill_stage_position(snapshot.skill),
            "previous_skill": previous_skill_in_graph(snapshot.skill),
            "next_skill": next_skill_in_graph(snapshot.skill),
            "has_stop_conditions": snapshot.has_stop_conditions,
            "stop_condition_preview": snapshot.stop_condition_preview,
            "stop_conditions": list(snapshot.stop_conditions),
            "has_operator_stop_guidance": snapshot.has_operator_stop_guidance,
            "operator_stop_guidance_preview": snapshot.operator_stop_guidance_preview,
            "runnable_from_skill_doc": snapshot.runnable_from_skill_doc,
            "sections_complete": snapshot.sections_complete,
            "script_output_alignment": snapshot.script_output_alignment,
        }
    return {}


def _skill_snapshot(*, base: Path, contract: SkillContract, text: str) -> SkillContractSnapshot:
    skill_dir = (base / contract.relative_path).parent
    script_paths = tuple(path for path in sorted(skill_dir.glob("scripts/*.py")) if path.is_file())
    scripts = tuple(str(path.relative_to(base)) for path in script_paths)
    input_fields = _section_fields(_section_body(text, "## Inputs"))
    default_command_body = _default_command_body(text)
    stop_conditions_body = _section_body(text, "## Stop Conditions")
    documented_output_fields = _section_fields(_section_body(text, "## Outputs"))
    script_output_fields = _script_output_fields(script_paths)
    key_output_fields = _section_fields(_section_body(text, "## Key Output Fields"))
    next_step_preview = _first_content_line(_section_body(text, "## Next Step"))
    sections_complete = all(_section_body(text, section) for section in _COMMON_CONTRACT_SECTIONS)
    operator_stop_guidance = _operator_stop_guidance(text)
    return SkillContractSnapshot(
        skill=contract.name,
        relative_path=contract.relative_path,
        skill_text=text,
        has_script=bool(scripts),
        scripts=scripts,
        input_fields=input_fields,
        has_default_command=bool(default_command_body.strip()),
        default_command_preview=_command_preview(default_command_body),
        documented_output_fields=documented_output_fields,
        script_output_fields=script_output_fields,
        script_output_alignment=_documented_outputs_align(
            documented_output_fields=documented_output_fields,
            script_output_fields=script_output_fields,
            has_script=bool(scripts),
        ),
        key_output_fields=key_output_fields,
        key_output_alignment=_key_outputs_align(
            key_output_fields=key_output_fields,
            documented_output_fields=documented_output_fields,
            script_output_fields=script_output_fields,
            skill_text=text,
        ),
        next_step_preview=next_step_preview,
        has_stop_conditions=bool(stop_conditions_body.strip()),
        stop_condition_preview=_first_content_line(stop_conditions_body),
        stop_conditions=_content_lines(stop_conditions_body),
        has_operator_stop_guidance=bool(operator_stop_guidance.strip()),
        operator_stop_guidance_preview=_first_content_line(operator_stop_guidance),
        runnable_from_skill_doc=_runnable_from_skill_doc(
            has_script=bool(scripts),
            has_default_command=bool(default_command_body.strip()),
            input_fields=input_fields,
            documented_output_fields=documented_output_fields,
            key_output_fields=key_output_fields,
            next_step_preview=next_step_preview,
            operator_stop_guidance=operator_stop_guidance,
            sections_complete=sections_complete,
        ),
        sections_complete=sections_complete,
    )


def _section_body(text: str, heading: str) -> str:
    lines = (text or "").splitlines()
    capture = False
    body: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == heading:
            capture = True
            continue
        if capture and stripped.startswith("## "):
            break
        if capture:
            body.append(line.rstrip())
    return "\n".join(line for line in body if line.strip()).strip()


def _default_command_body(text: str) -> str:
    for heading in ("## Default Command", "## Default Generator", "## Default Run"):
        body = _section_body(text, heading)
        if body:
            return body
    return ""


def _inline_code_tokens(text: str) -> tuple[str, ...]:
    tokens = re.findall(r"`([^`]+)`", text or "")
    return tuple(token for token in tokens if token)


def _section_fields(text: str) -> tuple[str, ...]:
    inline = _inline_code_tokens(text)
    if inline:
        return inline
    return _content_lines(text)


def _script_output_fields(script_paths: tuple[Path, ...]) -> tuple[str, ...]:
    seen: list[str] = []
    for script_path in script_paths:
        for field in _extract_script_output_fields(script_path):
            if field not in seen:
                seen.append(field)
    return tuple(seen)


def _extract_script_output_fields(script_path: Path) -> tuple[str, ...]:
    try:
        tree = ast.parse(script_path.read_text(encoding="utf-8"), filename=str(script_path))
    except (OSError, SyntaxError):
        return ()

    assigned_dicts: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            keys = _dict_string_keys(node.value)
            if not keys:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned_dicts[target.id] = keys
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            keys = _dict_string_keys(node.value)
            if keys:
                assigned_dicts[node.target.id] = keys

    seen: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "dumps" or not node.args:
            continue
        keys = _dict_string_keys(node.args[0])
        if not keys and isinstance(node.args[0], ast.Name):
            keys = assigned_dicts.get(node.args[0].id, ())
        for key in keys:
            if key not in seen:
                seen.append(key)
    return tuple(seen)


def _dict_string_keys(node: ast.AST | None) -> tuple[str, ...]:
    if not isinstance(node, ast.Dict):
        return ()
    keys: list[str] = []
    for key_node in node.keys:
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            keys.append(key_node.value)
    return tuple(keys)


def _documented_outputs_align(
    *,
    documented_output_fields: tuple[str, ...],
    script_output_fields: tuple[str, ...],
    has_script: bool,
) -> bool:
    if not has_script:
        return True
    if not documented_output_fields or not script_output_fields:
        return False
    return all(field in script_output_fields for field in documented_output_fields)


def _missing_documented_outputs(snapshot: SkillContractSnapshot) -> tuple[str, ...]:
    if not snapshot.script_output_fields:
        return ("Could not infer any top-level JSON output fields from the skill script.",)
    missing = tuple(
        field for field in snapshot.documented_output_fields if field not in snapshot.script_output_fields
    )
    if missing:
        return missing
    return ("Documented output fields do not align with the script contract.",)


def _key_outputs_align(
    *,
    key_output_fields: tuple[str, ...],
    documented_output_fields: tuple[str, ...],
    script_output_fields: tuple[str, ...],
    skill_text: str,
) -> bool:
    if not key_output_fields:
        return False
    referenced_roots = {
        _field_root(field)
        for field in key_output_fields
        if _looks_like_output_field(field)
    }
    if not referenced_roots:
        return True
    available_roots = {
        _field_root(field)
        for field in (*documented_output_fields, *script_output_fields)
        if _looks_like_output_field(field)
    }
    for root in referenced_roots:
        if root in available_roots:
            continue
        if _field_documented_elsewhere(skill_text=skill_text, field=root):
            continue
        return False
    return True


def _missing_key_outputs(snapshot: SkillContractSnapshot) -> tuple[str, ...]:
    available_roots = {
        _field_root(field)
        for field in (*snapshot.documented_output_fields, *snapshot.script_output_fields)
        if _looks_like_output_field(field)
    }
    missing = tuple(
        field
        for field in snapshot.key_output_fields
        if _looks_like_output_field(field)
        and _field_root(field) not in available_roots
        and not _field_documented_elsewhere(skill_text=snapshot.skill_text, field=_field_root(field))
    )
    if missing:
        return missing
    return ("Key output fields do not align with the documented or scripted outputs.",)


def _looks_like_output_field(field: str) -> bool:
    token = str(field or "").strip()
    if not token:
        return False
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\[\*\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\*\])?)*", token))


def _field_root(field: str) -> str:
    token = str(field or "").strip()
    if not token:
        return ""
    return token.split(".", 1)[0].replace("[*]", "")


def _field_documented_elsewhere(*, skill_text: str, field: str) -> bool:
    needle = f"`{field}`"
    return skill_text.count(needle) > 1


def _first_content_line(text: str) -> str:
    lines = _content_lines(text)
    return lines[0] if lines else ""


def _content_lines(text: str) -> tuple[str, ...]:
    lines: list[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lines.append(line.lstrip("- ").strip())
    return tuple(lines)


def _command_preview(text: str) -> str:
    in_fence = False
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or line:
            return line.lstrip("- ").strip()
    return ""


def _operator_stop_guidance(text: str) -> str:
    explicit = _section_body(text, "## Stop Conditions")
    if explicit.strip():
        return explicit
    candidates: list[str] = []
    for heading in ("## Failure Handling", "## Workflow", "## Next Step"):
        body = _section_body(text, heading)
        for line in _content_lines(body):
            if _looks_like_stop_guidance(line):
                candidates.append(line)
    return "\n".join(candidates).strip()


def _looks_like_stop_guidance(line: str) -> bool:
    lowered = str(line or "").strip().lower()
    if not lowered:
        return False
    return any(
        marker in lowered
        for marker in (
            "stop",
            "pause",
            "blocked",
            "no-go",
            "repair",
            "escalate",
        )
    )


def _runnable_from_skill_doc(
    *,
    has_script: bool,
    has_default_command: bool,
    input_fields: tuple[str, ...],
    documented_output_fields: tuple[str, ...],
    key_output_fields: tuple[str, ...],
    next_step_preview: str,
    operator_stop_guidance: str,
    sections_complete: bool,
) -> bool:
    if not sections_complete:
        return False
    if has_script and not has_default_command:
        return False
    if not input_fields or not documented_output_fields or not key_output_fields:
        return False
    if not next_step_preview.strip():
        return False
    return bool(operator_stop_guidance.strip())


def _runnable_from_skill_doc_problems(snapshot: SkillContractSnapshot) -> tuple[str, ...]:
    problems: list[str] = []
    if snapshot.has_script and not snapshot.has_default_command:
        problems.append("Missing `## Default Command` content for a scripted skill.")
    if not snapshot.input_fields:
        problems.append("Missing `## Inputs` details.")
    if not snapshot.documented_output_fields:
        problems.append("Missing `## Outputs` details.")
    if not snapshot.key_output_fields:
        problems.append("Missing `## Key Output Fields` details.")
    if not snapshot.next_step_preview:
        problems.append("Missing `## Next Step` guidance.")
    if not snapshot.has_operator_stop_guidance:
        problems.append("Missing stop guidance in `## Stop Conditions`, `## Failure Handling`, or `## Next Step`.")
    return tuple(problems) or ("Skill contract is not runnable from SKILL.md alone.",)
