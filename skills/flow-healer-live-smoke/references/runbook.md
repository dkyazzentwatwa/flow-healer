# Live Smoke Runbook

## Guardrails

- Use a dedicated smoke issue rather than a real backlog issue whenever possible.
- Prefer deterministic connector templates over real model output when validating GitHub plumbing.
- Keep live smoke changes low-risk and reviewable.
- Capture the exact config and connector paths used for the run.

## Artifact Checklist

- target issue id
- branch name
- PR id and URL
- last attempt state
- verifier result
- test summary tail
- whether the same PR was reused on follow-up

## When to Stop

- invalid auth or preflight failure
- issue stuck in `queued` past backoff window
- `patch_apply_failed` caused by malformed connector output
- base branch/worktree drift that makes the repo fixture no longer trustworthy
