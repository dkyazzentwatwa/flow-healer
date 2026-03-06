# Architecture

## High-Level Flow

~~~text
GitHub Issues / Repo Signals
            |
            v
   Flow Healer CLI + Service
            |
   +--------+--------+------------------+
   |        |        |                  |
   v        v        v                  v
 Scanner  Tracker  Workspace Mgr   SQLite Store
   |        |        |                  |
   +--------+--------+------------------+
            |
            v
      Autonomous Loop
            |
   Connector -> Docker Test Gate -> Verifier -> PR
~~~

## Key Modules

- `src/flow_healer/cli.py`: command entrypoint
- `src/flow_healer/service.py`: multi-repo orchestration
- `src/flow_healer/healer_loop.py`: issue lifecycle and retries
- `src/flow_healer/healer_scan.py`: deterministic repo scanning
- `src/flow_healer/healer_tracker.py`: GitHub issues, PRs, and comments
- `src/flow_healer/store.py`: SQLite persistence for issues, attempts, lessons, and scans

## Design Notes

- Work is isolated per issue in dedicated git worktrees.
- Retry and circuit-breaker behavior reduce repeated unsafe attempts.
- PR feedback can requeue an issue for follow-up work.
- [TODO: Verify] Whether future architecture docs should include a sequence diagram for PR feedback ingestion
