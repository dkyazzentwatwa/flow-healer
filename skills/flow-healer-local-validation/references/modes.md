# Validation Modes

## Use Local Validation Only When

- You changed Flow Healer internals and only need confidence before a later live run.
- The repo is in a risky local state and you do not want to touch GitHub yet.
- The user asked for dry-run style confidence only.

## Escalate to Live Smoke When

- GitHub issue ingestion must be proven.
- PR creation/update behavior must be validated.
- Feedback requeue behavior must be exercised.
- A past failure only appears when real GitHub state is involved.
