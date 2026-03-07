---
name: flow-healer-pr-followup
description: Run this skill when the user wants to validate or execute a Flow Healer PR follow-up on an existing live PR. Use for requests like "rerun the same PR", "ingest review feedback", "follow up on this healer PR", or "reuse the existing issue and PR after comments".
---

# Flow Healer PR Follow-Up

Use this skill only when a Flow Healer-created PR already exists.

## Inputs

- `--db-path`
- `--issue-id`

## Outputs

The script emits a JSON object with:

- `issue`
- `attempts`

## Key Output Fields

- `issue.pr_number`
- `issue.last_issue_comment_id`
- `issue.feedback_context`
- `issue.state`
- `attempts[*].state`

## Success Criteria

- Reuse is safe only when the issue is still active, the PR is still relevant, new external feedback exists, and no run is currently active.

## Failure Handling

- If the issue row is missing, stop because the script returns exit code `1`.
- Distinguish no new feedback, already-ingested feedback, active running state, and branch or worktree mismatch before deciding to resume.
- Keep the resume decision in operator judgment; this script reports state only.

## Workflow

1. Inspect the issue state with `scripts/inspect_issue_state.py`.
2. Read `issue.pr_number`, `issue.last_issue_comment_id`, and `issue.feedback_context` first to confirm this is a real follow-up candidate.
3. Confirm that external feedback exists and has not already been ingested.
4. Prefer the same issue id and same PR number.
5. If a deterministic connector is being used, make sure follow-up diffs are generated from the issue worktree branch, not repo root.
6. Requeue the issue only when the previous state is safe to resume.

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

## Safe Resume Checklist

- The issue is still active.
- The PR is still relevant.
- New external feedback exists.
- No active running attempt exists.
- Stored branch or worktree metadata still matches reality.

## Next Step

- Reuse the existing issue and PR only when the resume checks pass.
- Fall back to `flow-healer-triage` when reuse is unsafe or ambiguous.

## Load On Demand

- Use [references/followup_rules.md](references/followup_rules.md) when deciding whether to reuse or recreate artifacts.
