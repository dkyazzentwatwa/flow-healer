---
name: flow-healer-local-validation
description: Run this skill when the user wants safe local validation before any live Flow Healer action. Use for requests like "run local checks", "validate the healer locally", "do a dry run first", or "make sure the repo is healthy before live GitHub actions".
---

# Flow Healer Local Validation

Use this skill to verify the repo locally without touching live GitHub state.

## Workflow

1. Run `scripts/local_validation.py` from the repo root.
2. Treat any non-zero check as a no-go for a live run until the failure is understood.
3. If the user only wants a plumbing test, you may stop after local validation.
4. If the user wants live mutation, hand off to the preflight or live-smoke skill with the command results.

## Default Command

```bash
.venv/bin/python skills/flow-healer-local-validation/scripts/local_validation.py
```

## Load On Demand

- Use [references/modes.md](references/modes.md) when deciding whether a fake/in-process run is enough or a live smoke is justified.
