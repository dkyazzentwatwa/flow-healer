---
name: flow-healer-pr-followup
description: Run this skill when the user wants to validate or execute a Flow Healer PR follow-up on an existing live PR. Use for requests like "rerun the same PR", "ingest review feedback", "follow up on this healer PR", or "reuse the existing issue and PR after comments".
---

# Flow Healer PR Follow-Up

Use this skill only when a Flow Healer-created PR already exists.

## Workflow

1. Inspect the issue state with `scripts/inspect_issue_state.py`.
2. Confirm that external feedback exists and has not already been ingested.
3. Prefer the same issue id and same PR number.
4. If a deterministic connector is being used, make sure follow-up diffs are generated from the issue worktree branch, not repo root.
5. Requeue the issue only when the previous state is safe to resume.

## Default Command

```bash
.venv/bin/python skills/flow-healer-pr-followup/scripts/inspect_issue_state.py \
  --db-path /tmp/flow-healer-state/repos/live/state.db \
  --issue-id 3
```

## Stop Conditions

- No external comment/review exists
- Feedback is already fully ingested
- The issue is still actively `running`
- The existing PR branch no longer matches the stored worktree metadata

## Load On Demand

- Use [references/followup_rules.md](references/followup_rules.md) when deciding whether to reuse or recreate artifacts.
