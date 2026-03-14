# Agent Remediation Playbook

This doc defines how Flow Healer should repair its own weak spots when repeated failures show that the harness, docs, fixtures, or contracts are underspecified.

## Core Rule

When the same class of issue fails repeatedly, prefer fixing the repository's guidance and invariants before adding more connector cleverness.

The preferred remediation order is:

1. tighten the issue contract
2. add or refresh lane docs
3. add or refresh fixture and evidence contracts
4. add regression tests for the specific failure mode
5. only then change runtime code or connector behavior if the repo contract is already strong

## Canonical Anchors

- [src/flow_healer/healer_task_spec.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_task_spec.py)
- [src/flow_healer/healer_runner.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_runner.py)
- [src/flow_healer/healer_loop.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_loop.py)
- [tests/test_healer_task_spec.py](/Users/cypher-server/Documents/code/flow-healer/tests/test_healer_task_spec.py)
- [tests/test_healer_runner.py](/Users/cypher-server/Documents/code/flow-healer/tests/test_healer_runner.py)
- [tests/test_healer_loop.py](/Users/cypher-server/Documents/code/flow-healer/tests/test_healer_loop.py)

## Failure Patterns And Preferred Fixes

### Missing Or Weak Docs

Signal:

- the agent edits the wrong dashboard surface
- the agent confuses export/TUI surfaces with the Python HTTP control plane
- the agent changes payload semantics while trying to make a visual tweak

Preferred repo fix:

- update [docs/dashboard.md](/Users/cypher-server/Documents/code/flow-healer/docs/dashboard.md)
- add or refresh focused dashboard tests
- update [AGENTS.md](/Users/cypher-server/Documents/code/flow-healer/AGENTS.md) so agents know which surface is canonical

### Weak Issue Contract

Signal:

- wrong execution root
- scope violations outside declared outputs
- browser tasks that do not declare evidence needs or runtime profile
- repeated `needs_clarification`, `no_patch`, `scope_violation`, or `baseline_validation_blocked`

Preferred repo fix:

- update [docs/issue-contracts.md](/Users/cypher-server/Documents/code/flow-healer/docs/issue-contracts.md)
- refresh examples in [docs/harness-repro-contract-examples.json](/Users/cypher-server/Documents/code/flow-healer/docs/harness-repro-contract-examples.json)
- add parser or runner regressions

### Missing Smoke Fixture Or Runtime Contract

Signal:

- browser steps are flaky because data/auth state is not deterministic
- canaries fail because a runtime profile is undocumented or stale
- app-backed issues keep requiring manual cleanup

Preferred repo fix:

- update [docs/fixture-profile-guidance.md](/Users/cypher-server/Documents/code/flow-healer/docs/fixture-profile-guidance.md)
- update [docs/evidence-contract.md](/Users/cypher-server/Documents/code/flow-healer/docs/evidence-contract.md)
- update the relevant lane guide
- add canary or runner tests for the missing invariant

### Missing State Or Retry Invariant

Signal:

- attempts loop blindly instead of stopping for judgment
- runtime state is mutated without clear operator guidance
- quarantine, retry, or judgment behavior is surprising to operators

Preferred repo fix:

- update [docs/runtime-state.md](/Users/cypher-server/Documents/code/flow-healer/docs/runtime-state.md)
- update [docs/healing-state-machine.md](/Users/cypher-server/Documents/code/flow-healer/docs/healing-state-machine.md)
- add loop/store regression coverage

## What To Change In-Repo

When Flow Healer remediates itself, prefer repo-owned assets over out-of-band human notes:

- canonical docs under `docs/`
- issue examples under [docs/harness-repro-contract-examples.json](/Users/cypher-server/Documents/code/flow-healer/docs/harness-repro-contract-examples.json)
- tests in `tests/`
- fixture drivers or runtime-profile docs under app targets
- AGENTS operating rules

Do not treat chat history as the source of truth. Persist the lesson in the repo.

## What Good Remediation Looks Like

Good remediation usually bundles:

- one doc update that explains the rule
- one regression test that catches the failure
- one focused runtime or parser change only if the contract was already clear

## What This Doc Does Not Define

This doc defines remediation doctrine, not the contracts themselves. For the actual rules, use:

- [docs/issue-contracts.md](/Users/cypher-server/Documents/code/flow-healer/docs/issue-contracts.md)
- [docs/evidence-contract.md](/Users/cypher-server/Documents/code/flow-healer/docs/evidence-contract.md)
- [docs/runtime-state.md](/Users/cypher-server/Documents/code/flow-healer/docs/runtime-state.md)
- [docs/healing-state-machine.md](/Users/cypher-server/Documents/code/flow-healer/docs/healing-state-machine.md)
