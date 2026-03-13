# Runtime State

This doc explains the durable state model behind Flow Healer.

## Canonical Anchors

- [src/flow_healer/store.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/store.py)
- [src/flow_healer/repo_state_migration.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/repo_state_migration.py)
- [src/flow_healer/healer_locks.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_locks.py)
- [src/flow_healer/healer_loop.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_loop.py)

## What SQLite Stores

The main state buckets are:

- `kv_state`: repo-level counters, flags, timestamps, cached health, and runtime markers
- `healer_issues`: queue entries, current state, branch/workspace pointers, retry metadata, scope keys, and PR linkage
- `healer_attempts`: every attempt record with state, summary, artifacts, and failure details
- `healer_lessons`: reusable learning captured from prior attempts
- `healer_locks`: active path and scope locks
- `healer_events`: structured event log for runtime activity
- `healer_runtime`: runtime status snapshots
- `healer_mutation_log`: idempotent mutation tracking
- `control_commands`: operator-issued commands
- `scan_runs` and `scan_findings`: deterministic scan history

## Attempt Lifecycle

At a high level:

1. issue is queued or claimed
2. attempt row is created
3. runtime moves through proposal, validation, verification, and PR actions
4. attempt is finalized as success, failed, blocked, interrupted, or clarification-required
5. issue row is updated to the next visible queue state

The attempt row is the historical truth. The issue row is the current-state snapshot.

## Queue State Semantics

Common issue states include:

- `queued`
- `claimed`
- `running`
- `verify_pending`
- `pr_open`
- `pr_pending_approval`
- `blocked`
- `needs_clarification`
- `failed`
- `resolved`
- `archived`

Do not treat these as interchangeable. `needs_clarification` means the next step is a human contract decision, not another automatic retry.

## Lock Semantics

Locks exist to keep overlapping issues from mutating the same scope at the same time.

- prediction locks are acquired before work starts
- diff locks are upgraded after real changed paths are known
- locks expire via lease timestamps and are reaped by cleanup paths

If lock behavior changes, update this doc and the state-machine doc together.

## Retry, Quarantine, And Judgment State

State is not just queue depth. Flow Healer also persists:

- retry counters and backoff windows
- failure fingerprints
- infra pause markers
- stale runtime-profile markers
- swarm and reconciliation markers
- judgment-required payloads and clarification stops

These markers are operator-facing and should be treated as part of the runtime contract.

## Safe Reset / Delete Guidance

Generally safe:

- expired locks
- stale worktree paths after reconciliation confirms no active issue owns them
- cached health or canary timestamps when explicitly rebuilding runtime state

Needs care:

- `healer_issues` rows for active or paused work
- `healer_attempts` history
- issue/attempt linkage to artifact evidence
- migration state when moving between repo names or DB locations

If the operator action changes meaning, document it in [docs/operations.md](/Users/cypher-server/Documents/code/flow-healer/docs/operations.md).

## Relationship To Other Docs

- use [docs/healing-state-machine.md](/Users/cypher-server/Documents/code/flow-healer/docs/healing-state-machine.md) for the runtime decision flow
- use [docs/connectors.md](/Users/cypher-server/Documents/code/flow-healer/docs/connectors.md) for connector-level failure behavior
