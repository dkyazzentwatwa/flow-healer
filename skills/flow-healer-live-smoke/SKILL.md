---
name: flow-healer-live-smoke
description: Run this skill when the user wants a guarded live Flow Healer smoke test on a real GitHub repo. Use for requests like "do a live smoke", "test this repo live", "open a real PR through the healer", or "validate issue-to-PR plumbing on GitHub".
---

# Flow Healer Live Smoke

Use this skill for low-risk, live GitHub validation.

## Inputs

- `--repo-path`
- `--repo-slug`
- `--repo-name`
- `--output-dir`
- Optional `--template`

## Outputs

The bundle generator emits a JSON object with:

- `template`
- `connector_path`
- `config_path`
- `state_root`

## Key Output Fields

- `template`
- `connector_path`
- `config_path`
- `state_root`
- `issue_id`
- `pr_id`
- `branch_name`
- `attempt_state`
- `verifier_summary`
- `test_summary`

## Success Criteria

- Preflight passed and the bundle is generated successfully.
- The emitted `connector_path` and `config_path` exist and are ready for a guarded `flow-healer start --once` run.
- Any bundle-generation failure or missing artifact: blocked pending repair.

## Failure Handling

- Stop if preflight did not fully pass; repair first instead of generating live artifacts anyway.
- Stop if the bundle script fails or does not emit usable paths.
- Remember that this script only prepares the deterministic connector and config bundle. It does not run `flow-healer start --once` by itself.

## Workflow

1. Run the preflight skill first.
2. Generate a temporary config and deterministic connector bundle with `scripts/make_live_smoke_bundle.py`.
3. Use an isolated, smoke-safe issue. Prefer docs-only or similarly low-risk work.
4. Run `flow-healer start --once` with the generated config.
5. Capture the resulting issue id, PR id, branch name, attempt state, verifier summary, and test summary.
6. Stop if the run exposes a real product bug; hand off to the triage skill instead of retrying blindly.

## Default Generator

```bash
.venv/bin/python skills/flow-healer-live-smoke/scripts/make_live_smoke_bundle.py \
  --repo-path /absolute/path/to/repo \
  --repo-slug owner/repo \
  --repo-name live \
  --output-dir /tmp/flow-healer-live-bundle \
  --template docs_scaffold
```

## Templates

- `docs_scaffold`: create a minimal `/docs` structure from a smoke-safe issue
- `docs_followup_note`: apply a single-file README follow-up note on an existing PR branch

## Artifact Checklist

Capture these after the guarded `flow-healer start --once` run:

- `issue_id`
- `pr_id`
- `branch_name`
- `attempt_state`
- `verifier_summary`
- `test_summary`

## Next Step

- Run `flow-healer start --once` with the generated config only after preflight has passed and the smoke-safe issue is ready.
- Hand off to `flow-healer-triage` if the live run exposes a product bug or unexpected failure.

## Load On Demand

- Use [references/runbook.md](references/runbook.md) for the exact operator sequence and artifact checklist.
