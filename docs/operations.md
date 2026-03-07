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

## Common Issues

### "Docker not available"

**Symptom**: Test gate fails with "Docker not available" or "exec: docker: not found"

**Solution**: Ensure Docker is running and accessible. For repos without local toolchains, configure Docker-only mode:

```yaml
repos:
  - name: my-project
    test_gate_mode: docker_only
    local_gate_policy: skip
```

### Local toolchain missing

**Symptom**: Tests fail because local Go/Rust/Java is not installed

**Solution**: Use `docker_only` mode to skip local testing entirely:

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
