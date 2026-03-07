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


_EXPLICIT_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:\.?/)?(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:md|mdx|rst|txt|py|yaml|yml|json|toml|ini|cfg|conf|js|ts|tsx|jsx|css|html))"
)
_CODE_HINT_RE = re.compile(r"\b(build|feature|implement|fix|bug|app|todo app|api|service|refactor|code)\b", re.IGNORECASE)
_RESEARCH_HINT_RE = re.compile(r"\b(research|investigate|analyze|compare|survey|look up|best ways|best practices)\b", re.IGNORECASE)
_DOC_HINT_RE = re.compile(r"\b(plan|spec|doc|docs|readme|guide|proposal|notes|write up|document)\b", re.IGNORECASE)
_EDIT_HINT_RE = re.compile(r"\b(edit|revise|update|rewrite|expand|tighten|clarify)\b", re.IGNORECASE)
_OUTPUT_CONTEXT_RE = re.compile(r"\b(output|deliverable|required output|required outputs|create|write|generate|report)\b", re.IGNORECASE)
_SCOPE_CONTEXT_RE = re.compile(r"\b(scope|review|analyze|inspect|input|source files?)\b", re.IGNORECASE)
_TASK_KIND_RE = re.compile(r"^\s*[-*]?\s*task\s*kind:\s*([a-zA-Z]+)\s*$")


def compile_task_spec(*, issue_title: str, issue_body: str) -> HealerTaskSpec:
    issue_text = "\n".join(part for part in [issue_title.strip(), issue_body.strip()] if part).strip()
    output_targets = tuple(_explicit_output_targets(issue_text))
    task_kind_hint = _extract_task_kind_hint(issue_text=issue_text)
    input_context_paths: tuple[str, ...] = ()
    if _treat_markdown_targets_as_input_hints(issue_text=issue_text, output_targets=output_targets):
        input_context_paths = tuple(path for path in output_targets if _is_artifact_path(path))
        output_targets = ()
    task_kind = task_kind_hint or _classify_task_kind(issue_text=issue_text, output_targets=output_targets)
    inferred_targets = output_targets or _default_targets(issue_title=issue_title, task_kind=task_kind)
    tool_policy = "repo_plus_web" if task_kind == "research" else "repo_only"
    validation_profile = _validation_profile(task_kind=task_kind, output_targets=inferred_targets)
    return HealerTaskSpec(
        task_kind=task_kind,
        output_mode="patch",
        output_targets=tuple(inferred_targets),
        tool_policy=tool_policy,
        validation_profile=validation_profile,
        input_context_paths=input_context_paths,
    )


def task_spec_to_prompt_block(spec: HealerTaskSpec) -> str:
    targets = ", ".join(spec.output_targets) if spec.output_targets else "(infer during execution)"
    input_context = ", ".join(spec.input_context_paths) if spec.input_context_paths else "(none)"
    return "\n".join(
        [
            "### Task Contract",
            f"- Task kind: {spec.task_kind}",
            f"- Output mode: {spec.output_mode}",
            f"- Output targets: {targets}",
            f"- Input context: {input_context}",
            f"- Tool policy: {spec.tool_policy}",
            f"- Validation profile: {spec.validation_profile}",
        ]
    )


def _classify_task_kind(*, issue_text: str, output_targets: tuple[str, ...]) -> str:
    lowered = issue_text.lower()
    if _CODE_HINT_RE.search(lowered):
        return "build" if re.search(r"\b(build|feature|app|implement)\b", lowered) else "fix"
    if _RESEARCH_HINT_RE.search(lowered):
        return "research"
    if output_targets and any(_is_code_path(path) for path in output_targets):
        return "edit"
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


def _explicit_output_targets(issue_text: str) -> list[str]:
    scored: dict[str, int] = {}
    order: list[str] = []
    current_heading = ""
    for raw_line in issue_text.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            current_heading = line
        for match in _EXPLICIT_PATH_RE.finditer(line):
            candidate = match.group(1).strip().lstrip("./")
            if not candidate:
                continue
            if candidate not in scored:
                order.append(candidate)
                scored[candidate] = 0
            scored[candidate] += _score_path_context(line=line, heading=current_heading)
    prioritized = [path for path in order if scored.get(path, 0) >= 2]
    return prioritized or order


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


def _is_artifact_path(path: str) -> bool:
    lowered = path.lower()
    suffix = Path(path).suffix.lower()
    return lowered.startswith("docs/") or suffix in {".md", ".mdx", ".rst", ".txt"}


def _is_code_path(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in {".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".html"}


def _slugify(value: str) -> str:
    lowered = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return lowered or "artifact"
