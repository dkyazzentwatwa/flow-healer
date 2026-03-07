---
name: flow-healer-triage
description: Run this skill when a Flow Healer run fails or behaves unexpectedly and the user wants a fast, deterministic diagnosis. Use for requests like "triage this healer failure", "why did the run fail", "classify this issue state", or "tell me if this is an environment problem or a product bug".
---

# Flow Healer Triage

Use this skill after any failed or suspicious Flow Healer attempt.

## Inputs

- `--db-path`
- `--issue-id`

## Outputs

The script emits a JSON object with:

- `issue`
- `latest_attempt`
- `diagnosis`

## Key Output Fields

- `diagnosis`
- `latest_attempt.failure_class`
- `latest_attempt.failure_reason`
- `issue.state`

## Success Criteria

- Diagnosis is produced and paired with an operator-ready next action.

## Failure Handling

- If the issue row is missing or incomplete, stop and repair state visibility before classifying further.
- Repair operator or environment problems before another live run.
- Treat `connector_or_patch_generation` as an immediate handoff to `flow-healer-connector-debug`.

## Workflow

1. Run `scripts/triage_issue.py` with the healer DB path and issue id.
2. Read `diagnosis` first, then confirm it against `latest_attempt.failure_class`, `latest_attempt.failure_reason`, and `issue.state`.
3. If the failure lands in `product_bug`, read [references/failure_catalog.md](references/failure_catalog.md) and compare against known incidents.
4. If the failure lands in `operator_or_environment`, fix the environment before another live run.

## Default Command

```bash
.venv/bin/python skills/flow-healer-triage/scripts/triage_issue.py \
  --db-path /tmp/flow-healer-state/repos/live/state.db \
  --issue-id 3
```

## Diagnosis Buckets

- `operator_or_environment`
- `repo_fixture_or_setup`
- `connector_or_patch_generation`
- `product_bug`
- `external_service_or_github`

## Next Step

- `operator_or_environment`: repair the environment and rerun `flow-healer-preflight`.
- `repo_fixture_or_setup`: repair the repo/setup and rerun `flow-healer-local-validation`.
- `connector_or_patch_generation`: hand off to `flow-healer-connector-debug` and compare proposer versus verifier output contracts.
- `product_bug`: capture evidence and escalate.
- `external_service_or_github`: retry later with an operator note.

## Load On Demand

- Use [references/failure_catalog.md](references/failure_catalog.md) when the script classifies the issue as `product_bug` or when the pattern is unfamiliar.
