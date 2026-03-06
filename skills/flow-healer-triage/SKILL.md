---
name: flow-healer-triage
description: Run this skill when a Flow Healer run fails or behaves unexpectedly and the user wants a fast, deterministic diagnosis. Use for requests like "triage this healer failure", "why did the run fail", "classify this issue state", or "tell me if this is an environment problem or a product bug".
---

# Flow Healer Triage

Use this skill after any failed or suspicious Flow Healer attempt.

## Workflow

1. Run `scripts/triage_issue.py` with the healer DB path and issue id.
2. Read the diagnosis bucket and evidence before proposing action.
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

## Load On Demand

- Use [references/failure_catalog.md](references/failure_catalog.md) when the script classifies the issue as `product_bug` or when the pattern is unfamiliar.
