# Healing State Machine

This doc is the runtime decision map from ready issue to retry, PR, human stop, or resolution.

## Canonical Anchors

- [src/flow_healer/healer_loop.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_loop.py)
- [src/flow_healer/healer_runner.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_runner.py)
- [src/flow_healer/healer_verifier.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_verifier.py)
- [src/flow_healer/healer_reconciler.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_reconciler.py)
- [src/flow_healer/healer_tracker.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_tracker.py)
- [tests/test_healer_loop.py](/Users/cypher-server/Documents/code/flow-healer/tests/test_healer_loop.py)

## High-Level Flow

```text
ready issue
  -> claim
  -> parse and lint task contract
  -> connector/runtime preflight
  -> run attempt
  -> validation and evidence checks
  -> verifier
  -> PR open/update or human stop
  -> PR reconciliation, CI follow-up, approval follow-up
  -> resolved / blocked / failed / queued retry
```

## Tick-Level Ordering

Each worker tick is not just "claim an issue." Before claims, the loop also performs housekeeping such as:

- reconciler cleanup and stale lease recovery
- PR outcome reconciliation
- CI status refresh for open PRs
- requeue of deterministic remote CI failures
- approved-PR resume checks
- scan scheduling when enabled

If the repo is paused, in circuit-breaker cooldown, or under infra pause, the loop records runtime status and skips new claims.

## Claim And Parse

An issue becomes claimable only if it satisfies label and trust rules. Once claimed:

- the issue body is compiled into a `HealerTaskSpec`
- issue-contract lint checks can route it to `needs_clarification`
- execution root, language, framework, validation commands, and browser/evidence fields are resolved

Weak contracts should stop here, not after speculative edits.

## Preflight

Before the runner burns attempt time, the loop probes:

- connector availability
- selected backend health
- language/runtime prerequisites
- app runtime profile availability for browser-backed issues

A broken connector or runtime can fail before mutation and may trigger normal backoff or infra pause handling depending on failure class.

## Runner Attempt

The runner may:

- stage a repo patch
- boot an app runtime
- execute browser repro steps
- capture failure and resolution artifacts
- validate the workspace locally and optionally in Docker
- widen scope only for documented baseline-validation cases

Failure classes at this stage include code, scope, contract, connector, runtime, and evidence failures.

## Validation And Evidence Gates

After patch generation, Flow Healer enforces:

- task-scoped validation commands or language strategy defaults
- max failed test allowance
- browser repro behavior
- artifact completeness

Important outcomes include:

- `tests_failed`
- `browser_repro_failed`
- `artifact_publish_failed`
- `browser_artifact_capture_failed`
- `baseline_validation_blocked`

Browser tasks can pass without reproduction only when `browser_repro_mode` is `allow_success`.

## Verification

The verifier is a second connector pass that returns:

- `pass`
- `soft_fail`
- `hard_fail`

Verifier failures can still route differently depending on policy:

- retry
- judgment-required stop
- PR suppression

Artifact-only docs/config changes may short-circuit verification deterministically when they stay within the allowed file families.

## PR Creation And PR States

When validation and verification are good enough, Flow Healer opens or updates the managed PR and records one of these operator-visible states:

- `pr_open`
- `pr_pending_approval`
- `resolved`

`pr_pending_approval` is used when approval gating is enabled and the PR is waiting on the configured approval label.

## Open-PR Reconciliation

Open PRs are not terminal. The loop keeps reconciling them:

- refreshes PR state and mergeability
- stores GitHub CI summaries on the issue and latest attempt
- auto-resumes approved pending PRs
- handles merge conflicts and stuck PRs
- detects merged PRs and closes the linked issue

### Remote CI Failure Handling

If an open PR has remote CI failures in deterministic retriable buckets:

- `lint`
- `setup`
- `test`
- `typecheck`

the loop requeues the issue on the same managed branch with CI failure feedback added to `feedback_context`.

It does not blindly rerun CI. It queues another repair attempt.

If the failure is only transient infra, the issue stays `pr_open`. If the retry budget is exhausted, the PR stays open and the issue records `ci_retry_exhausted`.

## Conflict And Stuck-PR Handling

For conflicted PRs, the loop can:

- attempt conflict resolution
- close and requeue the PR if auto-requeue is enabled
- block the issue when conflict retries are exhausted

For non-mergeable PRs that stay stuck too long, the loop can close and requeue the issue after the configured timeout.

## Retry, Quarantine, And Infra Pause

Failures do not all retry the same way.

### Automatic requeue

Some failure classes always requeue with backoff, especially:

- infrastructure failures
- lock conflicts
- trust-exempt failures
- no-workspace-change classes that should not count against issue trust

### Adaptive retry

Normal code or contract failures can requeue while under budget with backoff and feedback hints.

### Retry exhausted

When attempt count reaches the retry budget, the issue moves to `failed` instead of retrying indefinitely.

### Quarantine

Repeated deterministic failure fingerprints can block the issue instead of looping forever.

### Infra pause

Some infrastructure failures activate a repo-level pause using:

- `healer_infra_failure_streak`
- `healer_infra_pause_until`
- `healer_infra_pause_reason`

While that pause is active, the worker still ticks and performs housekeeping but skips new claims.

## Human-Decision Stops

The main deliberate human stops are:

- `needs_clarification`
- `judgment_required`
- `blocked` conflict or baseline-validation states
- `pr_pending_approval`

These states mean automation should explain the next decision instead of retrying blindly.

## Where Outcome Data Lives

- current issue snapshot: `healer_issues`
- attempt history: `healer_attempts`
- runtime markers: `kv_state`
- locks: `healer_locks`
- control-plane actions: `control_commands`

The attempt row is the history. The issue row is the latest visible state.

## Testing Expectations

When state-machine behavior changes, run:

```bash
pytest tests/test_healer_loop.py -v
pytest tests/test_healer_runner.py -v
pytest tests/test_service.py -v
```

Add focused reconciler or tracker tests when the change affects PR or CI follow-up behavior.

## Relationship To Other Docs

- [docs/runtime-state.md](/Users/cypher-server/Documents/code/flow-healer/docs/runtime-state.md) defines the durable state model
- [docs/issue-contracts.md](/Users/cypher-server/Documents/code/flow-healer/docs/issue-contracts.md) defines task-spec inputs
- [docs/evidence-contract.md](/Users/cypher-server/Documents/code/flow-healer/docs/evidence-contract.md) defines artifact gates
