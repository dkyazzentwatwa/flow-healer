# Flow Healer: Autonomous Repository Maintenance

Flow Healer is an autonomous service designed to maintain GitHub repositories by scanning for breakage, proposing fixes using AI, and opening verified pull requests. It prioritizes safety through isolated worktrees, Docker-backed test gates, and a robust retry/circuit-breaker system.

## Project Overview

- **Core Purpose:** Automate the end-to-end lifecycle of repository healing (detect -> triage -> fix -> verify -> PR).
- **Key Technologies:**
    - **Language:** Python 3.11+
    - **State Management:** SQLite (located in `~/.flow-healer/` by default).
    - **AI Backend:** Codex (via CLI or `app-server` backend).
    - **Isolation:** Git worktrees for per-issue workspaces.
    - **Testing:** Docker-based test gates for Python/Node, local toolchains for Swift.
- **Architecture:**
    - `Scanner`: Deterministic scanning for known issues.
    - `Tracker`: GitHub API adapter for managing issues and PRs.
    - `Healer Loop`: Orchestrates the claim-fix-verify-PR lifecycle.
    - `Workspace Manager`: Handles isolated worktree creation and cleanup.
    - `Memory Service`: Learns from past failures to improve future attempts.
    - `Control Plane`: Supports CLI, Web Dashboard, and Apple Mail/Calendar DSL.

## Building and Running

### Setup
1. **Environment:** Create a virtual environment and install in editable mode.
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e '.[dev]'
   ```
2. **Configuration:** Copy `config.example.yaml` to `~/.flow-healer/config.yaml` and configure your repositories and GitHub token.
3. **Authentication:** Export `GITHUB_TOKEN`.

### Key Commands
- `flow-healer doctor`: Validate setup, toolchains, and connector health.
- `flow-healer status`: View active issues, circuit breaker state, and recent attempts.
- `flow-healer start [--once]`: Run the autonomous healing loop.
- `flow-healer scan [--repo NAME] [--dry-run]`: Trigger repository scanners.
- `flow-healer serve`: Launch the web dashboard and remote control pollers.
- `flow-healer pause/resume`: Control autonomous processing.

### Testing
- **Run all tests:** `pytest`
- **Run focused tests:** `pytest tests/test_healer_loop.py -v`

## Development Conventions

- **Stateful Persistence:** All durable state (issues, attempts, lessons) must be stored in the SQLite `store.py`.
- **Isolation:** Never perform work directly in the main repository path; always use `HealerWorkspaceManager` to create a worktree.
- **Safety First:** Adhere to retry budgets and circuit breaker logic defined in `healer_loop.py`. Infrastructure failures should trigger backoffs rather than exhausting retry budgets.
- **Idempotency:** Mutations to GitHub (PRs, comments) should be keyed and idempotent where possible.
- **Language Support:** Core execution support is limited to Python, Node.js, and Swift. Ensure new logic respects the `language_strategies.py`.
- **Learning:** Utilize `HealerMemoryService` to provide context from previous failures to the AI connector.
- **Verification:** Every fix must pass `HealerVerifier` before a PR is opened.
