# Healing State Machine

This doc is the runtime decision map for issue processing.

## Canonical Anchors

- [src/flow_healer/healer_loop.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_loop.py)
- [src/flow_healer/healer_runner.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_runner.py)
- [src/flow_healer/healer_verifier.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_verifier.py)
- [src/flow_healer/healer_swarm.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_swarm.py)
- [src/flow_healer/healer_reconciler.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_reconciler.py)

## High-Level Flow

```text
ready issue
  -> claim
  -> parse task contract
  -> preflight / runtime readiness
  -> runner attempt
  -> validation
  -> verifier
  -> PR actions or human stop
  -> feedback / retry / resolution
```

## Decision Points

### Claim And Parse

- issue must satisfy label and trust rules
- task spec is compiled from the issue body
- low-confidence or ambiguous contracts route to `needs_clarification`

### Preflight And Runtime Readiness

- connector health is probed
- language and execution root are resolved
- app-backed tasks resolve runtime profile and fixture behavior

### Runner Attempt

The runner may:

- capture browser repro/evidence
- widen scope safely for baseline validation blockers
- stop with `baseline_validation_blocked` when scope cannot be widened safely
- produce staged workspace changes
- fail fast on connector/runtime/contract issues

### Validation

Validation runs through the resolved execution root and language strategy or explicit `Validation:` commands.

Possible results:

- clean pass
- tests failed
- evidence missing
- invalid command / unresolved language
- runtime boot or browser-step failure

### Verification

Verifier decides whether a patch is trusted enough to open or update a PR. Soft and hard failures can route to retry or to human judgment depending on policy.

### Swarm And Recovery

Swarm or native multi-agent recovery may activate for configured failure classes. Quarantine exists to stop speculative retries when the same failure fingerprint keeps recurring.

### Human Decision Stops

The main human-stop states are:

- `needs_clarification`
- `judgment_required`
- blocked PR approval or review follow-up states

These states mean automation should stop and explain the next required decision, not keep retrying blindly.

## Where Key Outcomes Are Recorded

- no patch or malformed output: runner and retry playbook
- verifier rejection: verifier plus attempt/test summary
- missing evidence: runner artifact/evidence summary
- quarantine: loop failure fingerprint handling
- swarm activation: swarm summary in attempts
- PR feedback ingestion: issue feedback context plus re-queue flow

## Relationship To Other Docs

- [docs/runtime-state.md](/Users/cypher-server/Documents/code/flow-healer/docs/runtime-state.md) explains persistence
- [docs/evidence-contract.md](/Users/cypher-server/Documents/code/flow-healer/docs/evidence-contract.md) explains artifact gates
- [docs/issue-contracts.md](/Users/cypher-server/Documents/code/flow-healer/docs/issue-contracts.md) explains the task spec inputs
