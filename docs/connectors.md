# Connectors

This doc explains which AI connectors Flow Healer can use and how routing works.

## Canonical Anchors

- [src/flow_healer/service.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/service.py)
- [src/flow_healer/codex_cli_connector.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/codex_cli_connector.py)
- [src/flow_healer/codex_app_server_connector.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/codex_app_server_connector.py)
- [src/flow_healer/claude_cli_connector.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/claude_cli_connector.py)
- [src/flow_healer/cline_connector.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/cline_connector.py)
- [src/flow_healer/kilo_cli_connector.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/kilo_cli_connector.py)
- [src/flow_healer/fallback_connector.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/fallback_connector.py)

## Available Backends

- `exec`: Codex CLI execution path and the default code-oriented lane
- `app_server`: Codex app-server transport
- `claude_cli`
- `cline`
- `kilo_cli`

The service can also wrap non-exec backends in failover behavior so they fall back to `exec` for safety.

## Routing Model

Connector selection is built in [src/flow_healer/service.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/service.py).

Important modes:

- single backend mode: one backend handles all tasks
- `exec_for_code` routing: code-heavy tasks can use one backend while non-code tasks use another
- failover wrapper: unsupported or unstable non-exec paths can fall back to `exec`

## Operational Expectations

- connector health must be probeable before consuming attempt budget
- runtime/path drift under `launchd` is a common source of connector failure
- connector behavior is constrained by Flow Healer's issue contracts and staging rules, not by freeform model behavior

## Common Failure Modes

- connector unavailable
- connector runtime error
- malformed diff or no patch
- commentary-only or narrative-only output
- transport-specific startup or environment drift

When diagnosing connector failures, pair this doc with:

- [docs/operations.md](/Users/cypher-server/Documents/code/flow-healer/docs/operations.md)
- [docs/agent-remediation-playbook.md](/Users/cypher-server/Documents/code/flow-healer/docs/agent-remediation-playbook.md)

## What This Doc Does Not Define

This doc explains backend selection and runtime behavior. It does not define issue semantics or lane scope; use:

- [docs/issue-contracts.md](/Users/cypher-server/Documents/code/flow-healer/docs/issue-contracts.md)
- [docs/lane-guides/README.md](/Users/cypher-server/Documents/code/flow-healer/docs/lane-guides/README.md)
