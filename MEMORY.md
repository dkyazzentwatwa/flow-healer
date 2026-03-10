# MEMORY.md

## Purpose

This file captures durable repo-specific guidance that should help future Flow Healer runs stay aligned with how this repository works.

Use this file for stable patterns and invariants.
Do not use it as a per-issue log, retry diary, or dump of transient failures. Dynamic run history belongs in the SQLite lesson store.

## How This Complements SQL Memory

- `MEMORY.md` is for human-curated, slow-changing guidance.
- SQLite `healer_lessons` are for attempt-derived lessons such as successful fix patterns, guardrails, and frequently reused scope hints.

If guidance is still likely to matter a month from now, it may belong here.
If it is tied to one issue, one failure, or one retry chain, it belongs in SQL memory instead.

## Current Project Shape

Core Python code lives in `src/flow_healer/`.

High-value modules:

- `src/flow_healer/healer_task_spec.py`: issue-body parsing into task kind, output targets, input-only context, language hints, execution root, and validation commands
- `src/flow_healer/healer_runner.py`: proposer prompt assembly, execution-root resolution, output staging, and validation flow
- `src/flow_healer/healer_memory.py`: retrieval and recording of prior-attempt lessons
- `src/flow_healer/language_detector.py`: repo-level language detection
- `src/flow_healer/language_strategies.py`: per-language validation strategies
- `src/flow_healer/service.py`: multi-repo orchestration and runtime status
- `src/flow_healer/store.py`: SQLite persistence

Source-of-truth tests for this area:

- `tests/test_healer_task_spec.py`
- `tests/test_healer_runner.py`
- `tests/test_healer_memory.py`
- `tests/e2e/test_flow_healer_e2e.py`

## Repo Truths

- Keep the existing `codex exec` flow unless there is a strong reason to change connector shape.
- Current work is focused on prompt reliability and issue-driven execution routing, not connector redesign.
- Issue-scoped language hints, execution roots, and validation commands can override repo-wide defaults when the issue body is explicit.
- Input-only context files should be treated as reference material, not output targets.
- Docs- or artifact-only behavior should not leak into code-change tasks.

## Working Heuristics

- Prefer the smallest safe patch over broad cleanup.
- Tighten prompt sections by clarifying and deduplicating; do not add prompt bulk unless it clearly improves behavior.
- When task routing is ambiguous, trust explicit issue-body validation commands and required code outputs before repo-wide assumptions.
- Keep mixed-language sandbox behavior issue-scoped.
- Preserve existing verified behavior when retrying after test or verifier failures.
- If tests define the behavior, update tests and implementation together.

## Invariants To Protect

- Issue parsing must continue to extract:
  - task kind
  - output targets
  - input-only context
  - execution root
  - language hints
  - validation commands
- Prompt assembly should keep clear section ordering and task-specific execution rules.
- Retry prompts should remain focused on the last concrete failure mode instead of expanding scope.
- Memory retrieval should favor relevant scope overlap and recency, and should avoid contaminating code tasks with artifact-only lessons.

## Preferred Verification

Start with the smallest targeted tests that cover the change:

- `pytest tests/test_healer_task_spec.py -v`
- `pytest tests/test_healer_runner.py -v`
- `pytest tests/test_healer_memory.py -v`
- `pytest tests/e2e/test_flow_healer_e2e.py -k mixed_repo_sandbox -v`

Run broader `pytest` only after the targeted slice is green.

## Common Failure Patterns

- Prompt regressions that drift back toward exploratory summaries instead of direct repo edits
- Wrong execution root in mixed-language or sandbox issues
- Validation commands inferred too broadly instead of staying issue-scoped
- Artifact-only lessons or heuristics bleeding into code-change tasks
- Retrying with a wider patch instead of addressing the last concrete failure signal

## What Does Not Belong Here

- Per-issue notes
- Raw command output
- One-off debugging observations
- Retry-by-retry timelines
- Temporary TODO lists
- Lessons already captured automatically in SQLite

## Maintenance Rule

Keep this file short, opinionated, and current.
If a line would not help a future healer run make a better decision, remove it.
