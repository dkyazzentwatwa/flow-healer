# Skills Upgrade Suggestions

The repo-local `skills/` set is already well shaped for the Flow Healer lifecycle:

- `flow-healer-local-validation`
- `flow-healer-preflight`
- `flow-healer-live-smoke`
- `flow-healer-triage`
- `flow-healer-pr-followup`

The next round of improvement should stay narrow: tighten the contract of these five skills, make handoffs explicit, and add only the missing runtime-debugging skills that current failure buckets already imply.

## What To Preserve

- Keep one skill per operator stage.
- Keep script-driven, deterministic workflows.
- Keep the skill surface repo-local and low ceremony.
- Keep live GitHub work behind explicit preflight and stop conditions.

## Cross-Skill Fixes

Every `SKILL.md` should expose the same operator contract. Today the skills are directionally consistent, but the contract is uneven and forces operators to infer too much from nearby docs or script output.

Add these sections to all five skills:

- `Inputs`: required flags, optional flags, defaults, and any path assumptions.
- `Outputs`: exact artifact paths or top-level JSON fields the script returns.
- `Key Output Fields`: the first fields an operator should read.
- `Success Criteria`: what counts as pass, partial pass, or hard stop.
- `Failure Handling`: retryable versus non-retryable outcomes.
- `Next Step`: the default downstream skill or operator action.

Apply these shared writing rules:

- Put stop conditions in every skill, even if the current workflow implies them.
- Name the script output fields exactly as emitted by the script.
- Prefer direct action wording such as "stop", "rerun", "handoff", or "repair first".
- Keep each skill self-sufficient for the first pass; do not require opening a reference doc just to understand the default path.

## Skill-Specific Fixes

### `flow-healer-local-validation`

Current gap:

- The skill is too thin relative to how important the local gate is.
- It says to treat non-zero checks as a no-go, but it does not explain the check schema or local-only versus live-readiness outcomes.

Recommended fixes:

- Add `Inputs` for repo root, optional mode, and optional smoke-config dependency.
- Add `Outputs` and `Key Output Fields` for `repo_root` and `checks`.
- Document each check entry as `name`, `cmd`, `exit_code`, `output_tail`, and any future `category` or `duration_seconds` fields if the script is expanded.
- Add `Success Criteria` with three outcomes:
  - local repo healthy
  - healthy enough for preflight
  - blocked pending remediation
- Add `Next Step` guidance:
  - stop after local validation for plumbing-only work
  - hand off to `flow-healer-preflight` before live mutation
  - skip live smoke unless the request truly needs live GitHub validation
- Surface the decision boundary from `references/modes.md` directly in the skill instead of leaving it buried in the reference.

### `flow-healer-preflight`

Current gap:

- The skill covers the broad environment gate well, but it does not make runtime drift checks or output interpretation explicit enough.

Recommended fixes:

- Add `Inputs` for `repo-path`, `repo-slug`, and optional `state-db-path`.
- Add `Outputs` and `Key Output Fields` for:
  - `required_checks`
  - `context`
  - `samples`
  - `notes`
- Add `Success Criteria` buckets:
  - safe for live smoke
  - safe only for local work
  - blocked pending remediation
- Expand stop conditions to mention:
  - auth failure
  - dirty worktree when the run expects cleanliness
  - missing `.venv`
  - missing Docker when relevant gates require it
  - unexpected active healer state
- Add a short `Failure Handling` section that points operators to `references/remediation.md` only after the primary failure is named in the skill itself.
- Add a `Next Step` section that defaults to `flow-healer-live-smoke` only when all required checks pass.

### `flow-healer-live-smoke`

Current gap:

- The workflow is clear, but template scope, bundle outputs, and artifact checklist are still too implicit.

Recommended fixes:

- Add `Inputs` for repo path, repo slug, repo name, output dir, and template.
- Add `Outputs` and `Key Output Fields` for:
  - `template`
  - `connector_path`
  - `config_path`
  - `state_root`
- Move the core artifact checklist from `references/runbook.md` into the skill:
  - issue id
  - PR id
  - branch name
  - attempt state
  - verifier summary
  - test summary
- Add `Success Criteria` for a smoke run that completes with coherent issue, PR, and verifier artifacts.
- Add `Failure Handling` that explicitly routes suspicious failures to `flow-healer-triage` instead of retrying.
- Document the current templates as smoke-safe and note that docs-only smoke is useful for plumbing but not fully representative of broader patch behavior.

### `flow-healer-triage`

Current gap:

- The skill explains the diagnosis buckets, but not the default action to take after classification.

Recommended fixes:

- Add `Inputs` for DB path and issue id.
- Add `Outputs` and `Key Output Fields` for:
  - `issue`
  - `latest_attempt`
  - `diagnosis`
- Add `Success Criteria` that defines a successful run as one that produces a diagnosis plus an operator-ready next action.
- Add `Failure Handling` for incomplete or ambiguous issue state.
- Add explicit bucket-to-action mapping:
  - `operator_or_environment` -> repair environment and rerun `flow-healer-preflight`
  - `repo_fixture_or_setup` -> repair repo/setup and rerun `flow-healer-local-validation`
  - `connector_or_patch_generation` -> hand off to a connector-debug skill
  - `product_bug` -> capture evidence and escalate
  - `external_service_or_github` -> retry later with operator note
- Add `Next Step` language so the operator does not have to translate the bucket manually.

### `flow-healer-pr-followup`

Current gap:

- The skill is cautious, but the reuse contract is still partly hidden in `references/followup_rules.md`.

Recommended fixes:

- Add `Inputs` for DB path and issue id.
- Add `Outputs` and `Key Output Fields` for:
  - `issue`
  - `attempts`
- Add `Success Criteria` that defines when reuse is safe.
- Add `Failure Handling` that distinguishes:
  - no new feedback
  - already ingested feedback
  - active running state
  - branch or worktree mismatch
- Add a short safe-to-resume checklist directly in the skill:
  - issue still active
  - PR still relevant
  - new external feedback exists
  - no active running attempt
  - stored branch/worktree metadata still matches reality
- Add `Next Step` guidance that falls back to `flow-healer-triage` when reuse is unsafe or ambiguous.

## Missing Skills To Add

Only add skills that close gaps already visible in the current lifecycle.

### `flow-healer-connector-debug`

Why it belongs:

- `flow-healer-triage` already names `connector_or_patch_generation` as a first-class diagnosis bucket.
- There is no dedicated skill for `no_patch`, malformed diff output, patch-apply failures, or connector command resolution drift.

Recommended scope:

- Validate connector command resolution.
- Re-run the connector against a fixed prompt fixture.
- Detect malformed diff fences, empty patch bodies, and invalid JSON payloads.
- Compare proposer and verifier output contracts.

### `flow-healer-incident-capture`

Why it belongs:

- `flow-healer-triage` can identify likely product bugs, but there is no skill that packages evidence into a reusable escalation artifact.

Recommended scope:

- Gather issue metadata and recent attempts.
- Include failure class, failure reason, verifier summary, and test summary.
- Capture reproduction hints and relevant state rows.
- Produce a markdown incident packet ready for `docs/` or GitHub issue creation.

### `flow-healer-state-repair`

Why it belongs:

- Current skills can notice broken or stuck SQLite state, but none are dedicated to safely analyzing and repairing it.

Recommended scope:

- Inspect `running`, `queued`, backoff, and PR-linked issue states.
- Detect orphaned attempts or mismatched issue and attempt state.
- Recommend safe manual remediation before another live run.
- Prefer repair planning over automatic mutation.

## Highest-Leverage Order

If only a few changes land first, do them in this order:

1. Tighten the shared contract across all five existing `SKILL.md` files.
2. Expand `flow-healer-local-validation` so it reports healer-specific readiness instead of only broad repo health.
3. Expand `flow-healer-preflight` so it catches runtime drift before live execution.
4. Add `flow-healer-connector-debug` because triage already points to that missing branch.
5. Deepen `flow-healer-triage` so it returns explicit next-step guidance.

## Acceptance Bar

Treat the upgrade as complete when:

- Each existing skill can be executed without opening a second doc for the default path.
- Every skill names its inputs, outputs, stop conditions, and next step.
- `local-validation`, `preflight`, `live-smoke`, `triage`, and `pr-followup` form an explicit operator graph.
- The missing `connector_or_patch_generation` path is covered by a dedicated skill instead of an implied manual investigation.
