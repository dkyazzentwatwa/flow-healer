---
name: flow-healer-local-validation
description: Run this skill when the user wants safe local validation before any live Flow Healer action. Use for requests like "run local checks", "validate the healer locally", "do a dry run first", or "make sure the repo is healthy before live GitHub actions".
---

# Flow Healer Local Validation

Use this skill to verify the repo locally without touching live GitHub state.

## Inputs

- Run from the repo root so the script can emit the correct `repo_root`.
- An optional `.flow-healer-smoke-config.yaml` enables the dry-run scan check.

## Outputs

The script emits a JSON object with:

- `repo_root`
- `checks`

## Key Output Fields

- `repo_root`
- `checks[*].exit_code`
- `checks[*].output_tail`

## Success Criteria

- All checks pass: the local repo is healthy.
- `pytest` passes and the scan check is skipped: healthy enough for local work and preflight.
- Any non-zero check: blocked pending remediation.

## Failure Handling

- Repair local test or environment failures before any live run.
- Stop and do not escalate to live smoke from a failing local gate.
- Do not assume future fields such as `name`, `category`, or `duration_seconds`; act only on the fields the script emits today.

## Workflow

1. Run `scripts/local_validation.py` from the repo root.
2. Read `repo_root` first to confirm the check ran in the expected checkout.
3. Treat any non-zero `checks[*].exit_code` as a no-go for a live run until the failure is understood.
4. If the user only wants a plumbing test, you may stop after local validation.
5. If the user wants live mutation, hand off to the preflight or live-smoke skill with the command results.

## Default Command

```bash
.venv/bin/python skills/flow-healer-local-validation/scripts/local_validation.py
```

## Next Step

- Stop here for plumbing-only validation.
- Hand off to `flow-healer-preflight` before live GitHub work.

## Load On Demand

- Use [references/modes.md](references/modes.md) when deciding whether a fake/in-process run is enough or a live smoke is justified.
