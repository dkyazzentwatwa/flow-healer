# Connectors

This doc explains how Flow Healer selects, health-checks, and falls back between AI connectors.

## Canonical Anchors

- [src/flow_healer/config.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/config.py)
- [src/flow_healer/service.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/service.py)
- [src/flow_healer/healer_loop.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_loop.py)
- [src/flow_healer/healer_preflight.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_preflight.py)
- [src/flow_healer/codex_app_server_connector.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/codex_app_server_connector.py)
- [src/flow_healer/codex_cli_connector.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/codex_cli_connector.py)
- [src/flow_healer/fallback_connector.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/fallback_connector.py)
- [src/flow_healer/claude_cli_connector.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/claude_cli_connector.py)
- [src/flow_healer/cline_connector.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/cline_connector.py)
- [src/flow_healer/kilo_cli_connector.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/kilo_cli_connector.py)

## Supported Backends

Service config normalizes these connector backends:

- `app_server`: Codex `app-server` over local stdio JSON-RPC
- `exec`: Codex CLI `exec`
- `claude_cli`
- `cline`
- `kilo_cli`
- `gemini_cli`

The service default is:

- `connector_backend: app_server`
- `connector_routing_mode: single_backend`

## Routing Modes

Connector routing is built in [service.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/service.py).

### `single_backend`

One backend handles all tasks. If that backend is not `exec`, `app_server`, or `gemini_cli`, the service wraps it in [FailoverConnector](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/fallback_connector.py) so `exec` can catch connector-unavailable and connector-runtime failures.

### `exec_for_code`

Flow Healer keeps separate backends for code and non-code work:

- `code_connector_backend`
- `non_code_connector_backend`

In this mode, non-`exec` and non-`app_server` backends are wrapped with an `exec` fallback. Backend choice at run time is then made in [healer_loop.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_loop.py) based on task classification.

## Health Model

Every connector participates in a health contract:

- `ensure_started()`
- `get_or_create_thread()`
- `reset_thread()`
- `run_turn()`
- optional `health_snapshot()`

The loop records connector health into repo state before claims and can skip a claim cycle if the selected connector is unavailable. Attempt-time preflight also probes the selected backend before spending issue budget on a broken runtime.

## Codex App-Server Behavior

[CodexAppServerConnector](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/codex_app_server_connector.py):

- launches `codex app-server --listen stdio://`
- tracks sender-to-thread IDs
- restarts when the workspace changes
- reports runtime errors with structured health fields
- can perform explicit exec failover through a lazily created `CodexCliConnector`

This backend is stateful and is the main long-lived connector path.

## Codex Exec Behavior

[CodexCliConnector](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/codex_cli_connector.py):

- shells out to `codex exec --skip-git-repo-check --yolo`
- performs lightweight cached `--version` liveness checks
- resolves `service.connector_command` from PATH or common install paths
- returns `ConnectorUnavailable:` or `ConnectorRuntimeError:`-prefixed text on transport/runtime failures

That prefixing matters because the fallback wrapper keys off those exact failure prefixes.

## Failover Rules

[FailoverConnector](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/fallback_connector.py) retries on the secondary backend only when the primary output starts with:

- `ConnectorUnavailable:`
- `ConnectorRuntimeError:`

It does not reinterpret ordinary model output as transport failure.

The health snapshot also surfaces:

- fallback backend name
- whether fallback is currently available
- fallback attempt and success counts
- the last fallback trigger reason

## Common Failure Classes

The runtime and runner normalize connector failures into operator-facing classes such as:

- `connector_unavailable`
- `connector_runtime_error`
- `pr_open_failed` for GitHub-side PR operations after patching succeeded

Connector runtime failures are infrastructure failures, not issue-contract failures. The retry playbook and infra pause logic treat them differently from code or scope failures.

## Operational Notes

- absolute connector paths are safer under `launchd`
- command resolution drift is a common cause of `connector_unavailable`
- connector health is cached and recorded into repo state for status and doctor surfaces
- app-server and fallback metrics are persisted for operator inspection

When debugging repeated connector failures, pair this doc with [docs/operations.md](/Users/cypher-server/Documents/code/flow-healer/docs/operations.md) and [docs/agent-remediation-playbook.md](/Users/cypher-server/Documents/code/flow-healer/docs/agent-remediation-playbook.md).

## Testing Expectations

When connector routing or semantics change, run the focused config and loop coverage that exercises backend selection and failure handling:

```bash
pytest tests/test_config.py -v
pytest tests/test_healer_loop.py -v
```

Add backend-specific tests when a connector changes its health snapshot, restart, or failover behavior.

## What This Doc Does Not Define

This doc does not define issue parsing or lane-safe mutation scope. Use:

- [docs/issue-contracts.md](/Users/cypher-server/Documents/code/flow-healer/docs/issue-contracts.md)
- [docs/lane-guides/README.md](/Users/cypher-server/Documents/code/flow-healer/docs/lane-guides/README.md)
- [docs/healing-state-machine.md](/Users/cypher-server/Documents/code/flow-healer/docs/healing-state-machine.md)
