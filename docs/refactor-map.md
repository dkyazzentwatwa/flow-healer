# Refactor Map

This doc records the intended module boundaries for future refactors so agents do not move code without a target architecture.

## Current Hotspots

- [src/flow_healer/healer_loop.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_loop.py): orchestration density, retry policy, judgment routing, swarm coordination, PR flow
- [src/flow_healer/healer_runner.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_runner.py): task execution, prompt assembly, artifact/evidence logic, app-runtime behavior
- [src/flow_healer/store.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/store.py): broad state responsibilities
- [src/flow_healer/service.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/service.py): connector construction, runtime building, status aggregation

## Intended Boundaries

- loop orchestration should own queue policy, retries, and routing decisions
- runner execution should own mutation, validation, and evidence capture behavior
- service should own runtime construction, connector routing, and aggregation for operator views
- store should remain the persistence layer, not the state-machine policy layer
- dashboard UI should consume stable control-plane payloads, not define them

## Dependency Rules

- dashboard components should not invent new control-plane semantics without matching runtime-doc updates
- lane-specific rules should live in lane docs and issue contracts, not ad hoc comments in runtime code
- connector implementations should stay transport-specific and avoid absorbing task-policy logic

## Extraction Order

If future refactors happen, prefer this order:

1. extract explicit runtime/state-machine policy seams from `healer_loop.py`
2. extract browser/evidence helpers from `healer_runner.py`
3. narrow service aggregation vs connector construction responsibilities
4. split store read models from mutation-heavy behavior only if operator clarity improves

## Non-Goals

- not a mandate to refactor immediately
- not permission to rename modules casually
- not a replacement for runtime-state or issue-contract docs
