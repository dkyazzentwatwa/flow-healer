# Flow Healer Docs

This index is the canonical entrypoint for Flow Healer documentation. Use it to orient both operators and coding agents before changing runtime behavior, issue contracts, dashboard surfaces, evidence handling, or lane-specific fixtures.

## Start Here

- [installation.md](installation.md): local setup and config bootstrap
- [usage.md](usage.md): CLI workflows, controlled runs, and operator entrypoints
- [operations.md](operations.md): live-service runbooks, incident handling, and maintenance
- [test-strategy.md](test-strategy.md): testing pyramid and which regression to add when behavior escapes

## Canonical Docs

These documents define current repo behavior and should be updated in the same change when that behavior changes.

### Operator Runtime

- [runtime-state.md](runtime-state.md): SQLite state model, queue states, attempts, locks, and safe resets
- [healing-state-machine.md](healing-state-machine.md): issue claim-to-resolution decision flow
- [connectors.md](connectors.md): backend routing, timeout, and fallback policy
- [evidence-contract.md](evidence-contract.md): browser evidence completeness, artifact naming, and blocking rules

### Agent Contracts

- [issue-contracts.md](issue-contracts.md): canonical issue-body semantics and scope rules
- [agent-remediation-playbook.md](agent-remediation-playbook.md): how repeated failures should become docs, contract, fixture, and guardrail fixes
- [test-strategy.md](test-strategy.md): where to add coverage when harness behavior changes

### Lane Guides

- [lane-guides/README.md](lane-guides/README.md): lane-guide index and shared expectations
- [lane-guides/browser-apps.md](lane-guides/browser-apps.md): browser-backed app targets
- [lane-guides/node-smoke.md](lane-guides/node-smoke.md): JS and Node smoke families
- [lane-guides/python-smoke.md](lane-guides/python-smoke.md): Python web, data, and ML smoke families
- [lane-guides/ruby-smoke.md](lane-guides/ruby-smoke.md): Ruby smoke fixtures
- [lane-guides/java-gradle-smoke.md](lane-guides/java-gradle-smoke.md): Java Gradle smoke fixtures
- [lane-guides/go-smoke.md](lane-guides/go-smoke.md): Go smoke fixtures
- [lane-guides/rust-smoke.md](lane-guides/rust-smoke.md): Rust smoke fixtures
- [lane-guides/swift-smoke.md](lane-guides/swift-smoke.md): Swift smoke fixtures

### UI / Control Plane

- [dashboard.md](dashboard.md): Next dashboard vs legacy Python dashboard, routes, data sources, and safe edit boundaries
- [app-target-onboarding.md](app-target-onboarding.md): how to add a browser-backed app target or runtime profile
- [fixture-profile-guidance.md](fixture-profile-guidance.md): deterministic auth, fixture, and environment guidance for browser-backed apps

### Architecture

- [architecture.md](architecture.md): short architectural overview and module map
- [refactor-map.md](refactor-map.md): target seams, hotspots, and extraction order

## Supporting References

- [contributing.md](contributing.md): contributor expectations
- [harness-reliability-runbook.md](harness-reliability-runbook.md): focused browser-harness operations guidance
- [harness-smoke-checklist.md](harness-smoke-checklist.md): smoke validation checklist
- [harness-repro-contract-examples.json](harness-repro-contract-examples.json): issue-contract examples used by validation helpers
- [e2e/reliability-runbook.md](e2e/reliability-runbook.md): end-to-end reliability retest guidance

## Historical Plans And Archives

These files remain useful as background, but they are not canonical sources of current behavior.

- [plans/](plans/): historical planning and execution checklists
- [archive/README.md](archive/README.md): archived reviews, smoke notes, and prior planning material

## Quick Start

~~~bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export GITHUB_TOKEN=your_token_here
flow-healer doctor
flow-healer start --once
~~~
