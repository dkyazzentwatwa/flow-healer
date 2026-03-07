# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable + dev deps)
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

# Run all tests
pytest

# Run a focused test
pytest tests/test_healer_loop.py -v

# Run a single test function
pytest tests/test_healer_loop.py::test_function_name -v

# CLI smoke tests
flow-healer doctor
flow-healer start --once
flow-healer scan --dry-run
flow-healer serve
```

## Architecture

Flow Healer is a multi-repo autonomous healing service. It polls GitHub for labeled issues, feeds them to an AI connector (default: `codex` CLI), and opens PRs only when fixes pass verification.

**Control flow:**
```
GitHub Issues → FlowHealerService (service.py)
                        ↓
              AutonomousHealerLoop (healer_loop.py)
                        ↓
  HealerDispatcher → HealerRunner → HealerVerifier → HealerReviewer → PR
  (claims + locks)   (AI connector)  (post-fix check)  (AI review)
```

**Key module responsibilities:**

| Module | Role |
|---|---|
| `cli.py` | CLI entry point (`flow-healer` command) |
| `service.py` | Multi-repo orchestration, builds `RepoRuntime` per repo |
| `healer_loop.py` | Main control loop: retries, circuit breaker, feedback ingestion |
| `healer_runner.py` | Executes fix via `ConnectorProtocol`; applies patch to worktree |
| `healer_verifier.py` | Post-fix verification (test gate: local then Docker) |
| `healer_reviewer.py` | AI-driven code review of proposed fixes |
| `healer_dispatcher.py` | Claim logic and lock acquisition for issues |
| `healer_locks.py` | Path-level and coarse-grained locking |
| `healer_reconciler.py` | Cleanup expired leases, locks, orphan workspaces |
| `healer_workspace.py` | Isolated git worktrees per issue |
| `healer_tracker.py` | GitHub API adapter (issues, PRs, comments) |
| `healer_scan.py` | Deterministic repo scanning for known breakage patterns |
| `healer_task_spec.py` | Compiles issue title/body into structured `HealerTaskSpec` |
| `healer_triage.py` | Classifies issues to skill routes via `DiagnosisRoute` |
| `healer_memory.py` | Persists/retrieves lessons from prior attempts |
| `skill_contracts.py` | Validates skill YAML contracts (inputs, outputs, stop conditions) |
| `language_detector.py` | Detects repo language from marker files |
| `language_strategies.py` | Per-language test commands and Docker images |
| `protocols.py` | `ConnectorProtocol` interface (implemented by `codex_cli_connector.py`) |
| `store.py` | SQLite persistence (`~/.flow-healer/repos/<name>/state.db`) |
| `control_plane.py` | Command dispatch for web/mail/calendar control |
| `web_dashboard.py` | Web dashboard (default port 8787) |
| `apple_pollers.py` | Apple Mail + Calendar polling with `FH: <cmd>` subject DSL |
| `serve_runtime.py` | Orchestrates healer loop + web + pollers under `flow-healer serve` |

**Config:** `~/.flow-healer/config.yaml` (see `config.example.yaml`). Per-repo state in `~/.flow-healer/repos/<name>/state.db`.

## Coding Style

- All files use `from __future__ import annotations` at the top.
- `dataclass(slots=True, frozen=True)` for immutable value objects; `dataclass(slots=True)` for mutable state holders.
- 4-space indentation, `snake_case` for functions/variables, `PascalCase` for classes.
- No formatter or linter configured — keep changes PEP 8-compliant.

## Testing Patterns

Tests use `pytest` with shared fakes in `tests/conftest.py`:
- `FakeConnector` — implements `ConnectorProtocol` for unit tests
- `FakeStore` — full in-memory implementation of the `SQLiteStore` interface
- `FakeEgress` — captures outbound messages

Prefer these fakes over mocks. Do not rely on real GitHub tokens, real git repos, or the `codex` binary in unit tests — integration/e2e tests live under `tests/e2e/`.

## Skills

The `skills/` directory contains Claude Code skills (YAML + scripts) consumed by the healer. `skill_contracts.py` validates their structure at runtime. Skills must define `## Inputs`, `## Outputs`, `## Key Output Fields`, `## Success Criteria`, `## Failure Handling`, and `## Next Step` sections.
