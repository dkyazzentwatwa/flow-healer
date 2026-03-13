# Evidence Contract

This doc defines what counts as complete evidence for browser-backed and artifact-publishing work.

## Canonical Anchors

- [src/flow_healer/browser_harness.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/browser_harness.py)
- [src/flow_healer/healer_runner.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_runner.py)
- [src/flow_healer/healer_tracker.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_tracker.py)
- [docs/harness-reliability-runbook.md](/Users/cypher-server/Documents/code/flow-healer/docs/harness-reliability-runbook.md)
- [docs/harness-smoke-checklist.md](/Users/cypher-server/Documents/code/flow-healer/docs/harness-smoke-checklist.md)

## Evidence Completeness

For a browser-backed issue, evidence is complete only when the required artifacts exist for the relevant phase and can be validated or published.

Typical required evidence:

- failure screenshot or equivalent pre-fix evidence when the task expects failure reproduction
- resolution screenshot
- console log
- network log
- `_meta.json` when artifacts are published to the artifact branch

Some constructive browser tasks with `browser_repro_mode: allow_success` may skip failure-as-bug evidence, but they still need the declared artifact outputs.

## Artifact Types

Supported publishable artifact families include:

- screenshots and images
- console logs
- network logs
- text or JSON diagnostics

The tracker publishes them under:

- `flow-healer/evidence/issue-<issue_id>/<run_key>/...`

with a companion:

- `_meta.json`

## Failure vs Resolution Expectations

- `require_failure` tasks: failure evidence shows the pre-fix problem before mutation, then resolution evidence shows the repaired state.
- `allow_success` tasks: the initial journey may already pass, but declared evidence is still required for completion or for browser-evidence-only acceptance.

## Naming And Storage

- keep generated browser evidence outside the git worktree during capture
- publish only supported artifact types
- treat the artifact branch as durable operator evidence, not source code
- preserve `_meta.json` because it defines artifact run metadata and retention

## When Missing Evidence Blocks Completion

An issue is blocked when:

- required screenshots are missing
- console or network logs were explicitly required but not captured
- publish succeeded partially and the required bundle is incomplete
- artifact validation or retention metadata cannot be produced

In those cases, Flow Healer should fail with an evidence-related class instead of pretending the issue is complete.

## Browser Harness Expectations

The browser harness contract is:

- run the declared repro steps
- capture deterministic artifacts for the relevant phase
- record the final URL and transcript
- return evidence that the runner and tracker can validate

Lane-specific expectations live in the lane guides and [docs/fixture-profile-guidance.md](/Users/cypher-server/Documents/code/flow-healer/docs/fixture-profile-guidance.md).

## Relationship To Other Docs

- use [docs/issue-contracts.md](/Users/cypher-server/Documents/code/flow-healer/docs/issue-contracts.md) for `artifact_requirements`
- use [docs/dashboard.md](/Users/cypher-server/Documents/code/flow-healer/docs/dashboard.md) for the artifact browser UI
- use [docs/healing-state-machine.md](/Users/cypher-server/Documents/code/flow-healer/docs/healing-state-machine.md) for when evidence is required in the runtime flow
