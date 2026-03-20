# Flow Healer Architecture Report

## Executive Summary

Flow Healer is a local autonomous maintenance service for GitHub repositories. Its runtime combines four concerns:

1. Operator entrypoints through a CLI and an optional web, mail, and calendar control plane.
2. A multi-repository service layer that builds per-repo runtimes from shared configuration.
3. An autonomous healing loop that claims issues, creates isolated worktrees, asks a connector to produce a fix, validates the result, and opens or updates pull requests.
4. A SQLite-backed state model that preserves issue state, attempts, lessons, locks, scans, runtime health, and operator commands across restarts.

The system is intentionally not a simple "issue in, patch out" script. It behaves more like a guarded operations platform: it keeps durable state, isolates work in per-issue worktrees, uses retry and circuit-breaker controls, supports multiple connector backends, and exposes enough control surfaces for an operator to inspect or intervene without losing the execution history.

## Architectural Overview

### Core Runtime Shape

```text
GitHub issues / PRs / comments
            |
            v
     GitHubHealerTracker
            |
            v
      AutonomousHealerLoop
            |
            +--> HealerDispatcher -> leases + locks
            |
            +--> HealerWorkspaceManager -> isolated git worktrees
            |
            +--> HealerRunner -> connector turn -> staged diff -> test gate
            |
            +--> HealerVerifier / HealerReviewer -> independent judgment
            |
            +--> HealerReconciler -> stale lease, lock, workspace cleanup
            |
            v
        SQLiteStore
```

### Control Plane Shape

```text
CLI commands              Web dashboard            Mail / Calendar command pollers
     |                         |                               |
     +----------- FlowHealerService + FlowHealerServeRuntime --+
                               |
                               v
                     per-repo runtime construction
                               |
                               v
                       AutonomousHealerLoop(s)
```

## Main Components

### 1. CLI and Operator Entry Points

`src/flow_healer/cli.py` is the human-facing entrypoint. It loads config, configures logging, constructs `FlowHealerService`, and dispatches subcommands such as:

- `start` for one-shot or long-running healing
- `status` for per-repo runtime summaries
- `pause` and `resume` for operational control
- `scan` for deterministic repo scanning
- `doctor` for readiness and preflight diagnostics
- `serve` for the dashboard and Apple control plane
- `recycle-helpers` for connector helper maintenance

This keeps the CLI thin. It does not own healing logic itself; it routes into the service and serve-runtime layers.

### 2. Service Layer and Runtime Assembly

`src/flow_healer/service.py` is the composition root. Its `FlowHealerService.build_runtime()` method assembles a per-repository runtime containing:

- the repository-specific `RelaySettings`
- a `SQLiteStore`
- either a `GitHubHealerTracker` or `LocalHealerTracker`
- one or more connector implementations
- an `AutonomousHealerLoop`

This file is where backend selection and connector routing happen. It supports:

- a single connector backend for all work
- split routing where code tasks and non-code tasks use different backends
- failover behavior that falls back to `exec` when a non-exec backend is not suitable

That design matters architecturally because it separates "what work needs to happen" from "which connector should execute it."

### 3. Serve Runtime and Dashboard

`src/flow_healer/serve_runtime.py` extends the service into a long-running control plane. It:

- builds one runtime per selected repo
- starts each repo's autonomous loop as an async task
- optionally starts the dashboard server
- optionally starts Apple Mail and Calendar command pollers
- shares a `ControlRouter` so external commands can map back into the service

`src/flow_healer/web_dashboard.py` provides a lightweight HTTP dashboard using `ThreadingHTTPServer`. It exposes JSON endpoints such as:

- `/api/status`
- `/api/commands`
- `/api/logs`
- `/api/activity`
- `/api/overview`

It also renders an operator UI for monitoring and command submission. The dashboard is not a separate product tier; it is another view onto the same service state and control router.

### 4. Configuration Model

`src/flow_healer/config.py` defines two major configuration scopes:

- `ServiceSettings` for global runtime behavior, connector selection, tokens, dashboard, and control-plane defaults
- `RelaySettings` for per-repo healing policy

`RelaySettings` carries most of the operational policy surface, including:

- issue labels and trusted actors
- retry budget and backoff controls
- circuit-breaker settings
- swarm and multi-agent options
- verifier and review policy
- test gate behavior
- diff size limits
- scan behavior
- concurrency, housekeeping, and reconciliation intervals

Architecturally, this means the product is policy-driven. The healing loop reads behavior from configuration rather than baking operational choices into code paths.

## Autonomous Healing Lifecycle

### Step 1. Discover and Queue Work

The tracker layer in `src/flow_healer/healer_tracker.py` reads GitHub issues and pull-request state. `GitHubHealerTracker` is intentionally narrow: it focuses on issue listing, issue creation, issue detail lookup, PR handling, comments, and request metrics. It is not an ORM or a full GitHub abstraction layer.

Issues are filtered by required labels and trusted actors before they become candidates for healing. The loop then records or updates those issues in SQLite.

### Step 2. Claim Work Safely

`src/flow_healer/healer_dispatcher.py` handles issue claiming and lock acquisition. It delegates persistence to `SQLiteStore`, but it owns the orchestration semantics:

- claim the next eligible issue using leases
- acquire predicted lock keys before mutation
- upgrade locks if actual diff scope expands
- release locks and return issues to queue when needed

This is one of the key safety barriers in the system. It prevents overlapping autonomous edits from stepping on the same logical scope.

### Step 3. Create an Isolated Workspace

`src/flow_healer/healer_workspace.py` manages deterministic git worktrees under:

```text
<repo>/.apple-flow-healer/worktrees/
```

For each issue, it creates a stable branch and workspace path, reuses healthy worktrees when possible, and can fully prepare a workspace by:

- fetching the base branch
- resetting the issue branch to the base ref
- hard-resetting the worktree
- cleaning tracked and ignored artifacts

This isolation boundary is foundational. It lets Flow Healer reset, retry, or discard work without polluting the main checkout.

### Step 4. Parse the Task Contract

Within `src/flow_healer/healer_loop.py`, issue bodies are compiled into a structured task specification before execution. The loop uses that contract to understand:

- task kind
- output targets
- validation expectations
- scope constraints
- code-change versus artifact-only behavior

This contract then drives connector prompts, staging rules, verifier guardrails, and fallback behavior.

### Step 5. Generate a Candidate Fix

`src/flow_healer/healer_runner.py` is the execution engine for an attempt. It does substantially more than call a connector:

- binds the connector to the issue worktree
- resolves language and execution root
- builds a prompt from issue data, learned lessons, feedback context, and task spec
- selects or resets threads depending on workspace-edit mode
- runs the connector turn with retry budgets tuned to task type
- stages and filters workspace changes
- attempts structured recovery when the connector returns no direct file edits

The runner contains several important recovery paths:

- path-fenced output materialization
- artifact synthesis for report-like tasks
- unified diff extraction and application
- generated artifact cleanup before re-validation

This is the module where the product's "guarded autonomy" is most visible. The connector is treated as a proposal engine, not as a trusted actor.

### Step 6. Validate the Result

Validation is split across deterministic and model-assisted layers.

Deterministic validation in the runner uses language strategies, execution-root detection, install and test commands, and optional Docker support. The system currently has strongest first-class automation for Python and Node.js, while still parsing hints for additional ecosystems.

`src/flow_healer/healer_verifier.py` adds an independent verification pass. It asks a connector to return strict JSON with a `pass`, `soft_fail`, or `hard_fail` verdict. Its guardrails change depending on whether the task is:

- docs-only
- config-only
- standard code change
- high-risk change

This second judgment stage is designed to reduce proposer self-confirmation bias.

### Step 7. Review, Publish, and Requeue

`src/flow_healer/healer_reviewer.py` provides a reviewer persona that produces a concise technical review of the proposed fix. The broader loop uses review results, test summaries, and tracker state to decide whether to:

- open or update a PR
- request or wait for approval labels
- auto-approve or auto-merge if the repo policy allows it
- record a failure and retry with backoff
- quarantine or requeue the issue

`src/flow_healer/healer_loop.py` also contains policy for:

- failure classification and user-facing hints
- retry and backoff strategy
- circuit-breaker state
- stale-PR handling
- feedback ingestion from PR reviews and issue comments
- swarm recovery escalation for selected failure classes

In other words, the loop is not just a scheduler. It is the state machine that decides how the system behaves after each attempt.

## Deterministic Scanner Path

`src/flow_healer/healer_scan.py` is a separate ingestion path from operator-authored issues. `FlowHealerScanner` runs deterministic checks such as harness evaluations and the repo test suite, then optionally opens deduplicated GitHub issues when findings cross a configured severity threshold.

Its responsibilities include:

- recording scan runs in SQLite
- deduplicating findings against prior records and open GitHub issues
- enforcing a per-run issue budget
- skipping findings that do not match sandbox targeting constraints

This gives Flow Healer two ways to create work:

1. humans label issues as ready for healing
2. the scanner generates new issues from deterministic evidence

## Persistence and State Model

`src/flow_healer/store.py` is the durability backbone. It uses a single SQLite database per repository, with WAL mode and a thread-safe connection wrapper.

### Core Tables

| Table | Purpose |
| --- | --- |
| `healer_issues` | current issue state, leases, PR linkage, scope keys, failure status, workspace metadata |
| `healer_attempts` | attempt history, test summaries, verifier summaries, failure metadata, output targets |
| `healer_lessons` | reusable lessons and guardrails learned from prior attempts |
| `healer_locks` | logical lock keys that prevent conflicting concurrent edits |
| `scan_runs` | scan execution history |
| `scan_findings` | deduplicated deterministic findings |
| `healer_events` | operational event log |
| `healer_runtime` | singleton runtime heartbeat and health |
| `healer_mutation_log` | deduplicated mutation tracking and retry bookkeeping |
| `control_commands` | commands received from web, mail, or calendar surfaces |
| `kv_state` | generic key-value state |

### Why SQLite Matters Here

SQLite is not just a convenience store. It is the coordination substrate for:

- issue claiming
- lease expiry recovery
- attempt journaling
- lock conflict detection
- scan deduplication
- dashboard status views
- command auditing

Without the store, the service would lose most of its safety and restart resilience.

## Reconciliation and Runtime Hygiene

`src/flow_healer/healer_reconciler.py` cleans up the autonomous runtime over time. It is responsible for:

- recovering expired issue leases
- resetting stale active issues from dead workers
- interrupting inactive or superseded attempts
- cleaning up inactive and orphan workspaces
- expiring stale locks
- reaping orphan swarm subagents

This module is important because long-lived autonomous systems accumulate debris: abandoned worktrees, dead leases, locked scopes, and orphan helper processes. Reconciliation keeps those from turning into chronic false failures.

## Safety and Guardrails

Flow Healer's safety posture is distributed across modules rather than concentrated in one file.

### Isolation and Scope Control

- Work is executed inside per-issue git worktrees.
- Predicted and upgraded lock keys constrain overlapping edits.
- Task contracts and output targets narrow the allowed scope of mutation.
- Diff file and line budgets prevent oversized changes.

### Execution Guardrails

- Retry budgets are bounded.
- Failure classes drive differentiated backoff behavior.
- Circuit breakers can temporarily pause risky retry loops.
- Verification is independent from proposal generation.
- Docker is used selectively when local execution is not enough.

### Publication Guardrails

- PR mutation behavior is policy-controlled.
- Approval labels can be required before PR actions.
- Auto-approve and auto-merge are opt-in and still subject to GitHub protections.
- Review comments and feedback are ingested instead of ignored.

## Operator-Facing Surfaces

Flow Healer exposes several ways for an operator to observe or control the system:

- CLI commands from `cli.py`
- dashboard and JSON APIs from `web_dashboard.py`
- mail and calendar command pollers via `serve_runtime.py`
- status snapshots and doctor output from `service.py`

`FlowHealerService.status_rows()` is especially important because it pulls together:

- connector health
- issue counts by state
- recent attempts
- failure classification and recommended skills
- cached preflight reports

That turns the service into an inspectable system rather than a black box.

## End-to-End Sequence

```text
1. Operator or scanner creates an eligible issue.
2. FlowHealerService builds a runtime for the repo.
3. AutonomousHealerLoop syncs tracker state and claims an issue.
4. HealerDispatcher acquires leases and predicted locks.
5. HealerWorkspaceManager prepares a clean per-issue worktree.
6. HealerRunner parses the task contract, prompts the connector, and stages changes.
7. Deterministic tests and guardrails run.
8. HealerVerifier independently scores the result.
9. HealerReviewer produces review context.
10. Tracker opens or updates the PR, or the loop records failure and requeues with backoff.
11. HealerReconciler periodically cleans stale runtime artifacts.
12. Dashboard and control-plane surfaces expose status and accept operator commands.
```

## Design Strengths

- Clear separation between service composition, control plane, loop orchestration, execution, and persistence
- Strong isolation model through deterministic worktrees
- Durable operational state that survives restart and supports recovery
- Connector abstraction with routing and failover rather than a single hardcoded execution path
- Multiple guardrail layers: contracts, diff budgets, tests, verifier, reviewer, retry policy, and circuit breakers

## Architectural Risks and Tradeoffs

- `healer_loop.py` is a very large policy-heavy orchestrator, which makes it powerful but increases cognitive load and change risk.
- Connector behavior, fallback logic, and task parsing all interact in subtle ways; this creates resilience, but also makes failures harder to reason about without good observability.
- The web dashboard is intentionally lightweight, which keeps deployment simple, but means some control-plane logic is split between rendered HTML, JSON endpoints, and the router.
- SQLite is a good fit for local reliability, but it also means multi-process concurrency and lease behavior must be designed carefully, which the store and reconciler spend real effort managing.

## Conclusion

Flow Healer is best understood as a guarded autonomous repair platform for GitHub repos. The essential architectural pattern is:

- compose a per-repo runtime from configuration
- persist all important state in SQLite
- isolate each fix attempt in a git worktree
- treat the AI connector as a bounded proposal engine
- use verification, review, and retry policy to decide whether a change graduates into a PR

That combination gives the project its character. It is neither a thin CLI wrapper around an LLM nor a generic background worker. It is a stateful, operator-aware automation loop designed to keep repositories moving while staying recoverable and inspectable.
