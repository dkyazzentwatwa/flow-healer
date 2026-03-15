# Flow Healer MVP Design — 2026-03-14

## Product Positioning

**Headline:**
> Flow Healer opens draft PRs for flaky tests and safe repo maintenance issues — with validation evidence attached — so you can review, approve, or retry in one place.

## Target User

Solo developers and OSS maintainers running their own repos. Not fleet operators. Not enterprise. Someone who gets paged at 2am about a flaky CI step and wants it handled while they sleep.

## Distribution

Open source. Self-hosted. `pip install flow-healer`.

## The Job

1. Watches issues labeled `healer:ready`
2. Proposes a fix via configured connector (default: codex CLI)
3. Runs validation, attaches evidence (commands run, pass/fail, diff summary)
4. Opens a draft PR with human-readable summary
5. Operator reviews, approves, or retries from TUI or CLI

## What Is NOT Claimed at MVP

- Broad refactors
- Unsafe fixes (all fixes are auditable, all state is local SQLite)
- Multi-repo fleet management (supported but not the headline)
- Magic

## The Two Issue Classes

### Class A — Flaky Test Repair

**Accepted when:**
- Issue title/label indicates a flaky or intermittently failing test
- Output targets are inside test files only (no production code changes)
- Validation command explicitly provided or detectable
- Max diff: small (single test file or test helper)

**Rejected:** tests failing due to production bugs → `needs_clarification`

### Class B — Safe CI / Config / Doc Fixes

**Accepted when:**
- Files in: `.github/`, `Makefile`, `pyproject.toml`, `requirements*.txt`, `*.md` docs, `setup.cfg`, `tox.ini`
- No production source files touched
- Issue body has explicit `Required code outputs` section
- Max diff: small (1–3 files)

**Rejected:** dependency bumps requiring code changes, CI restructuring

### Shared Rejection Criteria

- No `Required code outputs` → `needs_clarification`
- No validation commands and none detectable → `needs_clarification`
- Output targets include `src/` for non-test files → rejected with reason
- Diff exceeds size limit → `judgment_required`

## Operator-Visible Failure Taxonomy

All internal failure codes map to one of six operator-visible reasons:

| Operator Label | Meaning |
|---|---|
| `validation_failed` | Fix was applied but tests/CI did not pass |
| `diff_too_large` | Proposed diff exceeded size limit |
| `scope_violation` | Fix touched files outside allowed scope |
| `no_confident_fix` | Connector could not produce a high-confidence fix |
| `repo_blocked` | Circuit breaker open or repo paused |
| `review_required` | AI reviewer flagged the fix for human attention |

## Evidence Bundle (per run)

Every run produces one consistent operator-facing object. Minimum fields:

- `issue_id`, `repo`, `summary` — what was attempted
- `files_changed`, `diff_summary` — scope of the fix
- `validation_commands` — what was run
- `validation_passed` — true/false per command
- `risk_level` — `low` / `medium` / `high`
- `failure_reason` — one of the six operator-visible codes (if failed)

## Success Metrics

- **Approval-ready PR rate:** ≥ 60% of accepted issues produce a draft PR operator can approve without modification
- **Operator review time:** ≤ 2 minutes per item from TUI
- **Onboarding time:** First-time user gets their first result in ≤ 15 minutes

## Launch Checklist

- [ ] `pip install flow-healer` + `flow-healer doctor` returns green on a fresh setup
- [ ] Demo repo has ≥ 3 successful draft PRs per class (Class A and Class B)
- [ ] Demo screen recording: issue → TUI → draft PR → operator approves — under 3 minutes
