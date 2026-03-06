---
name: flow-healer-preflight
description: Run this skill before any Flow Healer live operation when the user wants to validate GitHub auth, repo readiness, Docker, Python environment, open issue/PR surface, and local healer SQLite state. Use for requests like "preflight this repo", "is Flow Healer ready", "check live readiness", or "validate the healer environment before a run".
---

# Flow Healer Preflight

Use this skill before any live Flow Healer action.

## Workflow

1. Run `scripts/preflight_check.py` with the repo path, repo slug, and optional state DB path.
2. Treat any failed `required_checks` item as a no-go for live mutation.
3. If the user already has a target issue or PR, include that in the operator summary.
4. If the script reports active healer state, read [references/remediation.md](references/remediation.md) before proposing next steps.

## Default Command

```bash
.venv/bin/python skills/flow-healer-preflight/scripts/preflight_check.py \
  --repo-path /absolute/path/to/repo \
  --repo-slug owner/repo
```

## Stop Conditions

- Invalid GitHub auth
- Missing `.venv`
- Missing Docker when test gates will run
- Repo path is not a git worktree
- The healer DB already shows unexpected `running` state and the user did not ask to continue

## Load On Demand

- Use [references/remediation.md](references/remediation.md) when a check fails or when multiple live artifacts are already open.
