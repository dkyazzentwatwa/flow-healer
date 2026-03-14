# Operations

This runbook covers live-service operation, maintenance, and recovery. It intentionally links out to the canonical docs for runtime-state semantics, evidence rules, and connector behavior instead of redefining them here.

## Canonical Companions

- [runtime-state.md](runtime-state.md): queue states, attempts, locks, safe reset guidance
- [connectors.md](connectors.md): backend routing, timeout, and fallback behavior
- [evidence-contract.md](evidence-contract.md): artifact completeness and when missing evidence blocks completion
- [healing-state-machine.md](healing-state-machine.md): how the runtime moves from claim to retry, quarantine, or PR

## Split Service Cutover

Use this runbook when Apple Flow and Flow Healer must stay always-on while remaining fully isolated with separate launch labels, DB roots, logs, and working directories.

### 1. Back up state

~~~bash
mkdir -p ~/.apple-flow/backups ~/.flow-healer/backups
cp -av ~/Documents/code/codex-flow/data/relay.db ~/.apple-flow/backups/relay.db.$(date +%Y%m%d%H%M%S).bak || true
cp -av ~/.flow-healer/repos/flow-healer-self/state.db ~/.flow-healer/backups/flow-healer-self.state.$(date +%Y%m%d%H%M%S).bak || true
~~~

### 2. Stop both services

~~~bash
launchctl stop local.flow-healer || true
launchctl stop local.apple-flow || true
~~~

### 3. Ensure launch config separation

`local.flow-healer.plist` should use:

- `Label`: `local.flow-healer`
- `WorkingDirectory`: the Flow Healer repo root
- `ProgramArguments`: the Flow Healer CLI entrypoint
- stdout and stderr paths under `~/.flow-healer/`

`local.apple-flow.plist` should use its own repo root and log paths under `~/.apple-flow/`.

### 4. Start and verify

~~~bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.apple-flow.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.flow-healer.plist 2>/dev/null || true
launchctl enable gui/$(id -u)/local.apple-flow
launchctl enable gui/$(id -u)/local.flow-healer
launchctl start local.apple-flow
launchctl start local.flow-healer
scripts/diagnose_runtime.sh ~/.flow-healer/config.yaml flow-healer-self
scripts/verify_runtime.sh ~/.flow-healer/config.yaml flow-healer-self
flow-healer --config ~/.flow-healer/config.yaml doctor --repo flow-healer-self
flow-healer --config ~/.flow-healer/config.yaml status --repo flow-healer-self
~~~

## Workspace Reconciliation

The reconciler sweeps workspace directories that are no longer associated with an active issue.

~~~bash
flow-healer start --once
~~~

Use [runtime-state.md](runtime-state.md) before manually clearing issue state, leases, or locks.

## Failure Recovery

When a healing attempt ends with `no_patch`, `verifier_failed`, `baseline_validation_blocked`, or another incident-class failure:

1. Identify the failing issue and inspect the last failure record.
2. Determine whether the blocker is runtime, issue-contract, evidence, or lane-specific.
3. Fix the underlying blocker before rerunning a controlled pass.

~~~bash
sqlite3 ~/.flow-healer/repos/demo/state.db "SELECT issue_id, attempt_id, failure_reason, failure_details, started_at FROM healer_attempts ORDER BY started_at DESC LIMIT 10;"
flow-healer start --once --repo demo
~~~

Use [agent-remediation-playbook.md](agent-remediation-playbook.md) for repeated-failure doctrine. Use [lane-guides/README.md](lane-guides/README.md) when the failure belongs to a specific fixture or browser app family.

### Infra Pause Preventing Claims

If the worker is alive but no queued issue is being claimed, check whether an infra safety pause is active before treating the queue as stalled.

~~~bash
sqlite3 ~/.flow-healer/repos/demo/state.db "SELECT key, value FROM kv_state WHERE key IN ('healer_infra_failure_streak', 'healer_infra_pause_until', 'healer_infra_pause_reason');"
flow-healer --config ~/.flow-healer/config.yaml status --repo demo
tail -n 80 ~/.flow-healer/flow-healer.log
~~~

If the pause reason points at a now-closed issue or an already-cleared runtime problem, reset the pause markers so the next tick can claim work again:

~~~bash
sqlite3 ~/.flow-healer/repos/demo/state.db "UPDATE kv_state SET value = '0' WHERE key = 'healer_infra_failure_streak';"
sqlite3 ~/.flow-healer/repos/demo/state.db "UPDATE kv_state SET value = '' WHERE key IN ('healer_infra_pause_until', 'healer_infra_pause_reason');"
~~~

Use [runtime-state.md](runtime-state.md) before manual queue-state edits. Only clear the pause after confirming the triggering blocker is resolved or intentionally bypassed.

## PR-Open Failures

When an attempt reaches `pr_open_failed`, the patch and push steps already succeeded and the failure happened while talking to GitHub.

~~~bash
flow-healer doctor --repo demo
sqlite3 ~/.flow-healer/repos/demo/state.db "SELECT issue_id, failure_class, failure_reason, started_at FROM healer_attempts WHERE failure_class = 'pr_open_failed' ORDER BY started_at DESC LIMIT 10;"
~~~

Common next checks:

- auth or token drift
- repository permissions or branch protection
- stale or duplicate PR state
- transient GitHub API or network errors

Connector failure-class semantics are documented in [connectors.md](connectors.md).

## Common Issues

### Docker not available

For Python or Node repos without usable local toolchains, configure Docker-only mode where the lane supports it:

~~~yaml
repos:
  - name: my-project
    test_gate_mode: docker_only
    local_gate_policy: skip
~~~

### Local toolchain missing

Repair the local toolchain for Swift, Go, Rust, Ruby, and Java lanes because those families do not currently rely on Docker fallback in the main model.

### Missing evidence artifacts

If the UI looks correct but verification still fails, check whether the exact named evidence files were published. The artifact naming and completeness rules live in [evidence-contract.md](evidence-contract.md).

## Monitoring

`flow-healer status --repo <repo>` includes high-value reliability surfaces such as retry metrics, reliability trends, and daily rollups. Interpret those signals together with [runtime-state.md](runtime-state.md) and [healing-state-machine.md](healing-state-machine.md) before changing retry behavior or queue policy.
