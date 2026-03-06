# Follow-Up Rules

## Reuse Existing Artifacts

- Reuse the same issue id and PR whenever the PR is still open.
- Reuse the same issue worktree branch for connector-generated follow-up diffs.
- Use external PR comments, reviews, or inline review comments as valid triggers.

## Ignore These Triggers

- The healer's own reviewer comment
- Other comments authored by the same authenticated GitHub actor
- Re-running with no new external feedback since the last stored watermark

## Escalate Instead of Retrying

- Stored worktree branch no longer reflects the intended base
- The previous failure indicates malformed connector output
- The PR has already been closed or merged
