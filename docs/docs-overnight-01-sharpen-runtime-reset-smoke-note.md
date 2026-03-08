# Runtime Reset Smoke Note

This overnight smoke note verifies that Flow Healer can recover cleanly after a
runtime reset without carrying stale assumptions from the prior run.

## What The Reset Should Prove

- The next proposer pass starts from the current workspace state instead of
  replaying stale status from the failed attempt.
- The agent edits the requested artifact directly in the managed workspace.
- The run finishes with a scoped file change and a brief operator summary.

## Failure Pattern To Guard Against

The reset is not healthy if the proposer only reports progress, returns a plan,
or exits with a summary that leaves the target file unchanged. The smoke should
specifically catch the `no_workspace_change` failure mode that follows a prior
attempt which looked complete in prose but never wrote the artifact.

## Clean Run Signal

A healthy reset path updates this file in place, keeps the artifact path stable,
and exits without falling back to diff-only output, plan-only prose, or a
no-op completion.

## Operator Check

- Confirm that `docs/docs-overnight-01-sharpen-runtime-reset-smoke-note.md`
  changed in the workspace during the run.
- Confirm that the proposer summary names the file it touched.
- Confirm that no fallback artifact block was needed because the direct edit
  path succeeded.
