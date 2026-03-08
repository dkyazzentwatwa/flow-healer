from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .healer_locks import diff_paths_to_lock_keys

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "if",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}
_NEGATIVE_FAILURES = {
    "empty_diff",
    "malformed_diff",
    "no_patch",
    "no_workspace_change",
    "patch_apply_failed",
    "diff_limit_exceeded",
    "tests_failed",
    "verifier_failed",
    "lock_conflict",
    "lock_upgrade_conflict",
    "connector_unavailable",
    "connector_runtime_error",
}


@dataclass(slots=True, frozen=True)
class RetrievedHealerLesson:
    lesson_id: str
    lesson_kind: str
    lesson_text: str
    test_hint: str
    score: int


class HealerMemoryService:
    def __init__(self, store: Any, *, enabled: bool) -> None:
        self.store = store
        self.enabled = bool(enabled)

    def maybe_record_lesson(
        self,
        *,
        issue: Any,
        attempt_id: str,
        final_state: str,
        predicted_lock_set: list[str],
        actual_diff_set: list[str],
        test_summary: dict[str, Any],
        verifier_summary: dict[str, Any],
        failure_class: str,
        failure_reason: str,
    ) -> None:
        if not self.enabled or not hasattr(self.store, "create_healer_lesson"):
            return

        outcome = self._derive_outcome(final_state)
        if not outcome:
            return
        if outcome == "success" and not bool(verifier_summary.get("passed")):
            return
        if (
            outcome == "failure"
            and failure_class not in _NEGATIVE_FAILURES
            and not str(failure_class or "").startswith("no_workspace_change:")
        ):
            return

        lesson_kind = "successful_fix" if outcome == "success" else "guardrail"
        scope_key = self._choose_scope_key(predicted_lock_set, actual_diff_set)
        title = str(getattr(issue, "title", "") or "").strip()
        body = str(getattr(issue, "body", "") or "").strip()
        problem_summary = title[:160]
        test_hint = self._build_test_hint(test_summary)
        guardrail = {
            "predicted_lock_set": list(predicted_lock_set or []),
            "actual_diff_set": list(actual_diff_set or []),
            "actual_lock_set": diff_paths_to_lock_keys(actual_diff_set or []),
            "failure_class": failure_class,
            "failure_reason": (failure_reason or "")[:200],
        }
        test_output_excerpt = str(test_summary.get("output_tail", "") or "").strip()[:200]
        sandbox_scoped = (
            str(test_summary.get("execution_root_source") or "").strip().lower() == "issue"
            and _is_sandbox_execution_root(str(test_summary.get("execution_root") or "").strip())
        )
        lesson_text = self._build_lesson_text(
            outcome=outcome,
            title=title,
            scope_key=scope_key,
            failure_class=failure_class,
            failure_reason=failure_reason,
            verifier_summary=str(verifier_summary.get("summary") or ""),
            test_hint=test_hint,
            test_output_excerpt=test_output_excerpt,
            sandbox_scoped=sandbox_scoped,
        )
        fingerprint_basis = "|".join(
            [
                lesson_kind,
                scope_key,
                failure_class or outcome,
                title.lower()[:120],
                body.lower()[:120],
            ]
        )
        fingerprint = hashlib.sha256(fingerprint_basis.encode("utf-8")).hexdigest()
        confidence = 85 if outcome == "success" else 65

        self.store.create_healer_lesson(
            lesson_id=f"hl_{uuid4().hex[:12]}",
            issue_id=str(getattr(issue, "issue_id", "") or ""),
            attempt_id=attempt_id,
            lesson_kind=lesson_kind,
            scope_key=scope_key,
            fingerprint=fingerprint,
            problem_summary=problem_summary,
            lesson_text=lesson_text,
            test_hint=test_hint,
            guardrail=guardrail,
            confidence=confidence,
            outcome=outcome,
        )

    def build_prompt_context(
        self,
        *,
        issue_text: str,
        predicted_lock_set: list[str],
        last_failure_class: str = "",
        task_kind: str = "",
        validation_profile: str = "",
        output_targets: list[str] | tuple[str, ...] | None = None,
        issue_id: str = "",
        limit: int = 3,
    ) -> str:
        lessons = self.retrieve_lessons(
            issue_text=issue_text,
            predicted_lock_set=predicted_lock_set,
            last_failure_class=last_failure_class,
            task_kind=task_kind,
            validation_profile=validation_profile,
            output_targets=output_targets,
            issue_id=issue_id,
            limit=limit,
        )
        if not lessons:
            return ""
        if hasattr(self.store, "mark_healer_lessons_used"):
            self.store.mark_healer_lessons_used([lesson.lesson_id for lesson in lessons])
        lines = ["## Prior healer lessons for this area"]
        follow_lines: list[str] = []
        avoid_lines: list[str] = []
        for lesson in lessons:
            prefix = "FOLLOW" if lesson.lesson_kind == "successful_fix" else "AVOID"
            entry = f"- **{prefix}:** {lesson.lesson_text}"
            if lesson.test_hint:
                entry += f"\n  Test hint: {lesson.test_hint}"
            if prefix == "FOLLOW":
                follow_lines.append(entry)
            else:
                avoid_lines.append(entry)
        lines.extend(follow_lines)
        lines.extend(avoid_lines)
        return "\n".join(lines)

    def retrieve_lessons(
        self,
        *,
        issue_text: str,
        predicted_lock_set: list[str],
        last_failure_class: str = "",
        task_kind: str = "",
        validation_profile: str = "",
        output_targets: list[str] | tuple[str, ...] | None = None,
        issue_id: str = "",
        limit: int = 3,
    ) -> list[RetrievedHealerLesson]:
        if not self.enabled or not hasattr(self.store, "list_healer_lessons"):
            return []
        rows = self.store.list_healer_lessons(limit=300)
        if not rows:
            return []

        issue_terms = self._tokenize(issue_text)
        predicted_keys = set(predicted_lock_set or [])
        scored: list[RetrievedHealerLesson] = []
        for row in rows:
            scope_key = str(row.get("scope_key") or "").strip()
            if _should_skip_lesson_for_task(
                scope_key=scope_key,
                task_kind=task_kind,
                validation_profile=validation_profile,
                output_targets=output_targets or (),
            ):
                continue
            guardrail = row.get("guardrail") if isinstance(row.get("guardrail"), dict) else {}
            lesson_keys = set()
            for key in guardrail.get("predicted_lock_set") or []:
                if isinstance(key, str) and key.strip():
                    lesson_keys.add(key.strip())
            for key in guardrail.get("actual_lock_set") or []:
                if isinstance(key, str) and key.strip():
                    lesson_keys.add(key.strip())
            score = 0
            overlap_count = 0
            if predicted_keys and lesson_keys:
                overlap = predicted_keys & lesson_keys
                overlap_count = len(overlap)
                if overlap:
                    score += min(24, 12 * len(overlap))
                elif "repo:*" in predicted_keys and row.get("scope_key") == "repo:*":
                    score += 4
            if scope_key and scope_key in predicted_keys:
                score += 8
            lesson_failure_class = str(guardrail.get("failure_class") or "").strip()
            if last_failure_class and lesson_failure_class == last_failure_class:
                score += 6

            haystack_terms = self._tokenize(
                "\n".join(
                    [
                        str(row.get("problem_summary") or ""),
                        str(row.get("lesson_text") or ""),
                        str(row.get("test_hint") or ""),
                    ]
                )
            )
            term_overlap = len(issue_terms & haystack_terms)
            score += min(5, term_overlap)
            score += int(row.get("confidence") or 0) // 20
            if str(row.get("outcome") or "") == "success":
                score += 2
            if issue_id and str(row.get("issue_id") or "") == issue_id:
                score += 10
            created_at = str(row.get("created_at") or "").strip()
            if created_at:
                try:
                    created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if created_dt.tzinfo is None:
                        created_dt = created_dt.replace(tzinfo=UTC)
                    lesson_age_days = (datetime.now(UTC) - created_dt).days
                    if lesson_age_days > 30:
                        score = int(score * 0.7)
                    elif lesson_age_days > 7:
                        score = int(score * 0.85)
                except (TypeError, ValueError):
                    pass

            if predicted_keys and overlap_count == 0 and term_overlap < 2:
                continue
            if score <= 0:
                continue
            scored.append(
                RetrievedHealerLesson(
                    lesson_id=str(row.get("lesson_id") or ""),
                    lesson_kind=str(row.get("lesson_kind") or ""),
                    lesson_text=str(row.get("lesson_text") or "").strip(),
                    test_hint=str(row.get("test_hint") or "").strip(),
                    score=score,
                )
            )

        scored.sort(key=lambda lesson: (-lesson.score, lesson.lesson_kind, lesson.lesson_id))
        return scored[: max(1, int(limit))]

    @staticmethod
    def _derive_outcome(final_state: str) -> str:
        normalized = (final_state or "").strip().lower()
        if normalized in {"pr_open", "resolved", "pr_pending_approval"}:
            return "success"
        if normalized != "failed":
            return ""
        return "failure"

    @staticmethod
    def _choose_scope_key(predicted_lock_set: list[str], actual_diff_set: list[str]) -> str:
        actual_keys = [key for key in diff_paths_to_lock_keys(actual_diff_set or []) if key != "repo:*"]
        if actual_keys:
            return sorted(actual_keys)[0]
        predicted_keys = [key for key in (predicted_lock_set or []) if key != "repo:*"]
        if predicted_keys:
            return sorted(predicted_keys)[0]
        return "repo:*"

    @staticmethod
    def _build_test_hint(test_summary: dict[str, Any]) -> str:
        execution_root = str(test_summary.get("execution_root") or "").strip()
        execution_root_source = str(test_summary.get("execution_root_source") or "").strip().lower()
        sandbox_scoped = execution_root_source == "issue" and _is_sandbox_execution_root(execution_root)
        targeted_tests = test_summary.get("targeted_tests") or []
        if isinstance(targeted_tests, list) and targeted_tests:
            rendered = ", ".join(str(item) for item in targeted_tests[:3])
            if sandbox_scoped:
                return f"Run the targeted sandbox validation from `{execution_root}` first: {rendered}"
            return f"Run targeted pytest first: {rendered}"
        if test_summary:
            if sandbox_scoped:
                return f"Re-run only the issue-scoped validation commands from `{execution_root}` before publishing."
            return "Re-run targeted and full pytest gates before publishing."
        return ""

    @staticmethod
    def _build_lesson_text(
        *,
        outcome: str,
        title: str,
        scope_key: str,
        failure_class: str,
        failure_reason: str,
        verifier_summary: str,
        test_hint: str,
        test_output_excerpt: str = "",
        sandbox_scoped: bool = False,
    ) -> str:
        short_title = title[:100] or "similar healer issues"
        if outcome == "success":
            tail = f" Keep the change scoped to `{scope_key}` and preserve current behavior."
            if verifier_summary:
                tail = f" Keep the change scoped to `{scope_key}` and preserve the verified behavior."
            return f"Successful fixes for '{short_title}' stayed narrow around `{scope_key}`.{tail}"

        failure_map = {
            "no_patch": "Return only a valid unified diff fenced block.",
            "no_workspace_change": "Ensure the run actually edits files and stages a scoped artifact diff.",
            "patch_apply_failed": "Do not assume stale file paths or hunk context; align the diff to the current tree.",
            "diff_limit_exceeded": "Keep the patch narrowly scoped and avoid broad refactors.",
            "tests_failed": (
                "Preserve existing behavior and satisfy the issue-scoped sandbox validation gates."
                if sandbox_scoped
                else "Preserve existing behavior and satisfy both targeted and full pytest gates."
            ),
            "verifier_failed": "Address the root cause instead of silencing symptoms or only making tests pass.",
            "lock_conflict": "Avoid overlapping edits outside the predicted scope to reduce contention.",
            "lock_upgrade_conflict": "Avoid expanding the patch into new paths after the initial scoped plan.",
            "connector_unavailable": "Check worker runtime environment and ensure Codex CLI is available before consuming retries.",
            "connector_runtime_error": "Treat connector runtime crashes as infra failures and capture raw error output for diagnosis.",
        }
        normalized_failure_class = "no_workspace_change" if str(failure_class or "").startswith("no_workspace_change:") else failure_class
        mapped = failure_map.get(normalized_failure_class, "Keep the patch conservative and easy to verify.")
        reason = (failure_reason or "").strip()
        if reason:
            mapped = f"{mapped} Recent failure signal: {reason[:120]}."
        if failure_class == "tests_failed" and test_output_excerpt:
            mapped = f"{mapped} Test output: {test_output_excerpt[:200]}"
        if failure_class == "verifier_failed" and verifier_summary:
            mapped = f"{mapped} Verifier note: {verifier_summary[:200]}"
        if test_hint:
            mapped = f"{mapped} {test_hint}"
        return f"Guardrail from '{short_title}': {mapped}"

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        words = {
            token
            for token in re.findall(r"[A-Za-z0-9_./:-]+", (text or "").lower())
            if len(token) >= 3 and token not in _STOPWORDS
        }
        return words


def _should_skip_lesson_for_task(
    *,
    scope_key: str,
    task_kind: str,
    validation_profile: str,
    output_targets: list[str] | tuple[str, ...],
) -> bool:
    normalized_scope = (scope_key or "").strip()
    if not normalized_scope.startswith("path:"):
        return False
    if validation_profile != "code_change":
        return False
    normalized_kind = (task_kind or "").strip().lower()
    if normalized_kind not in {"build", "fix", "edit"}:
        return False
    if output_targets and not all(_is_artifact_path(path) for path in output_targets):
        return False
    rel_path = normalized_scope.removeprefix("path:").strip()
    return _is_artifact_path(rel_path)


def _is_sandbox_execution_root(root: str) -> bool:
    normalized = str(root or "").strip().strip("/")
    return normalized.startswith("e2e-smoke/") or normalized.startswith("e2e-apps/")


def _is_artifact_path(path: str) -> bool:
    lowered = str(path or "").strip().lower()
    suffix = Path(lowered).suffix
    return lowered.startswith("docs/") or suffix in {".md", ".mdx", ".rst", ".txt"}
