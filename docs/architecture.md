# Architecture

This document is the short architectural overview. Use it to orient quickly, then move to [healing-state-machine.md](healing-state-machine.md) for runtime decision flow and [refactor-map.md](refactor-map.md) for future module boundaries.

## High-Level Flow

~~~text
GitHub Issues / Repo Signals <----------------------+
            |                                       |
            v                                       |
   Flow Healer CLI + Service                        |
            |                                       |
   +--------+--------+------------------+           |
   |        |        |                  |           | (Feedback Loop)
   v        v        v                  v           |
 Scanner  Tracker  Workspace Mgr   SQLite Store     |
   |        |        |                  |           |
   +--------+--------+------------------+           |
            |                                       |
            v                                       |
      Autonomous Loop ------------------------------+
            |
   Connector -> validation -> verifier -> reviewer -> PR
~~~

## Key Modules

- `src/flow_healer/cli.py`: CLI entrypoint
- `src/flow_healer/service.py`: multi-repo orchestration and polling
- `src/flow_healer/healer_loop.py`: issue processing, retries, and feedback ingestion
- `src/flow_healer/healer_runner.py`: prompt assembly, execution-root resolution, and validation orchestration
- `src/flow_healer/healer_task_spec.py`: issue-body parsing and task-contract extraction
- `src/flow_healer/healer_tracker.py`: GitHub issues, PRs, comments, and artifact publishing
- `src/flow_healer/healer_workspace.py`: isolated git worktree management
- `src/flow_healer/healer_verifier.py`: post-fix verification and evidence checks
- `src/flow_healer/store.py`: SQLite persistence
- `src/flow_healer/web_dashboard.py`, `src/flow_healer/telemetry_exports.py`, and `src/flow_healer/tui.py`: operator API, export, and terminal surfaces

## Design Notes

- Isolation is per issue via dedicated worktrees.
- Runtime behavior is stateful and restart-safe because queue, attempt, lock, and event state lives in SQLite.
- Verification is lane-aware rather than repo-global by default.
- Browser-backed tasks may also require artifact completeness, not just passing tests.

## Read Next

- [healing-state-machine.md](healing-state-machine.md): claim, preflight, propose, validate, verify, PR, retry, quarantine
- [runtime-state.md](runtime-state.md): queue states, attempts, locks, and safe reset boundaries
- [refactor-map.md](refactor-map.md): hotspots, target seams, extraction order, and non-goals
