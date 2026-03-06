flow-healer start --once
~~~

The reconciler runs at the start of every tick and sweeps any workspace directory not associated with an active issue in the `healer_issues` table.

## Failure Recovery

When a healing attempt ends with `no_patch` or `verifier_failed`, handle it as an operational incident and recover predictably:

1. Identify the failing issue and inspect the last failure record.
2. Correct any environmental precondition (dependencies, flaky tests, temporary repo issues) that blocked the patch/verification.
3. Re-run a single pass so the same issue re-enters the queue and gets one immediate retry.

~~~bash
sqlite3 ~/.flow-healer/repos/demo/state.db "SELECT issue_id, attempt_id, failure_reason, failure_details, started_at FROM healer_attempts WHERE failure_reason IN ('no_patch', 'verifier_failed') ORDER BY started_at DESC LIMIT 10;"
~~~

~~~bash
flow-healer start --once --repo demo
~~~

## Common Issues

### "Docker not available"
diff --git a/docs/usage.md b/docs/usage.md
index 9ab9f4c..3ea9db1 100644
The scanner identifies deterministic breakage patterns (e.g., failed CI, linting errors). If `scan_enable_issue_creation` is set to `true`, it will create deduplicated GitHub issues for these findings, labeled with `kind:scan` and `healer:ready` to trigger the healing loop automatically.

> **Note**: Labels can be customized per-repo in the configuration to match your project's workflow. Standardizing labels across repos is recommended for consistent multi-repo orchestration.

## Failure Recovery

If a healing attempt finishes with `no_patch` or `verifier_failed`, stop and recover in this sequence:

1. Verify the issue is still visible and has context for retry.
2. Confirm temporary blockers are fixed (for example: dependency version drift, transient test flakiness, or missing credentials).
3. Trigger one controlled pass so the operator can review retry behavior before allowing normal cadence.

~~~bash
flow-healer start --repo my-project --once
~~~
diff --git a/docs/README.md b/docs/README.md
index 6e7d9a1..f4e0d2b 100644
## Doc Map

- [installation.md](installation.md): local environment setup and config
- [usage.md](usage.md): CLI flows and examples
- [usage.md - Failure Recovery](usage.md#failure-recovery): handling `no_patch` and `verifier_failed` retries
- [architecture.md](architecture.md): control loop and module map
- [operations.md](operations.md): common maintenance tasks and troubleshooting
- [operations.md - Failure Recovery](operations.md#failure-recovery): incident response for failed healing attempts
- [contributing.md](contributing.md): development and review expectations

## Failure Recovery

For production runs, use the dedicated recovery sections when a healing attempt ends with `no_patch` or `verifier_failed`:

- [Usage Failure Recovery](usage.md#failure-recovery)
- [Operations Failure Recovery](operations.md#failure-recovery)

~~~bash
flow-healer start --repo demo --once
~~~
