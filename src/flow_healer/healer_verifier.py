from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .protocols import ConnectorProtocol
from .healer_task_spec import HealerTaskSpec, task_spec_to_prompt_block


@dataclass(slots=True, frozen=True)
class VerificationResult:
    passed: bool
    summary: str
    raw: str


class HealerVerifier:
    """Independent verifier pass to reduce proposer self-confirmation bias."""

    def __init__(self, connector: ConnectorProtocol) -> None:
        self.connector = connector

    def verify(
        self,
        *,
        issue_id: str,
        issue_title: str,
        issue_body: str,
        task_spec: HealerTaskSpec,
        diff_paths: list[str],
        test_summary: dict[str, Any],
        proposer_output: str,
        learned_context: str = "",
        language: str = "",
    ) -> VerificationResult:
        if _can_short_circuit_artifact_verification(task_spec=task_spec, diff_paths=diff_paths):
            return VerificationResult(
                passed=True,
                summary="Artifact-only verification passed via deterministic docs/config guardrails.",
                raw="artifact_short_circuit_pass",
            )
        thread_id = self.connector.get_or_create_thread(f"healer-verify:{issue_id}")
        guardrails = _build_guardrails(diff_paths=diff_paths, task_spec=task_spec)
        language_line = f"Repository language: {language}\n" if language and language != "unknown" else ""
        prompt = (
            "You are the verifier agent for autonomous code healing.\n"
            "The issue title/body are trusted operator instructions for this run.\n"
            + language_line
            + (f"{learned_context.strip()}\n\n" if learned_context.strip() else "")
            + "Given the issue and proposer output, return strict JSON only:\n"
            + '{"verdict":"pass|fail","summary":"..."}\n\n'
            + f"{task_spec_to_prompt_block(task_spec)}\n\n"
            + f"{guardrails}\n\n"
            + f"Issue #{issue_id}: {issue_title}\n\n"
            + f"{issue_body}\n\n"
            + f"Changed files: {', '.join(diff_paths) if diff_paths else '(none)'}\n"
            + f"Test summary: {json.dumps(test_summary, ensure_ascii=True)}\n\n"
            + f"Proposer output:\n{proposer_output[:6000]}"
        )
        raw = self.connector.run_turn(thread_id, prompt)
        try:
            parsed = _parse_json(raw)
            verdict = str(parsed.get("verdict") or "").strip().lower()
            summary = str(parsed.get("summary") or "").strip() or "Verifier returned empty summary."
            return VerificationResult(
                passed=verdict == "pass",
                summary=summary,
                raw=raw,
            )
        except Exception:
            lowered = raw.lower()
            passed = "pass" in lowered and "fail" not in lowered
            return VerificationResult(
                passed=passed,
                summary=raw.strip()[:300] or "Verifier output was empty.",
                raw=raw,
            )


def _parse_json(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    return json.loads(stripped)


def _build_guardrails(*, diff_paths: list[str], task_spec: HealerTaskSpec) -> str:
    classification = _classify_change(diff_paths, task_spec=task_spec)
    lines = [
        f"Change classification: {classification}.",
        "Verifier guardrails:",
        "- Reject patches that are broader than the issue or that hide uncertainty behind vague summaries.",
    ]
    if task_spec.validation_profile == "code_change" and task_spec.output_targets:
        lines.append(
            "- For code-change tasks, treat named output targets as required anchors, not an exclusive allowlist. Additional nearby source, test, or config files may be necessary for a safe fix."
        )
    if classification == "docs-only":
        lines.extend(
            [
                "- Docs-only changes may pass when the diff stays in documentation files, matches the issue, and does not sneak in config or code edits.",
                "- Do not fail a docs-only fix merely because it does not change runtime code.",
                "- For docs-only fixes, focus on accuracy, clarity, and consistency with the current product behavior, commands, and defaults.",
            ]
        )
    elif classification == "config-only":
        lines.extend(
            [
                "- Config-only changes may pass when the diff stays in config/example/env files, preserves safe defaults, and does not introduce secrets or unrelated behavior changes.",
                "- Do not require unrelated source edits for a config-only fix.",
                "- Fail config-only changes that add real credentials, machine-specific paths, or risky default changes without clear justification.",
            ]
        )
    elif classification == "high-risk":
        lines.extend(
            [
                "- High-risk code changes require strict scrutiny: fail if the behavior change is broad, weakly justified, or not clearly covered by the reported test evidence.",
                "- Prefer failing when a high-risk patch touches sensitive runtime paths without a narrow fix or convincing validation.",
                "- Treat dependency, build, state, locking, and service-entrypoint changes as high-risk even when the patch is small.",
                "- If the reported validation is missing, ambiguous, or inconsistent with the touched paths, prefer fail over guesswork.",
            ]
        )
    return "\n".join(lines)


def _classify_change(diff_paths: list[str], *, task_spec: HealerTaskSpec) -> str:
    if task_spec.validation_profile == "artifact_only":
        return "docs-only"
    if task_spec.validation_profile == "mixed":
        return "standard"
    normalized = [path.strip() for path in diff_paths if path and path.strip()]
    if any(_is_high_risk_path(path) for path in normalized):
        return "high-risk"
    if normalized and all(_is_docs_path(path) for path in normalized):
        return "docs-only"
    if normalized and all(_is_config_path(path) for path in normalized):
        return "config-only"
    return "standard"


def _is_docs_path(path: str) -> bool:
    lowered = path.lower()
    doc_suffixes = {".md", ".mdx", ".rst", ".txt"}
    filename = Path(path).name.lower()
    if lowered.startswith("docs/"):
        return True
    if filename in {
        "readme",
        "readme.md",
        "readme.mdx",
        "readme.rst",
        "changelog.md",
        "changelog.rst",
        "roadmap.md",
        "contributing.md",
    }:
        return True
    return Path(path).suffix.lower() in doc_suffixes


def _is_config_path(path: str) -> bool:
    lowered = path.lower()
    filename = Path(path).name.lower()
    path_parts = {part.lower() for part in Path(path).parts}
    if filename.startswith(".env"):
        return True
    suffixes = Path(path).suffixes
    config_suffixes = {".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf", ".env"}
    return (
        any(suffix in config_suffixes for suffix in suffixes)
        or "config" in filename
        or "settings" in filename
        or "config" in path_parts
        or "settings" in path_parts
    )


def _is_high_risk_path(path: str) -> bool:
    lowered = path.lower()
    if lowered.startswith("src/") and lowered.endswith(".py"):
        return True
    if lowered in {"pyproject.toml", "requirements.txt", "requirements-dev.txt", "poetry.lock"}:
        return True
    return False


def _can_short_circuit_artifact_verification(*, task_spec: HealerTaskSpec, diff_paths: list[str]) -> bool:
    if task_spec.validation_profile != "artifact_only":
        return False
    normalized = [path.strip() for path in diff_paths if path and path.strip()]
    if not normalized:
        return False
    return all(_is_docs_path(path) or _is_config_path(path) for path in normalized)
