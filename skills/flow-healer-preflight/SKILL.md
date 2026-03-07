---
name: flow-healer-preflight
description: Run this skill before any Flow Healer live operation when the user wants to validate GitHub auth, repo readiness, Docker, Python environment, open issue/PR surface, and local healer SQLite state. Use for requests like "preflight this repo", "is Flow Healer ready", "check live readiness", or "validate the healer environment before a run".
---

# Flow Healer Preflight

Use this skill before any live Flow Healer action.

## Inputs

- `--repo-path`
- `--repo-slug`
- Optional `--db-path`

## Outputs

The script emits a JSON object with:

- `repo_path`
- `repo_slug`
- `required_checks`
- `context`
- `samples`
- `notes`

## Key Output Fields

- `required_checks.gh_auth_ok`
- `required_checks.repo_exists`
- `required_checks.git_repo`
- `required_checks.repo_clean_git`
- `required_checks.venv_ok`
- `required_checks.docker_ok`
- `context.state_counts`
- `notes.gh_auth_output_tail`

## Success Criteria

- All required checks pass: safe for live smoke.
- The repo is locally usable but one or more required live checks fail: safe only for local work.
- Active unexpected healer state or missing core prerequisites: blocked pending remediation.

## Failure Handling

- Name the failing check before sending the operator to [references/remediation.md](references/remediation.md).
- Stop on failed auth, missing repo, invalid git worktree, dirty worktree, missing `.venv`, or missing Docker.
- Treat `docker_ok` as required because the script requires it today.

## Workflow

1. Run `scripts/preflight_check.py` with the repo path, repo slug, and optional state DB path.
2. Read `required_checks` first; they decide whether live mutation is allowed.
3. Treat any failed `required_checks` item as a no-go for live mutation.
4. If the user already has a target issue or PR, include that in the operator summary.
5. If the script reports active healer state, read [references/remediation.md](references/remediation.md) before proposing next steps.

## Default Command

```bash
.venv/bin/python skills/flow-healer-preflight/scripts/preflight_check.py \
  --repo-path /absolute/path/to/repo \
  --repo-slug owner/repo
```

## Next Step

- Default to `flow-healer-live-smoke` only when every required check passes.

## Stop Conditions

- Invalid GitHub auth
- Missing `.venv`
- Missing Docker when test gates will run
- Repo path is not a git worktree
- The healer DB already shows unexpected `running` state and the user did not ask to continue

## Load On Demand

- Use [references/remediation.md](references/remediation.md) when a check fails or when multiple live artifacts are already open.
