from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class HealerTaskSpec:
    task_kind: str
    output_mode: str
    output_targets: tuple[str, ...]
    tool_policy: str
    validation_profile: str
    input_context_paths: tuple[str, ...] = ()
    language: str = ""
    language_source: str = ""
    framework: str = ""
    framework_source: str = ""
    execution_root: str = ""
    validation_commands: tuple[str, ...] = ()
    app_target: str = ""
    entry_url: str = ""
    repro_steps: tuple[str, ...] = ()
    fixture_profile: str = ""
    artifact_requirements: tuple[str, ...] = ()
    runtime_profile: str = ""
    judgment_required_conditions: tuple[str, ...] = ()
    parse_confidence: float = 1.0


@dataclass(slots=True, frozen=True)
class IssueContractLint:
    reason_codes: tuple[str, ...]
    suggested_execution_root: str = ""

    @property
    def is_valid(self) -> bool:
        return not self.reason_codes


_EXPLICIT_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:\.?/)?(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:md|mdx|rst|txt|py|yaml|yml|json|toml|ini|cfg|conf|js|ts|tsx|jsx|css|html|go|rs|rb|java|kt|scala|swift|c|cpp|h|hpp|gradle|kts|sql))"
,
    re.IGNORECASE,
)
_PATH_DIRECTIVE_RE = re.compile(r"\bpath:\s*(?P<path>[^\s`'\"(){}<>,;:]+)", re.IGNORECASE)
_BUILD_HINT_RE = re.compile(r"\b(build|feature|implement|scaffold|bootstrap)\b", re.IGNORECASE)
_FIX_HINT_RE = re.compile(r"\b(fix|bug|repair|regression|stabilize|harden|tighten|narrow|correct)\b", re.IGNORECASE)
_CODE_HINT_RE = re.compile(r"\b(build|feature|implement|fix|bug|refactor|code)\b", re.IGNORECASE)
_RESEARCH_HINT_RE = re.compile(r"\b(research|investigate|analyze|compare|survey|look up|best ways|best practices)\b", re.IGNORECASE)
_DOC_HINT_RE = re.compile(r"\b(plan|spec|doc|docs|readme|guide|proposal|notes|write up|document)\b", re.IGNORECASE)
_EDIT_HINT_RE = re.compile(r"\b(edit|revise|update|rewrite|expand|tighten|clarify)\b", re.IGNORECASE)
_OUTPUT_CONTEXT_RE = re.compile(r"\b(output|deliverable|required output|required outputs|create|write|generate|report)\b", re.IGNORECASE)
_SCOPE_CONTEXT_RE = re.compile(r"\b(scope|review|analyze|inspect|input|source files?)\b", re.IGNORECASE)
_TASK_KIND_RE = re.compile(r"^\s*[-*]?\s*task\s*kind:\s*([a-zA-Z]+)\s*$", re.IGNORECASE)
_INPUT_CONTEXT_RE = re.compile(
    r"\b(input context|input spec|spec only|input only|input-only|not the output target|not output targets?)\b",
    re.IGNORECASE,
)
_DIRECTORY_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:\.?/)?(?:[A-Za-z0-9_.-]+/)+(?:[A-Za-z0-9_.-]+/)?)"
)
_COMMAND_LINE_RE = re.compile(
    r"(?:^|\b)(?:cd\s+[^\n&|;]+&&\s*)?"
    r"(?:npm\s+test|npm\s+run\s+(?:lint|test|build|smoke)\b|"
    r"pnpm\s+test\b|pnpm\s+run\s+(?:lint|test|build|smoke)\b|"
    r"yarn\s+test\b|yarn\s+run\s+(?:lint|test|build|smoke)\b|"
    r"bun\s+test\b|bun\s+run\s+(?:lint|test|build|smoke)\b|"
    r"pytest\b|python(?:3(?:\.\d+)?)?\s+-m\s+pytest\b|python(?:3(?:\.\d+)?)?\s+manage\.py\s+test\b|bundle\s+exec\s+rspec\b|cargo\s+test\b|go\s+test\b|swift\s+test\b|mvn\s+test\b|\./gradlew\s+test\b|\./scripts/healer_validate\.sh\b)"
    r"[^\n]*",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"\bhttps?://[^\s)>`]+", re.IGNORECASE)
_DIRECTIVE_LINE_RE = re.compile(r"^(?P<label>[A-Za-z][A-Za-z0-9 _-]+?)\s*:\s*(?P<value>.*)$")
_LIST_ITEM_PREFIX_RE = re.compile(r"^(?:[-*]\s+|\d+[.)]\s+)")

_CONTRACT_SCALAR_FIELD_NAMES: tuple[str, ...] = (
    "app_target",
    "entry_url",
    "execution_root",
    "fixture_profile",
    "runtime_profile",
)
_CONTRACT_LIST_FIELD_NAMES: tuple[str, ...] = (
    "repro_steps",
    "artifact_requirements",
    "judgment_required_conditions",
)
_CONTRACT_FIELD_NAMES = set((*_CONTRACT_SCALAR_FIELD_NAMES, *_CONTRACT_LIST_FIELD_NAMES))

_LANGUAGE_COMMAND_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bnpm\s+test\b", re.IGNORECASE), "node"),
    (re.compile(r"\bpnpm\s+test\b|\bpnpm\s+run\s+test\b", re.IGNORECASE), "node"),
    (re.compile(r"\byarn\s+test\b|\byarn\s+run\s+test\b", re.IGNORECASE), "node"),
    (re.compile(r"\bbun\s+test\b|\bbun\s+run\s+test\b", re.IGNORECASE), "node"),
    (re.compile(r"\bpython(?:3(?:\.\d+)?)?\s+-m\s+pytest\b|\bpytest\b", re.IGNORECASE), "python"),
    (re.compile(r"\bpython(?:3(?:\.\d+)?)?\s+manage\.py\s+test\b", re.IGNORECASE), "python"),
    (re.compile(r"\bbundle\s+exec\s+rspec\b|\brspec\b", re.IGNORECASE), "ruby"),
    (re.compile(r"\bcargo\s+test\b", re.IGNORECASE), "rust"),
    (re.compile(r"\bgo\s+test\b", re.IGNORECASE), "go"),
    (re.compile(r"\bswift\s+test\b", re.IGNORECASE), "swift"),
    (re.compile(r"\bmvn\s+test\b", re.IGNORECASE), "java_maven"),
    (re.compile(r"\./gradlew\s+test\b", re.IGNORECASE), "java_gradle"),
)

_LANGUAGE_PATH_HINTS: tuple[tuple[str, str], ...] = (
    ("e2e-smoke/node", "node"),
    ("e2e-smoke/js-next", "node"),
    ("e2e-smoke/js-vue-vite", "node"),
    ("e2e-smoke/js-nuxt", "node"),
    ("e2e-smoke/js-angular", "node"),
    ("e2e-smoke/js-sveltekit", "node"),
    ("e2e-smoke/js-express", "node"),
    ("e2e-smoke/js-nest", "node"),
    ("e2e-smoke/js-remix", "node"),
    ("e2e-smoke/js-astro", "node"),
    ("e2e-smoke/js-solidstart", "node"),
    ("e2e-smoke/js-qwik", "node"),
    ("e2e-smoke/js-hono", "node"),
    ("e2e-smoke/js-koa", "node"),
    ("e2e-smoke/js-adonis", "node"),
    ("e2e-smoke/js-redwoodsdk", "node"),
    ("e2e-smoke/js-lit", "node"),
    ("e2e-smoke/js-alpine-vite", "node"),
    ("e2e-smoke/python", "python"),
    ("e2e-smoke/py-fastapi", "python"),
    ("e2e-smoke/py-django", "python"),
    ("e2e-smoke/py-flask", "python"),
    ("e2e-smoke/py-data-pandas", "python"),
    ("e2e-smoke/py-ml-sklearn", "python"),
    ("e2e-smoke/go", "go"),
    ("e2e-smoke/rust", "rust"),
    ("e2e-smoke/swift", "swift"),
    ("e2e-smoke/ruby", "ruby"),
    ("e2e-smoke/java-gradle", "java_gradle"),
    ("e2e-smoke/java-maven", "java_maven"),
    ("e2e-apps/node-next", "node"),
    ("e2e-apps/python-fastapi", "python"),
    ("e2e-apps/prosper-chat", "node"),
    ("e2e-apps/nobi-owl-trader", "python"),
    ("e2e-apps/ruby-rails-web", "ruby"),
    ("e2e-apps/java-spring-web", "java_gradle"),
)

_FRAMEWORK_COMMAND_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bremix\b", re.IGNORECASE), "remix"),
    (re.compile(r"\bastro\b", re.IGNORECASE), "astro"),
    (re.compile(r"\bsolidstart\b|\bsolid-start\b", re.IGNORECASE), "solidstart"),
    (re.compile(r"\bqwik\b", re.IGNORECASE), "qwik"),
    (re.compile(r"\bhono\b", re.IGNORECASE), "hono"),
    (re.compile(r"\bkoa\b", re.IGNORECASE), "koa"),
    (re.compile(r"\badonis\b", re.IGNORECASE), "adonis"),
    (re.compile(r"\bredwoodsdk\b|\bredwood\b", re.IGNORECASE), "redwoodsdk"),
    (re.compile(r"\blit\b", re.IGNORECASE), "lit"),
    (re.compile(r"\balpine(?:-vite)?\b", re.IGNORECASE), "alpine_vite"),
    (re.compile(r"\bnext\s+(?:test|lint|build|dev)\b", re.IGNORECASE), "next"),
    (re.compile(r"\bnuxt\s+(?:test|build|dev)\b", re.IGNORECASE), "nuxt"),
    (re.compile(r"\bng\s+test\b|\bangular\b", re.IGNORECASE), "angular"),
    (re.compile(r"\bsvelte-kit\b|\bsveltekit\b", re.IGNORECASE), "sveltekit"),
    (re.compile(r"\bnest\s+(?:test|build|start)\b", re.IGNORECASE), "nest"),
    (re.compile(r"\bvitest\b", re.IGNORECASE), "vue_vite"),
    (re.compile(r"\bmanage\.py\s+test\b", re.IGNORECASE), "django"),
)

_FRAMEWORK_PATH_HINTS: tuple[tuple[str, str], ...] = (
    ("e2e-smoke/js-next", "next"),
    ("e2e-smoke/js-vue-vite", "vue_vite"),
    ("e2e-smoke/js-nuxt", "nuxt"),
    ("e2e-smoke/js-angular", "angular"),
    ("e2e-smoke/js-sveltekit", "sveltekit"),
    ("e2e-smoke/js-express", "express"),
    ("e2e-smoke/js-nest", "nest"),
    ("e2e-smoke/js-remix", "remix"),
    ("e2e-smoke/js-astro", "astro"),
    ("e2e-smoke/js-solidstart", "solidstart"),
    ("e2e-smoke/js-qwik", "qwik"),
    ("e2e-smoke/js-hono", "hono"),
    ("e2e-smoke/js-koa", "koa"),
    ("e2e-smoke/js-adonis", "adonis"),
    ("e2e-smoke/js-redwoodsdk", "redwoodsdk"),
    ("e2e-smoke/js-lit", "lit"),
    ("e2e-smoke/js-alpine-vite", "alpine_vite"),
    ("e2e-smoke/py-fastapi", "fastapi"),
    ("e2e-smoke/py-django", "django"),
    ("e2e-smoke/py-flask", "flask"),
    ("e2e-smoke/py-data-pandas", "pandas"),
    ("e2e-smoke/py-ml-sklearn", "sklearn"),
    ("e2e-apps/node-next", "next"),
    ("e2e-apps/python-fastapi", "fastapi"),
    ("e2e-apps/prosper-chat", "next"),
    ("e2e-apps/nobi-owl-trader", "fastapi"),
    ("e2e-apps/ruby-rails-web", "rails"),
    ("e2e-apps/java-spring-web", "spring"),
)


def compile_task_spec(*, issue_title: str, issue_body: str, language: str = "") -> HealerTaskSpec:
    issue_text = "\n".join(part for part in [issue_title.strip(), issue_body.strip()] if part).strip()
    task_kind_hint = _extract_task_kind_hint(issue_text=issue_text)
    explicit_paths = tuple(_explicit_paths(issue_text))
    explicit_directories = tuple(_explicit_directories(issue_text))
    validation_commands = _extract_validation_commands(issue_body)
    app_target = _extract_explicit_scalar_field(issue_body=issue_body, field_name="app_target")
    entry_url = _extract_explicit_scalar_field(issue_body=issue_body, field_name="entry_url")
    explicit_execution_root = _extract_explicit_scalar_field(issue_body=issue_body, field_name="execution_root")
    repro_steps = _extract_explicit_list_field(issue_body=issue_body, field_name="repro_steps")
    fixture_profile = _extract_explicit_scalar_field(issue_body=issue_body, field_name="fixture_profile")
    artifact_requirements = _extract_explicit_list_field(
        issue_body=issue_body,
        field_name="artifact_requirements",
    )
    runtime_profile = _extract_explicit_scalar_field(issue_body=issue_body, field_name="runtime_profile")
    judgment_required_conditions = _extract_explicit_list_field(
        issue_body=issue_body,
        field_name="judgment_required_conditions",
    )
    input_context_paths = _explicit_input_context_paths(issue_text=issue_text, explicit_paths=explicit_paths)
    output_targets = tuple(path for path in explicit_paths if path not in input_context_paths)
    if not input_context_paths and _treat_markdown_targets_as_input_hints(issue_text=issue_text, output_targets=output_targets):
        input_context_paths = tuple(path for path in output_targets if _is_artifact_path(path))
        output_targets = tuple(path for path in output_targets if path not in input_context_paths)
    task_kind = task_kind_hint or _classify_task_kind(issue_text=issue_text, output_targets=output_targets)
    inferred_targets = output_targets or _default_targets(issue_title=issue_title, task_kind=task_kind)
    tool_policy = "repo_plus_web" if task_kind == "research" else "repo_only"
    validation_profile = _validation_profile(task_kind=task_kind, output_targets=inferred_targets)
    inferred_execution_root = _infer_execution_root(
        explicit_execution_root=explicit_execution_root,
        explicit_directories=explicit_directories,
        output_targets=inferred_targets,
        validation_commands=validation_commands,
    )
    inferred_language = _infer_issue_language(
        issue_text=issue_text,
        output_targets=inferred_targets,
        execution_root=inferred_execution_root,
        validation_commands=validation_commands,
    )
    resolved_language = inferred_language or str(language or "").strip()
    language_source = "issue" if inferred_language else ("default" if resolved_language else "")
    inferred_framework = _infer_issue_framework(
        issue_text=issue_text,
        output_targets=inferred_targets,
        execution_root=inferred_execution_root,
        validation_commands=validation_commands,
    )
    framework_source = "issue" if inferred_framework else ""
    parse_confidence = _score_parse_confidence(
        task_kind_hint=task_kind_hint,
        explicit_paths=explicit_paths,
        validation_commands=validation_commands,
        execution_root=inferred_execution_root,
    )
    return HealerTaskSpec(
        task_kind=task_kind,
        output_mode="patch",
        output_targets=tuple(inferred_targets),
        tool_policy=tool_policy,
        validation_profile=validation_profile,
        input_context_paths=input_context_paths,
        language=resolved_language,
        language_source=language_source,
        framework=inferred_framework,
        framework_source=framework_source,
        execution_root=inferred_execution_root,
        validation_commands=validation_commands,
        app_target=app_target,
        entry_url=entry_url,
        repro_steps=repro_steps,
        fixture_profile=fixture_profile,
        artifact_requirements=artifact_requirements,
        runtime_profile=runtime_profile,
        judgment_required_conditions=judgment_required_conditions,
        parse_confidence=parse_confidence,
    )


def lint_issue_contract(
    *,
    issue_title: str,
    issue_body: str,
    task_spec: HealerTaskSpec,
    contract_mode: str,
    parse_confidence_threshold: float,
) -> IssueContractLint:
    reasons: list[str] = []
    threshold = max(0.0, min(1.0, float(parse_confidence_threshold)))
    if float(task_spec.parse_confidence) < threshold:
        reasons.append("low_confidence")

    requires_code_contract = str(task_spec.validation_profile or "") != "artifact_only"
    if str(contract_mode or "").strip().lower() == "strict" and requires_code_contract:
        if not task_spec.output_targets:
            reasons.append("missing_required_outputs")
        if not task_spec.validation_commands:
            reasons.append("missing_validation")

    suggested_execution_root = _suggest_execution_root(task_spec)
    if (
        requires_code_contract
        and not task_spec.execution_root
        and suggested_execution_root
        and len(_sandbox_roots_from_targets(task_spec.output_targets)) > 1
    ):
        reasons.append("ambiguous_execution_root")
    if requires_code_contract and _execution_root_conflicts_with_targets(task_spec):
        reasons.append("validation_root_mismatch")

    return IssueContractLint(
        reason_codes=tuple(reasons),
        suggested_execution_root=suggested_execution_root,
    )


def _score_parse_confidence(
    *,
    task_kind_hint: str | None,
    explicit_paths: tuple[str, ...],
    validation_commands: tuple[str, ...],
    execution_root: str,
) -> float:
    """Score how confidently the task spec was parsed from explicit issue signals.

    Range: 0.0 (all guessed) to 1.0 (all explicit).
    """
    score = 0.0
    if task_kind_hint:
        score += 0.3
    if explicit_paths:
        score += 0.3
    if validation_commands:
        score += 0.2
    if execution_root:
        score += 0.2
    return min(1.0, score)


def task_spec_to_prompt_block(spec: HealerTaskSpec) -> str:
    targets = ", ".join(spec.output_targets) if spec.output_targets else "(infer during execution)"
    input_context = ", ".join(spec.input_context_paths) if spec.input_context_paths else "(none)"
    lines = [
        "### Task Contract",
        f"- Task kind: {spec.task_kind}",
        f"- Output mode: {spec.output_mode}",
        f"- Output targets: {targets}",
        f"- Input context: {input_context}",
        f"- Tool policy: {spec.tool_policy}",
        f"- Validation profile: {spec.validation_profile}",
    ]
    if spec.app_target:
        lines.append(f"- App target: {spec.app_target}")
    if spec.entry_url:
        lines.append(f"- Entry URL: {spec.entry_url}")
    if spec.fixture_profile:
        lines.append(f"- Fixture profile: {spec.fixture_profile}")
    if spec.runtime_profile:
        lines.append(f"- Runtime profile: {spec.runtime_profile}")
    if spec.repro_steps:
        lines.append(f"- Repro steps: {' | '.join(spec.repro_steps)}")
    if spec.artifact_requirements:
        lines.append(f"- Artifact requirements: {' | '.join(spec.artifact_requirements)}")
    if spec.judgment_required_conditions:
        lines.append(
            f"- Judgment required conditions: {' | '.join(spec.judgment_required_conditions)}"
        )
    if spec.language:
        lines.append(f"- Language: {spec.language}")
    if spec.framework:
        lines.append(f"- Framework: {spec.framework}")
    if spec.execution_root:
        lines.append(f"- Execution root: {spec.execution_root}")
    if spec.validation_commands:
        lines.append(f"- Validation commands: {' | '.join(spec.validation_commands)}")
    if spec.validation_profile == "code_change" and spec.output_targets:
        if _uses_exact_output_target_policy(spec):
            lines.append(
                "- Output target policy: Named targets are the exact allowed edit set for this issue; do not modify nearby code, tests, or config unless the issue explicitly declares them."
            )
        else:
            lines.append(
                "- Output target policy: Named targets are anchors for the fix; additional nearby code, test, or config files may also be edited when required."
            )
    lines.extend(
        [
            f"- Success criteria: {_success_criteria(spec)}",
            f"- Failure handling: {_failure_handling(spec)}",
            f"- Default next action: {_default_next_action(spec)}",
        ]
    )
    return "\n".join(lines)


def _classify_task_kind(*, issue_text: str, output_targets: tuple[str, ...]) -> str:
    lowered = issue_text.lower()
    if output_targets and any(_is_code_path(path) for path in output_targets):
        natural_language = _natural_language_text(issue_text)
        if _BUILD_HINT_RE.search(natural_language):
            return "build"
        if _FIX_HINT_RE.search(natural_language):
            return "fix"
        if _EDIT_HINT_RE.search(natural_language):
            return "edit"
        return "edit"
    if _CODE_HINT_RE.search(lowered):
        return "build" if _BUILD_HINT_RE.search(_natural_language_text(issue_text)) else "fix"
    if _FIX_HINT_RE.search(lowered):
        return "fix"
    if _RESEARCH_HINT_RE.search(lowered):
        return "research"
    if _DOC_HINT_RE.search(lowered):
        return "docs"
    if _EDIT_HINT_RE.search(lowered):
        return "edit"
    return "fix"


def _extract_task_kind_hint(*, issue_text: str) -> str | None:
    for raw_line in issue_text.splitlines():
        match = _TASK_KIND_RE.search(raw_line.strip())
        if not match:
            continue
        candidate = match.group(1).lower()
        if candidate in {"edit", "fix", "build", "research", "docs"}:
            return candidate
    return None


def _default_targets(*, issue_title: str, task_kind: str) -> tuple[str, ...]:
    if task_kind in {"research", "docs"}:
        return (f"docs/{_slugify(issue_title or task_kind)}.md",)
    return ()


def _validation_profile(*, task_kind: str, output_targets: tuple[str, ...]) -> str:
    if output_targets and all(_is_artifact_path(path) for path in output_targets):
        return "artifact_only"
    if output_targets and any(_is_artifact_path(path) for path in output_targets) and any(_is_code_path(path) for path in output_targets):
        return "mixed"
    if task_kind in {"research", "docs"}:
        return "artifact_only"
    return "code_change"


def _uses_exact_output_target_policy(spec: HealerTaskSpec) -> bool:
    normalized_root = str(spec.execution_root or "").strip().strip("/")
    if normalized_root.startswith("e2e-smoke/") or normalized_root.startswith("e2e-apps/"):
        return True
    return False


def _explicit_paths(issue_text: str) -> list[str]:
    scored: dict[str, int] = {}
    order: list[str] = []
    seen: set[str] = set()
    current_heading = ""
    for raw_line in issue_text.splitlines():
        line = _strip_external_references(raw_line.strip())
        if _looks_like_heading(line):
            current_heading = line
        for match in _PATH_DIRECTIVE_RE.finditer(line):
            candidate = match.group("path").strip().lstrip("./")
            if not candidate:
                continue
            key = candidate.lower()
            if key not in seen:
                order.append(candidate)
                seen.add(key)
                scored[candidate] = 0
            scored[candidate] += _score_path_context(line=line, heading=current_heading)
        for match in _EXPLICIT_PATH_RE.finditer(line):
            candidate = match.group(1).strip().lstrip("./")
            if not candidate:
                continue
            key = candidate.lower()
            if key not in seen:
                order.append(candidate)
                seen.add(key)
                scored[candidate] = 0
            scored[candidate] += _score_path_context(line=line, heading=current_heading)
    rooted_paths = {path.lower() for path in order if "/" in path}
    prioritized = [
        path for path in order
        if scored.get(path, 0) >= 2 and not _looks_like_incidental_bare_path(path, rooted_paths=rooted_paths)
    ]
    if prioritized:
        return prioritized
    filtered = [path for path in order if not _looks_like_incidental_bare_path(path, rooted_paths=rooted_paths)]
    return filtered or order


def _explicit_directories(issue_text: str) -> list[str]:
    directories: list[str] = []
    seen: set[str] = set()
    for raw_line in issue_text.splitlines():
        line = _strip_external_references(raw_line.strip())
        for match in _DIRECTORY_RE.finditer(line):
            candidate = match.group(1).strip().lstrip("./").rstrip("/")
            if not candidate or "://" in candidate or "." in Path(candidate).name:
                continue
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            directories.append(candidate)
    return directories


def _explicit_input_context_paths(*, issue_text: str, explicit_paths: tuple[str, ...]) -> tuple[str, ...]:
    if not explicit_paths:
        return ()
    current_heading = ""
    identified: list[str] = []
    for raw_line in issue_text.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            current_heading = line
            continue
        context = " ".join(part for part in (current_heading, line) if part).strip()
        if not _INPUT_CONTEXT_RE.search(context):
            continue
        normalized_line = line.strip(" -*")
        for path in explicit_paths:
            if path in normalized_line and path not in identified:
                identified.append(path)
    return tuple(identified)


def _score_path_context(*, line: str, heading: str) -> int:
    score = 1
    if _OUTPUT_CONTEXT_RE.search(line) or _OUTPUT_CONTEXT_RE.search(heading):
        score += 2
    if _SCOPE_CONTEXT_RE.search(line) or _SCOPE_CONTEXT_RE.search(heading):
        score -= 1
    return score


def _treat_markdown_targets_as_input_hints(*, issue_text: str, output_targets: tuple[str, ...]) -> bool:
    if not output_targets:
        return False
    if not all(_is_artifact_path(path) for path in output_targets):
        return False
    lowered = issue_text.lower()
    if not _CODE_HINT_RE.search(lowered):
        return False
    if re.search(r"\b(?:input context|input spec|spec only|input only|not the output target)\b", lowered):
        return True
    if re.search(r"\bcode changes only\b", lowered):
        return True
    if re.search(r"\bdo not make doc(?:umentation)?-only edits\b", lowered):
        return True
    if re.search(r"\b(pass|passes|passing)\s+the\s+tests?\b", lowered):
        return True
    if re.search(r"\b(?:make sure|ensure|verify|confirm)\b.*\btests?\b.*\bpass(?:es|ing)?\b", lowered):
        return True
    if re.search(r"\b(?:code|implementation)\s+(?:upgrade|upgrades|change|changes)\b.*\btests?\b", lowered):
        return True
    if re.search(r"\b(apply|implement|fix|upgrade|refactor|change)\b.*\b(from|found in|based on|using)\b", lowered):
        return True
    return False


def _extract_validation_commands(issue_text: str) -> tuple[str, ...]:
    commands: list[str] = []
    seen: set[str] = set()
    for raw_line in issue_text.splitlines():
        line = raw_line.strip().strip(" -*`")
        if not line:
            continue
        match = _COMMAND_LINE_RE.search(line)
        if not match:
            continue
        command = " ".join(match.group(0).split()).strip()
        key = command.lower()
        if key in seen:
            continue
        seen.add(key)
        commands.append(command)
    return tuple(commands)


def _extract_explicit_scalar_field(*, issue_body: str, field_name: str) -> str:
    lines = issue_body.splitlines()
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        directive = _parse_directive_line(stripped)
        if directive and directive[0] == field_name:
            value = directive[1]
            if value:
                return value
            return _collect_scalar_section_value(lines=lines, start_index=index + 1)

        heading_name = _parse_heading_name(stripped)
        if heading_name == field_name:
            return _collect_scalar_section_value(lines=lines, start_index=index + 1)
    return ""


def _extract_explicit_list_field(*, issue_body: str, field_name: str) -> tuple[str, ...]:
    lines = issue_body.splitlines()
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        directive = _parse_directive_line(stripped)
        if directive and directive[0] == field_name:
            if directive[1]:
                return (directive[1],)
            return _collect_list_section_values(lines=lines, start_index=index + 1)

        heading_name = _parse_heading_name(stripped)
        if heading_name == field_name:
            return _collect_list_section_values(lines=lines, start_index=index + 1)
    return ()


def _collect_scalar_section_value(*, lines: list[str], start_index: int) -> str:
    for raw_line in lines[start_index:]:
        stripped = raw_line.strip()
        if not stripped:
            continue
        if _is_section_boundary(stripped):
            return ""
        return _clean_list_item(stripped)
    return ""


def _collect_list_section_values(*, lines: list[str], start_index: int) -> tuple[str, ...]:
    items: list[str] = []
    for raw_line in lines[start_index:]:
        stripped = raw_line.strip()
        if not stripped:
            if items:
                break
            continue
        if _is_section_boundary(stripped):
            break
        cleaned = _clean_list_item(stripped)
        if cleaned:
            items.append(cleaned)
    return tuple(items)


def _parse_directive_line(line: str) -> tuple[str, str] | None:
    if not line or line.startswith("#"):
        return None
    match = _DIRECTIVE_LINE_RE.match(line)
    if not match:
        return None
    normalized = _normalize_app_field_name(match.group("label"))
    if normalized not in _CONTRACT_FIELD_NAMES:
        return None
    return normalized, match.group("value").strip().strip("`")


def _parse_heading_name(line: str) -> str:
    if not line.startswith("#"):
        return ""
    heading = line.lstrip("#").strip()
    normalized = _normalize_app_field_name(heading)
    if normalized in _CONTRACT_FIELD_NAMES:
        return normalized
    return ""


def _is_section_boundary(line: str) -> bool:
    if not line:
        return False
    if line.startswith("#"):
        return True
    return _DIRECTIVE_LINE_RE.match(line) is not None


def _clean_list_item(line: str) -> str:
    return _LIST_ITEM_PREFIX_RE.sub("", line).strip()


def _normalize_app_field_name(label: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "_", str(label or "").strip().lower()).strip("_")
    return lowered


def _infer_execution_root(
    *,
    explicit_execution_root: str,
    explicit_directories: tuple[str, ...],
    output_targets: tuple[str, ...],
    validation_commands: tuple[str, ...],
) -> str:
    normalized_explicit_root = _normalize_contract_execution_root(explicit_execution_root)
    if normalized_explicit_root:
        return normalized_explicit_root

    for command in validation_commands:
        cd_root = _extract_cd_root(command)
        normalized_cd_root = _normalize_known_sandbox_root(cd_root)
        if normalized_cd_root:
            return normalized_cd_root
        if cd_root:
            return cd_root

    explicit_roots = {
        normalized
        for directory in explicit_directories
        if (normalized := _normalize_known_sandbox_root(directory))
    }
    if len(explicit_roots) == 1:
        return next(iter(explicit_roots))
    if len(explicit_roots) > 1:
        return ""

    sandbox_roots = {
        normalized
        for target in output_targets
        if (normalized := _normalize_known_sandbox_root(target))
    }
    if len(sandbox_roots) == 1:
        return next(iter(sandbox_roots))
    return ""


def _sandbox_roots_from_targets(output_targets: tuple[str, ...]) -> tuple[str, ...]:
    roots = {
        normalized
        for target in output_targets
        if (normalized := _normalize_known_sandbox_root(target))
    }
    return tuple(sorted(roots))


def _suggest_execution_root(task_spec: HealerTaskSpec) -> str:
    roots = _sandbox_roots_from_targets(task_spec.output_targets)
    normalized_execution_root = _normalize_known_sandbox_root(task_spec.execution_root)
    if normalized_execution_root and normalized_execution_root in roots:
        return normalized_execution_root
    if len(roots) == 1:
        return roots[0]
    if task_spec.execution_root:
        return str(task_spec.execution_root)
    if roots:
        return roots[0]
    return ""


def _execution_root_conflicts_with_targets(task_spec: HealerTaskSpec) -> bool:
    if not task_spec.execution_root:
        return False
    target_roots = _sandbox_roots_from_targets(task_spec.output_targets)
    if not target_roots:
        return False
    normalized_execution_root = _normalize_known_sandbox_root(task_spec.execution_root)
    if normalized_execution_root:
        return normalized_execution_root not in target_roots
    return str(task_spec.execution_root) not in target_roots


def _infer_issue_language(
    *,
    issue_text: str,
    output_targets: tuple[str, ...],
    execution_root: str,
    validation_commands: tuple[str, ...],
) -> str:
    for command in validation_commands:
        hinted = _language_from_command(command)
        if hinted:
            return hinted

    hinted = _language_from_path(execution_root)
    if hinted:
        return hinted

    for target in output_targets:
        hinted = _language_from_path(target)
        if hinted:
            return hinted
        suffix = Path(target).suffix.lower()
        if suffix == ".py":
            return "python"
        if suffix == ".rb":
            return "ruby"
        if suffix == ".go":
            return "go"
        if suffix == ".rs":
            return "rust"
        if suffix == ".swift":
            return "swift"
        if suffix == ".java":
            if "gradle" in issue_text.lower():
                return "java_gradle"
            if "maven" in issue_text.lower():
                return "java_maven"
        if suffix in {".js", ".jsx", ".ts", ".tsx"}:
            return "node"

    return _language_from_command(issue_text)


def _infer_issue_framework(
    *,
    issue_text: str,
    output_targets: tuple[str, ...],
    execution_root: str,
    validation_commands: tuple[str, ...],
) -> str:
    for command in validation_commands:
        hinted = _framework_from_command(command)
        if hinted:
            return hinted

    hinted = _framework_from_path(execution_root)
    if hinted:
        return hinted

    for target in output_targets:
        hinted = _framework_from_path(target)
        if hinted:
            return hinted

    return _framework_from_command(issue_text)


def _extract_cd_root(command: str) -> str:
    match = re.search(r"\bcd\s+([^\n&|;]+?)\s*&&", command, re.IGNORECASE)
    if not match:
        return ""
    candidate = match.group(1).strip().strip("'\"").lstrip("./").rstrip("/")
    return candidate


def _normalize_known_sandbox_root(path: str) -> str:
    normalized = str(path or "").strip().strip("'\"").lstrip("./").rstrip("/")
    if not normalized:
        return ""
    parts = Path(normalized).parts
    if len(parts) >= 2 and parts[0] in {"e2e-smoke", "e2e-apps"}:
        return Path(parts[0], parts[1]).as_posix()
    if normalized.startswith("e2e-smoke/") or normalized.startswith("e2e-apps/"):
        return normalized
    return ""


def _normalize_contract_execution_root(path: str) -> str:
    normalized = _normalize_known_sandbox_root(path)
    if normalized:
        return normalized
    return str(path or "").strip().strip("'\"").lstrip("./").rstrip("/")


def _language_from_command(text: str) -> str:
    for pattern, language in _LANGUAGE_COMMAND_HINTS:
        if pattern.search(text or ""):
            return language
    return ""


def _language_from_path(path: str) -> str:
    lowered = str(path or "").strip().strip("/").lower()
    for prefix, language in _LANGUAGE_PATH_HINTS:
        if lowered.startswith(prefix):
            return language
    return ""


def _framework_from_command(text: str) -> str:
    source = str(text or "")
    for pattern, framework in _FRAMEWORK_COMMAND_HINTS:
        if pattern.search(source):
            return framework
    return ""


def _framework_from_path(path: str) -> str:
    lowered = str(path or "").strip().strip("/").lower()
    for prefix, framework in _FRAMEWORK_PATH_HINTS:
        if lowered.startswith(prefix):
            return framework
    return ""


def _is_artifact_path(path: str) -> bool:
    lowered = path.lower()
    suffix = Path(path).suffix.lower()
    return lowered.startswith("docs/") or suffix in {".md", ".mdx", ".rst", ".txt"}


def _is_code_path(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".html",
        ".go", ".rs", ".java", ".kt", ".rb",
        ".c", ".cpp", ".h", ".hpp",
        ".swift", ".scala", ".sql",
    }


def _strip_external_references(text: str) -> str:
    return _URL_RE.sub(" ", text or "")


def _looks_like_heading(line: str) -> bool:
    stripped = str(line or "").strip()
    if not stripped:
        return False
    return stripped.startswith("#") or stripped.endswith(":")


def _looks_like_incidental_bare_path(path: str, *, rooted_paths: set[str]) -> bool:
    candidate = str(path or "").strip().lstrip("./")
    if not candidate or "/" in candidate:
        return False
    lowered = candidate.lower()
    if any(rooted.endswith(f"/{lowered}") for rooted in rooted_paths):
        return True
    suffix = Path(candidate).suffix.lower()
    if suffix not in {".js", ".jsx", ".ts", ".tsx", ".swift", ".py", ".rb", ".go", ".rs"}:
        return False
    stem = Path(candidate).stem
    # Human-readable product names like "Next.js" should not become file targets
    # when the issue also provides rooted repo paths.
    return bool(rooted_paths) and any(char.isupper() for char in stem)


def _natural_language_text(issue_text: str) -> str:
    text = _strip_external_references(issue_text)
    text = _EXPLICIT_PATH_RE.sub(" ", text)
    text = _DIRECTORY_RE.sub(" ", text)
    text = _COMMAND_LINE_RE.sub(" ", text)
    return text.lower()


def _slugify(value: str) -> str:
    lowered = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return lowered or "artifact"


def _success_criteria(spec: HealerTaskSpec) -> str:
    if spec.validation_profile == "artifact_only":
        return "Write the requested artifact content directly into the target files."
    if spec.validation_profile == "mixed":
        return "Produce the requested artifact targets and include the required non-doc code changes."
    return "Stage a production-safe code patch and keep the requested validation passing."


def _failure_handling(spec: HealerTaskSpec) -> str:
    if spec.validation_profile == "artifact_only":
        return "If a direct edit is not possible, return file content in explicit fenced blocks for each target."
    return "If a direct edit is not possible, return exactly one valid unified diff fenced block."


def _default_next_action(spec: HealerTaskSpec) -> str:
    if spec.tool_policy == "repo_plus_web":
        return "Gather the required facts, then write the target files."
    if spec.validation_profile == "artifact_only":
        return "Write the requested artifact content into the named files."
    return "Implement the smallest safe repo patch that satisfies the issue."
