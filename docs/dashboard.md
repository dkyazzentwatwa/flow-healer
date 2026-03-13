# Dashboard

This doc defines the operator-facing dashboard surface for Flow Healer and the contract around changing it safely.

## What Exists Today

Flow Healer currently has two dashboard surfaces:

- The legacy Python dashboard in [src/flow_healer/web_dashboard.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/web_dashboard.py), served by `flow-healer serve` and the always-on runtime.
- The Next.js dashboard app in [apps/dashboard](/Users/cypher-server/Documents/code/flow-healer/apps/dashboard), which is the modern operator UI and the preferred surface for product-facing dashboard work.

Use the Python dashboard as the control-plane reference and fallback surface. Use the Next app for ongoing UI work unless the change explicitly targets the embedded Python dashboard.

## Canonical Anchors

- [src/flow_healer/web_dashboard.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/web_dashboard.py)
- [apps/dashboard/src/lib/flow-healer.ts](/Users/cypher-server/Documents/code/flow-healer/apps/dashboard/src/lib/flow-healer.ts)
- [apps/dashboard/app/api/flow-healer/[...path]/route.ts](/Users/cypher-server/Documents/code/flow-healer/apps/dashboard/app/api/flow-healer/[...path]/route.ts)
- [apps/dashboard/app/operations/page.tsx](/Users/cypher-server/Documents/code/flow-healer/apps/dashboard/app/operations/page.tsx)
- [apps/dashboard/app/telemetry/page.tsx](/Users/cypher-server/Documents/code/flow-healer/apps/dashboard/app/telemetry/page.tsx)
- [apps/dashboard/app/artifacts/page.tsx](/Users/cypher-server/Documents/code/flow-healer/apps/dashboard/app/artifacts/page.tsx)
- [apps/dashboard/app/settings/page.tsx](/Users/cypher-server/Documents/code/flow-healer/apps/dashboard/app/settings/page.tsx)

## Running The Dashboards

Legacy Python dashboard:

```bash
flow-healer serve --repo <repo-name>
```

Next dashboard app:

```bash
cd apps/dashboard
npm install
npm run dev
```

The Next app defaults to port `3099` and proxies Flow Healer runtime data through `/api/flow-healer/*`.

## Data Flow And Fallback Behavior

The Next app fetches live data through [apps/dashboard/src/lib/flow-healer.ts](/Users/cypher-server/Documents/code/flow-healer/apps/dashboard/src/lib/flow-healer.ts). That library has two modes:

- `live`: runtime fetch succeeds and the UI renders current queue, overview, issue-detail, and artifact data.
- `fallback`: fetch fails and the UI renders built-in demo payloads so the shell stays usable during local UI development or when the runtime is offline.

The Python dashboard is always live against the in-process service runtime. It is the source of truth for payload semantics and endpoint behavior.

## Route Map

Next dashboard routes:

- `/operations`: issue queue, workbench, and issue drill-down workflows
- `/telemetry`: repo status, reliability signals, and trend summaries
- `/artifacts`: published evidence browsing and artifact-focused triage
- `/settings`: local configuration and operator controls

Python dashboard routes and APIs:

- `/`: rendered HTML dashboard shell
- `/api/overview`
- `/api/status`
- `/api/queue`
- `/api/issue-detail`
- `/api/activity`
- `/api/logs`
- `/api/commands`
- `/artifact`

## Safe UI Change vs Control-Plane Change

Safe UI-only changes:

- typography, spacing, layout, cards, labels, and component composition inside `apps/dashboard`
- route-local presentation tweaks that do not change payload expectations
- fallback/demo content updates that preserve the same data shape

Control-plane contract changes:

- changing JSON field names or meanings in the Python dashboard payloads
- changing the proxy route behavior or error semantics
- changing artifact link formats, queue row semantics, issue-detail structure, or telemetry rollups
- changing operator command behavior exposed through dashboard actions

If a change is control-plane-facing, update this doc plus [docs/runtime-state.md](/Users/cypher-server/Documents/code/flow-healer/docs/runtime-state.md), [docs/healing-state-machine.md](/Users/cypher-server/Documents/code/flow-healer/docs/healing-state-machine.md), or [docs/evidence-contract.md](/Users/cypher-server/Documents/code/flow-healer/docs/evidence-contract.md) as appropriate.

## Testing Expectations

When changing `apps/dashboard`:

- run `cd apps/dashboard && npm test`
- run the focused dashboard route and component tests when behavior changes
- verify live/fallback behavior if the change touches `src/lib/flow-healer.ts`

When changing Python dashboard payloads:

- run `pytest tests/test_web_dashboard.py -q`
- run `pytest tests/test_service.py -q` if the payload source changes

## What This Doc Does Not Define

This doc does not define issue-body semantics, evidence completeness, or retry/state transitions. Use:

- [docs/issue-contracts.md](/Users/cypher-server/Documents/code/flow-healer/docs/issue-contracts.md)
- [docs/evidence-contract.md](/Users/cypher-server/Documents/code/flow-healer/docs/evidence-contract.md)
- [docs/healing-state-machine.md](/Users/cypher-server/Documents/code/flow-healer/docs/healing-state-machine.md)
