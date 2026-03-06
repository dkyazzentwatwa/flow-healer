# Skills Upgrade Suggestions

The repo-local `/skills` set is already pointed in the right direction. The current five skills cover the main operator loop:

- `flow-healer-local-validation`
- `flow-healer-preflight`
- `flow-healer-live-smoke`
- `flow-healer-triage`
- `flow-healer-pr-followup`

That gives Flow Healer a workable path from safe local checks to live smoke, failure diagnosis, and PR reuse. The next upgrade should keep that narrow, deterministic style while closing a few gaps around handoffs, artifact contracts, and deeper runtime diagnostics.

## What Is Already Strong

- Each skill is scoped to one stage of the healer lifecycle instead of trying to be a catch-all.
- Four of the five skills already anchor to small scripts, which keeps execution deterministic.
- The sequence is easy to understand: validate locally, preflight, smoke, triage failures, then follow up on an existing PR.
- The references files are lightweight and useful; they add guardrails without bloating the skill entrypoints.

## Main Improvement Areas

### 1. Standardize the contract for every skill

The skills are similar in tone, but they do not yet expose the same operator contract.

Suggested additions to every `SKILL.md`:

- `Inputs`: required arguments, optional arguments, and where they come from
- `Outputs`: exact artifact or report produced
- `Success Criteria`: what counts as pass, partial pass, or hard stop
- `Next Step`: which skill should usually follow
- `Failure Handling`: retryable versus non-retryable outcomes

Why this matters:

- `preflight` and `live-smoke` are clearly related, but the handoff is still implied rather than explicit.
- `triage` returns a diagnosis bucket, but the default next move still lives in operator judgment.
- `pr-followup` has good stop conditions, but not a crisp definition of "safe to resume."

### 2. Make script output schemas part of the skills

The scripts mostly emit structured JSON, but the skills do not tell the operator which fields matter first.

Concrete gaps:

- `flow-healer-local-validation` returns `checks`, but the skill does not explain which failures block live work versus which are informational.
- `flow-healer-preflight` emits `required_checks`, `context`, `samples`, and `notes`, but the skill only describes them at a high level.
- `flow-healer-triage` returns `issue`, `latest_attempt`, and `diagnosis`, but the meaning of the evidence is not formalized in the skill.
- `flow-healer-pr-followup` returns `issue` plus `attempts`, but the resume criteria are still partially inferred.
- `flow-healer-live-smoke` depends on a generated bundle and a runbook checklist, but the artifact set could be more explicit in the main skill file.

Recommended upgrade:

- Add a short "Key Output Fields" section to each skill that names the first fields an operator or agent should inspect.

### 3. Strengthen transitions between skills

The current skills are good as individual islands. The next step is to make them behave more like an operating graph.

Recommended handoff rules:

- `local-validation` should say when to stop locally, when to escalate to `preflight`, and when to jump directly to `live-smoke`.
- `preflight` should classify outcomes as:
  - safe for live smoke
  - safe only for local work
  - blocked pending remediation
- `triage` should map each diagnosis bucket to a default next skill.
- `pr-followup` should state when follow-up should fall back to `triage` instead of attempting resume.

Suggested bucket-to-next-step mapping:

- `operator_or_environment` -> fix environment, rerun `flow-healer-preflight`
- `repo_fixture_or_setup` -> repair local repo/test setup, rerun `flow-healer-local-validation`
- `connector_or_patch_generation` -> run a dedicated connector-debug skill
- `product_bug` -> capture evidence with an incident skill
- `external_service_or_github` -> retry later with a clear operator note

### 4. Expand `flow-healer-local-validation`

This skill is currently the thinnest compared with how important it is.

Observed behavior today:

- It runs `pytest -q`.
- It optionally runs a dry-run scan only if `.flow-healer-smoke-config.yaml` exists.

That is useful, but it leaves out a lot of healer-specific confidence checks.

Recommended upgrades:

- Add validation modes such as `fast`, `core`, and `full`.
- Add targeted checks for:
  - `tests/test_healer_loop.py`
  - `tests/test_healer_runner.py`
  - `tests/test_codex_cli_connector.py`
  - `tests/test_skill_assets.py`
  - `flow-healer doctor`
  - `flow-healer scan --dry-run`
- Report a `category` and `duration_seconds` per check so the skill can recommend the next action more reliably.

### 5. Expand `flow-healer-preflight` for runtime drift

`preflight` is already a good repo readiness check, but its focus is still mostly git, auth, Docker, and SQLite state.

Observed behavior today:

- Checks GitHub auth
- Verifies git worktree state
- Verifies clean working tree
- Verifies `.venv`
- Verifies Docker
- Samples open issues and PRs
- Optionally inspects SQLite issue counts

Recommended upgrades:

- Verify the configured connector command resolves and is executable.
- Verify the state DB path is writable, not just present.
- Confirm the configured default branch matches remote reality.
- Check that the CLI resolves from the intended interpreter, not just that `.venv/bin/python` exists.
- Detect environment drift that would break launchd or non-interactive runs.

This is a high-value area because Flow Healer has core modules like `codex_cli_connector.py`, `healer_runner.py`, and `service.py`, but the skill surface does not yet inspect connector readiness directly.

### 6. Broaden `flow-healer-live-smoke`

The live smoke bundle generator is solid and deterministic, but the templates are still narrow.

Observed behavior today:

- `docs_scaffold`
- `docs_followup_note`

That is a good starting point, but it only proves a subset of low-risk mutation paths.

Recommended upgrades:

- Add more smoke-safe templates such as:
  - `single_markdown_edit`
  - `comment_only_followup`
  - `tests_fixture_note`
  - `config_comment_annotation`
- Add a `risk class` note for each template.
- Add guidance on when docs-only smoke is not representative enough.
- Promote the artifact checklist from the runbook into the main skill file so fewer steps depend on opening a second document.

### 7. Deepen `flow-healer-triage`

The current triage script is intentionally lightweight, but it is one of the best places to invest next.

Observed behavior today:

- Reads the issue row
- Reads the latest attempt
- Classifies into one of five buckets

Recommended upgrades:

- Include previous attempts for the same issue, not just the latest one.
- Surface recurring failure patterns such as repeated `no_patch` or `patch_apply_failed`.
- Include verifier and test summaries when present.
- Capture lock prediction versus actual lock behavior when relevant.
- Add a compact "incident packet" mode for product bugs.

This would turn triage from a simple classifier into a reusable incident-analysis tool.

### 8. Clarify `flow-healer-pr-followup`

This skill is careful, which is good, but it could be more explicit about what makes reuse safe.

Recommended upgrades:

- Define exact resume criteria:
  - issue state
  - PR state
  - presence of new external feedback
  - branch/worktree metadata alignment
  - no active running attempt
- Define explicit "recreate instead of resume" conditions.
- Add a short checklist for feedback ingestion across issue comments, PR comments, and review comments.
- Explain how to handle stale branches, force-pushes, and closed/reopened PRs.

## New Skills Worth Adding

### 1. `flow-healer-connector-debug`

Purpose:

- Diagnose `no_patch`, malformed diff output, patch-apply failures, verifier/proposer contract mismatches, and connector command resolution problems.

Why it should exist:

- `flow-healer-triage` already has a `connector_or_patch_generation` bucket.
- There is no dedicated skill for digging into that bucket once it is identified.

Suggested scope:

- Validate connector command resolution
- Re-run the connector against a fixed prompt fixture
- Check output mode expectations against actual output
- Detect malformed diff fences, empty patch bodies, and invalid JSON payloads
- Compare proposer/verifier output contracts

Best trigger examples:

- "why did the healer produce no patch"
- "debug connector output"
- "investigate patch_apply_failed"

### 2. `flow-healer-incident-capture`

Purpose:

- Turn a suspicious failure into a compact, reusable incident packet.

Why it should exist:

- `triage` can identify a likely product bug, but it does not yet package the evidence into an artifact ready for escalation.

Suggested scope:

- Gather issue metadata
- Gather recent attempts
- Capture failure class and reason
- Include verifier and test summaries
- Include reproduction hints and relevant state rows
- Produce a markdown report suitable for `docs/` or GitHub issue creation

Best trigger examples:

- "capture this healer incident"
- "prepare a product bug packet"
- "collect evidence for escalation"

### 3. `flow-healer-state-repair`

Purpose:

- Inspect and safely repair stuck or inconsistent healer state in SQLite after interrupted runs.

Why it should exist:

- The current skills can detect state problems, but none are dedicated to resolving them safely.

Suggested scope:

- Inspect `running`, `queued`, backoff, and PR-linked issue states
- Detect orphaned attempts or mismatched issue/attempt state
- Recommend safe manual remediation steps before another live run
- Optionally generate a before/after repair plan without mutating automatically

Best trigger examples:

- "why is this issue stuck in running"
- "repair the healer state db"
- "inspect queue drift after interruption"

### 4. `flow-healer-review-readiness`

Purpose:

- Decide whether a healer-generated PR is ready for human review or needs another local iteration first.

Why it should exist:

- Today the repo can validate, smoke, and follow up, but there is no focused skill for the review boundary itself.

Suggested scope:

- Summarize verifier output and test results
- Check patch scope and changed-file risk
- Confirm branch/PR metadata is coherent
- Flag when follow-up should wait for a human instead of auto-resume

Best trigger examples:

- "is this healer PR ready for review"
- "should we requeue this PR or wait"
- "summarize review readiness"

## Highest-Leverage Next Steps

If only a few upgrades are taken first, the best sequence is:

1. Expand `flow-healer-local-validation` so it validates healer-specific behavior rather than only broad repo health.
2. Add `flow-healer-connector-debug`, because connector and patch-generation failures are already a named triage category.
3. Expand `flow-healer-preflight` to catch runtime drift before live execution.
4. Add `flow-healer-incident-capture` so product-bug classification leads directly to a reusable artifact.

## Summary

The current skills are already a good foundation because they are narrow, deterministic, and aligned with real operator workflows. The biggest win now is not adding a large number of overlapping skills. It is tightening the contracts of the existing five skills, making handoffs explicit, and adding a few missing lifecycle skills around connector debugging, state repair, and incident capture.
