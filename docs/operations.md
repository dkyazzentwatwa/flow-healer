# Operations

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

Check healer status:

~~~bash
flow-healer status --repo demo
~~~

Review recent attempts:

~~~bash
sqlite3 ~/.flow-healer/repos/demo/state.db "SELECT issue_id, status, failure_reason, started_at FROM healer_attempts ORDER BY started_at DESC LIMIT 20;"
~~~
