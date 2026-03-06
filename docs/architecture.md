# Architecture

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
   Codex Connector -> Docker Test Gate -> Verifier -> Reviewer -> PR
~~~

## Key Modules

- `src/flow_healer/cli.py`: CLI Command entrypoint.
- `src/flow_healer/service.py`: Multi-repo orchestration and polling.
- `src/flow_healer/healer_loop.py`: Main control loop for issue processing, retries, and feedback ingestion.
- `src/flow_healer/healer_scan.py`: Deterministic repository scanning for known breakage patterns.
- `src/flow_healer/healer_tracker.py`: GitHub API adapter for issues, PRs, and comments.
- `src/flow_healer/healer_workspace.py`: Manager for isolated git worktrees.
- `src/flow_healer/healer_dispatcher.py`: Handles claim logic and lock acquisition for issues.
- `src/flow_healer/healer_locks.py`: Implements path-level and coarse-grained locking.
- `src/flow_healer/healer_runner.py`: Executes the fix proposal via the AI connector.
- `src/flow_healer/healer_verifier.py`: Post-fix verification pass to ensure quality.
- `src/flow_healer/healer_reviewer.py`: Generates AI-driven code reviews for proposed fixes.
- `src/flow_healer/healer_memory.py`: Persists and retrieves lessons from prior attempts to improve future fixes.
- `src/flow_healer/healer_reconciler.py`: Cleans up expired leases, locks, and orphan workspaces.
- `src/flow_healer/store.py`: SQLite persistence for issues, attempts, lessons, and scans.

## Design Notes

- **Isolation**: Work is isolated per issue in dedicated git worktrees.
- **Safety**: Retry budgets, backoff, and circuit-breaker behavior reduce repeated unsafe attempts.
- **Iterative Healing**: PR feedback (comments from human reviewers) is monitored and incorporated into the `feedback_context` for subsequent healing attempts.
- **Stateful**: Durable state is maintained in SQLite to allow recovery across restarts.
