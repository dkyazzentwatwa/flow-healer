# Operations

## Split Service Cutover (Apple Flow + Flow Healer)

Use this runbook when both daemons must stay always-on while remaining fully isolated (separate launch labels, DB roots, logs, and working directories).

### 1) Backup DBs

~~~bash
mkdir -p ~/.apple-flow/backups ~/.flow-healer/backups
cp -av ~/Documents/code/codex-flow/data/relay.db ~/.apple-flow/backups/relay.db.$(date +%Y%m%d%H%M%S).bak || true
cp -av ~/.flow-healer/repos/flow-healer/state.db ~/.flow-healer/backups/flow-healer.state.$(date +%Y%m%d%H%M%S).bak || true
~~~

### 2) Stop both services

~~~bash
launchctl stop local.flow-healer || true
launchctl stop local.apple-flow || true
~~~

### 3) Apple Flow DB migration

~~~bash
mkdir -p ~/.apple-flow
cp -av ~/Documents/code/codex-flow/data/relay.db ~/.apple-flow/relay.db
~~~

Set Apple Flow env to prevent healer ownership drift:

~~~bash
perl -0pi -e 's/^apple_flow_enable_autonomous_healer=.*/apple_flow_enable_autonomous_healer=false/m' ~/Documents/code/codex-flow/.env
perl -0pi -e 's/^apple_flow_enable_healer_scheduled_scans=.*/apple_flow_enable_healer_scheduled_scans=false/m' ~/Documents/code/codex-flow/.env
perl -0pi -e 's|^apple_flow_db_path=.*|apple_flow_db_path=/Users/cypher-server/.apple-flow/relay.db|m' ~/Documents/code/codex-flow/.env
~~~

### 4) Ensure Flow Healer launch config is explicit

`local.flow-healer.plist` should include:

- `Label`: `local.flow-healer`
- `WorkingDirectory`: `/Users/cypher-server/Documents/code/flow-healer`
- `ProgramArguments`: `/Users/cypher-server/Documents/code/flow-healer/.venv/bin/python -m flow_healer.cli --config /Users/cypher-server/.flow-healer/config.yaml start`
- `EnvironmentVariables.PYTHONPATH`: `/Users/cypher-server/Documents/code/flow-healer/src`
- `StandardErrorPath` / `StandardOutPath` under `~/.flow-healer/`

`local.apple-flow.plist` should include:

- `Label`: `local.apple-flow`
- `WorkingDirectory`: `/Users/cypher-server/Documents/code/codex-flow`
- stdout/stderr paths under `~/.apple-flow/logs/`

### 5) Start and enable boot/login persistence

~~~bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.apple-flow.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.flow-healer.plist 2>/dev/null || true
launchctl enable gui/$(id -u)/local.apple-flow
launchctl enable gui/$(id -u)/local.flow-healer
launchctl start local.apple-flow
launchctl start local.flow-healer
~~~

### 5a) Optional nightly helper recycle

To recycle Flow Healer helper subprocesses without taking down the parent daemon, add a separate LaunchAgent:

- `Label`: `local.flow-healer.recycle-helpers`
- `ProgramArguments`: `/Users/cypher-server/Documents/code/flow-healer/.venv/bin/python -m flow_healer.cli --config /Users/cypher-server/.flow-healer/config.yaml recycle-helpers --idle-only`
- `WorkingDirectory`: `/Users/cypher-server/Documents/code/flow-healer`
- `StartCalendarInterval`: `Hour=3`, `Minute=0`
- `StandardErrorPath`: `~/.flow-healer/recycle-helpers.err`
- `StandardOutPath`: `~/.flow-healer/recycle-helpers.out`

After shipping code that adds the recycle handler, restart the main `local.flow-healer` agent once during an idle window so the live daemon loads the new logic:

~~~bash
launchctl kickstart -k gui/$(id -u)/local.flow-healer
~~~

The continuous `start` command now boots the same always-on runtime as `serve`, so the web dashboard should be available whenever `local.flow-healer` is running.

### 6) Clear stale running attempts

If an issue remains `running` after daemon restart, requeue expired leases:

~~~bash
sqlite3 ~/.flow-healer/repos/flow-healer/state.db "UPDATE healer_issues SET state='queued', lease_owner=NULL, lease_expires_at=NULL, updated_at=CURRENT_TIMESTAMP WHERE state='running' AND lease_expires_at <= CURRENT_TIMESTAMP;"
~~~

### 7) Verify separation

~~~bash
scripts/diagnose_runtime.sh ~/.flow-healer/config.yaml flow-healer
scripts/verify_runtime.sh ~/.flow-healer/config.yaml flow-healer
flow-healer --config ~/.flow-healer/config.yaml doctor --repo flow-healer
flow-healer --config ~/.flow-healer/config.yaml status --repo flow-healer
~~~

## Workspace Reconciliation

The reconciler runs at the start of every tick and sweeps any workspace directory not associated with an active issue in the `healer_issues` table.

~~~bash
flow-healer start --once
~~~

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

### PR-open failures

When an attempt reaches `pr_open_failed`, the patch and push steps already succeeded and the failure happened while calling the GitHub issue or pull request API. Start by confirming the repo is healthy and capturing the latest GitHub-side error signal:

~~~bash
flow-healer doctor --repo demo
~~~

~~~bash
sqlite3 ~/.flow-healer/repos/demo/state.db "SELECT issue_id, failure_class, failure_reason, started_at FROM healer_attempts WHERE failure_class = 'pr_open_failed' ORDER BY started_at DESC LIMIT 10;"
~~~

If the latest attempt also recorded a connector GitHub error, inspect the cached runtime state:

~~~bash
sqlite3 ~/.flow-healer/repos/demo/state.db "SELECT key, value FROM healer_state WHERE key IN ('healer_connector_last_error_class', 'healer_connector_last_error_reason') ORDER BY key;"
~~~

Use the following triage path for the most common root causes.

#### `github_auth_missing`

Use this path when `flow-healer doctor` reports `github_token_present` as false, the service environment lost the configured token, or the last error reason shows authentication or permission failures such as `401`, `403`, or `Bad credentials`.

1. Confirm which token variable the service expects from `doctor` output under `github_token_env`.
2. Export or restore that variable in the runtime environment used by the service or launch agent.
3. If the token exists but PR creation still fails, replace it with a token that can read the repo, push branches, and open pull requests for the target repository.
4. Re-run `flow-healer doctor --repo demo` and confirm `github_token_present` is true before retrying the queue.

~~~bash
flow-healer start --once --repo demo
~~~

#### `github_api_error`

Use this path when the cached error class is `github_api_error` or the failure reason mentions GitHub returning `403`, `422`, `500`, `502`, `503`, or `504`.

1. Read the stored `healer_connector_last_error_reason` value to capture the exact GitHub response.
2. For `403`, check for branch protection, missing repository permissions, or temporary abuse or rate-limit responses.
3. For `422`, inspect whether the managed branch already has an open pull request, the base branch is invalid, or the PR payload became stale.
4. For `5xx`, treat the incident as transient and retry after the service backoff window.
5. If the error persists across retries, pause automation for that repo until credentials or repository policy are corrected.

~~~bash
flow-healer status --repo demo
~~~

#### `github_network_error`

Use this path when the cached error class is `github_network_error` or the last error reason shows `URLError`, DNS resolution failure, TLS handshake failure, or connection timeout.

1. Verify general outbound connectivity from the host running Flow Healer.
2. Check whether `https://api.github.com` is reachable from that environment and whether any proxy, VPN, or firewall rule changed.
3. If the service runs under `launchd`, compare the `launchd_path` and `launchd_path_has_connector` fields from `doctor` with the interactive shell environment to catch path or networking drift.
4. Retry one controlled pass after connectivity is restored.

~~~bash
flow-healer start --once --repo demo
~~~

If none of the three paths explain the failure, preserve the `healer_connector_last_error_reason` value and the matching `healer_attempts` row in the incident notes before deeper debugging.

## Common Issues

### "Docker not available"

**Symptom**: Test gate fails with "Docker not available" or "exec: docker: not found"

**Solution**: Ensure Docker is running and accessible. For Python or Node repos without usable local toolchains, configure Docker-only mode:

```yaml
repos:
  - name: my-project
    test_gate_mode: docker_only
    local_gate_policy: skip
```

### Local toolchain missing

**Symptom**: Tests fail because the local Python, Node.js, or Swift toolchain is unavailable or broken.

**Solution**:

- For Python or Node, use `docker_only` to skip local testing entirely.
- For Swift, repair the local toolchain and use `local_only` or `local_then_docker` because Swift does not support Docker gates.

```yaml
repos:
  - name: node-project
    test_gate_mode: docker_only
    local_gate_policy: skip
    language: node
```

### Docker image pull failure

**Symptom**: "Unable to find image" or network timeout during Docker operations

**Solution**:
1. Check Docker is running: `docker ps`
2. Pull the image manually: `docker pull node:20-slim`
3. Verify network connectivity to Docker Hub

### Test command timeout

**Symptom**: Tests hang or timeout during Docker execution

**Solution**: Increase `connector_timeout_seconds` in config:

```yaml
service:
  connector_timeout_seconds: 600
```

## Monitoring

`flow-healer status --repo <repo>` now includes three high-value reliability surfaces:

- `retry_playbook_metrics`: retry strategy volume, dominant failure domain, and last selected playbook details.
- `reliability_trends`: `7d` and `30d` windows with current vs previous-window deltas.
- `reliability_daily_rollups`: per-day reliability summaries for quick regression spotting.

When retry behavior drifts, start with `retry_playbook_metrics.dominant_domain` and `top_failure_classes` to decide whether to tune contract prompts, infra preflight, or code-focused retries.

Check healer status:

~~~bash
flow-healer status --repo demo
~~~

Review recent attempts:

~~~bash
sqlite3 ~/.flow-healer/repos/demo/state.db "SELECT issue_id, status, failure_reason, started_at FROM healer_attempts ORDER BY started_at DESC LIMIT 20;"
~~~
