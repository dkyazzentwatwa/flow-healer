# Dashboard

This doc defines the remaining operator-facing UI and API surface for Flow Healer after retiring the separate Next.js dashboard app.

## What Exists Today

Flow Healer now has three operator-facing surfaces:

- `flow-healer export`: primary telemetry/reporting surface that writes CSV and JSONL snapshots
- `flow-healer tui`: primary built-in live operator surface for read-only queue, attempt, event, log, and health inspection
- `flow-healer serve`: Python HTTP control plane for JSON APIs, artifact serving, and custom integrations

The old `apps/dashboard` Next.js app is retired and should not be reintroduced as a supported operator surface.
The TUI intentionally uses compact terminal panels and sparkline-style summaries inspired by tools like Chartli, Terminui, and Codex CLI, but it stays Python-native so the repo no longer depends on a separate Node UI stack.

## Canonical Anchors

- [src/flow_healer/cli.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/cli.py)
- [src/flow_healer/telemetry_exports.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/telemetry_exports.py)
- [src/flow_healer/tui.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/tui.py)
- [src/flow_healer/web_dashboard.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/web_dashboard.py)
- [src/flow_healer/dashboard_cockpit.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/dashboard_cockpit.py)

## Operator Workflows

Telemetry export:

```bash
flow-healer export --repo <repo-name>
flow-healer export --repo <repo-name> --formats csv,jsonl --output-dir /tmp/flow-healer-exports
```

Read-only terminal view:

```bash
flow-healer tui --repo <repo-name>
flow-healer tui --repo <repo-name> --once
```

Live TUI mode uses a Codex-style split layout:

- a compact repo health header
- a selectable queue pane on the left
- an inspector pane on the right with `Attempts`, `Events`, and `Logs` tabs
- a wrapped detail panel for the current selection

Keybindings:

- `↑` / `↓`: move within the active pane
- `Tab`: switch between queue and inspector panes
- `←` / `→`: switch inspector tabs
- `r`: refresh immediately
- `q`: quit

HTTP control plane:

```bash
flow-healer serve --repo <repo-name>
```

## HTTP Routes And APIs

The Python control plane remains available for custom connections and automation:

- `/`: minimal landing page describing export, TUI, and API usage
- `/api/overview`
- `/api/status`
- `/api/queue`
- `/api/issue-detail`
- `/api/activity`
- `/api/logs`
- `/api/commands`
- `/artifact`

These APIs remain control-plane/integration surfaces. They are not the primary built-in operator experience.

## Change Boundaries

Control-plane contract changes include:

- changing JSON field names or meanings in the Python API payloads
- changing artifact link formats, queue row semantics, issue-detail structure, or telemetry rollups
- changing export row shape or JSONL event payload expectations
- changing operator command behavior exposed through HTTP endpoints or CLI actions

If the change affects persisted state, queue semantics, or evidence handling, update this doc and the matching canonical runtime docs in the same change.

## Testing Expectations

When changing export or TUI behavior:

- run focused export and TUI tests
- run `pytest tests/test_cli.py -v`
- run `pytest tests/test_service.py -q`

When changing Python API payloads or artifact serving:

- run `pytest tests/test_web_dashboard.py -q`
- run `pytest tests/test_service.py -q`

## What This Doc Does Not Define

This doc does not define issue-body semantics, evidence completeness, or retry/state transitions. Use:

- [docs/issue-contracts.md](/Users/cypher-server/Documents/code/flow-healer/docs/issue-contracts.md)
- [docs/evidence-contract.md](/Users/cypher-server/Documents/code/flow-healer/docs/evidence-contract.md)
- [docs/healing-state-machine.md](/Users/cypher-server/Documents/code/flow-healer/docs/healing-state-machine.md)
