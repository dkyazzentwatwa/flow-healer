# Operations Guide

This guide covers common administrative tasks and troubleshooting steps for maintaining a Flow Healer instance.

## Monitoring Status

Check the current state of all managed repositories and their recent healing attempts.

~~~bash
# Summary of all repos
flow-healer status

# Detailed status for a specific repo
flow-healer status --repo demo
~~~

The status output includes:
- **Queued Issues**: Issues labeled and ready to be processed.
- **Running Attempts**: Issues currently being worked on by a healer worker.
- **Recent Failures**: Recent attempts that hit retry limits or encountered fatal errors.
- **Pause Status**: Whether the repo is currently accepting new work.

## Pausing and Resuming

To stop the healer from picking up new work (e.g., during planned maintenance of the target repo):

~~~bash
flow-healer pause --repo demo
~~~

To resume work:

~~~bash
flow-healer resume --repo demo
~~~

## Inspecting the SQLite State

All durable state is stored in SQLite databases. By default, these are located at:
`~/.flow-healer/repos/<repo-name>/state.db`

You can use the `sqlite3` CLI to inspect the tables:

~~~bash
# View all issues in the system
sqlite3 ~/.flow-healer/repos/demo/state.db "SELECT * FROM healer_issues;"

# View recent healing attempts
sqlite3 ~/.flow-healer/repos/demo/state.db "SELECT * FROM healer_attempts ORDER BY started_at DESC LIMIT 5;"
~~~

### Table Reference

| Table | Purpose |
| --- | --- |
| `healer_issues` | Tracks the lifecycle of GitHub issues. |
| `healer_attempts` | History of individual healing runs. |
| `healer_lessons` | Insights captured from successes and failures. |
| `scan_findings` | Issues detected by the scanner. |
| `healer_locks` | Current path-level locks held by workers. |

## Handling Stuck Issues

If an issue is stuck in the `running` state (e.g., due to a crash), the **Healer Reconciler** should automatically recover it once its lease expires (usually 3x the poll interval).

To manually force-release an issue, you can clear its lease in the database (not recommended unless the service is stopped):

~~~bash
sqlite3 ~/.flow-healer/repos/demo/state.db "UPDATE healer_issues SET state='queued', lease_owner=NULL, lease_expires_at=NULL WHERE issue_id='123';"
~~~

## Cleaning Up Orphan Workspaces

Workspaces are created under the `state_root` in a `worktrees` directory. If they are not cleaned up automatically, you can run the reconciler logic via a single pass:

~~~bash
flow-healer start --once
~~~

The reconciler runs at the start of every tick and sweeps any workspace directory not associated with an active issue in the `healer_issues` table.

## Common Issues

### "Docker not available"
Flow Healer requires a running Docker daemon to execute test gates. Ensure Docker is started and your user has permissions to run `docker ps`.

### "GitHub Token Missing"
Check that the environment variable specified in `github_token_env` (default `GITHUB_TOKEN`) is exported in your shell.

### "Lock Conflict"
If multiple issues affect the same files, Flow Healer will wait for locks to release. If you suspect a stale lock, the reconciler will clean it up after its expiration time.
