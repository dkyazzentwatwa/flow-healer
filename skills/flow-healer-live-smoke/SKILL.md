---
name: flow-healer-live-smoke
description: Run this skill when the user wants a guarded live Flow Healer smoke test on a real GitHub repo. Use for requests like "do a live smoke", "test this repo live", "open a real PR through the healer", or "validate issue-to-PR plumbing on GitHub".
---

# Flow Healer Live Smoke

Use this skill for low-risk, live GitHub validation.

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

## Load On Demand

- Use [references/runbook.md](references/runbook.md) for the exact operator sequence and artifact checklist.
