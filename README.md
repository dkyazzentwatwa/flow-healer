<div align="center">

# Flow Healer

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](docs/installation.md)
[![Interface](https://img.shields.io/badge/interface-CLI%20%2B%20TUI-111111?style=for-the-badge&logo=gnubash&logoColor=white)](docs/dashboard.md)
[![State](https://img.shields.io/badge/state-SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](docs/runtime-state.md)
[![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)](docs/test-strategy.md)
[![GitHub](https://img.shields.io/badge/automation-GitHub-181717?style=for-the-badge&logo=github&logoColor=white)](docs/issue-contracts.md)

**Flow Healer opens draft PRs for flaky tests and safe repo maintenance issues — with validation evidence attached — so you can review, approve, or retry in one place.**

[Get Started in 15 Minutes →](docs/onboarding.md) · [MVP Scope](docs/mvp.md) · [Operator Guide](docs/operator-workflow.md) · [Safe Scope Contract](docs/safe-scope.md)

</div>

## What It Does

Flow Healer watches your GitHub issues labeled `healer:ready`, proposes a fix, runs validation, and opens a draft PR with evidence attached. You review and decide.

```text
GitHub issue (healer:ready)
         │
         ▼
  Flow Healer claims it
         │
         ▼
  AI connector proposes fix
         │
         ▼
  Validation runs (local / Docker)
         │
         ▼
  Evidence bundle built
    ┌────┴────┐
    ▼         ▼
Draft PR    retry / clarify
opened      (operator notified)
```

## Issue Classes Supported

**Class A — Flaky Test Repair:** Fix intermittently failing tests. Output targets must be test files only.

**Class B — Safe CI / Config / Doc Fixes:** Fix `.github/`, `Makefile`, `pyproject.toml`, `requirements*.txt`, `*.md`, and similar safe files.

Both classes require an explicit `Required code outputs` section and a `Validation command` in the issue body. See [docs/safe-scope.md](docs/safe-scope.md) for the full contract.

## Get Started

```bash
pip install flow-healer
mkdir -p ~/.flow-healer
cp config.example.yaml ~/.flow-healer/config.yaml
# edit config.yaml with your repo path and slug
export GITHUB_TOKEN=ghp_your_token
flow-healer doctor
flow-healer start --once
```

Read the [15-minute onboarding guide](docs/onboarding.md) for a full walkthrough.

## Operator Interface

```bash
# Terminal UI — review queue, retry, open PRs
flow-healer tui

# CLI status
flow-healer status

# Diagnose setup issues
flow-healer doctor
```

The TUI shows a **Review Queue** of draft PRs ready to approve, a **Blocked** tab for failures needing attention, and a **Repo Health** tab.

## Not Magic

- All state is local SQLite (`~/.flow-healer/repos/<name>/state.db`)
- All fixes are auditable — every diff and validation run is in the PR body
- No production code changes without explicit issue contracts
- You approve every merge

## Documentation

- [docs/onboarding.md](docs/onboarding.md) — 15-minute setup guide
- [docs/haiku.md](docs/haiku.md) — Claude Haiku configuration and usage
- [docs/agentic-coding.md](docs/agentic-coding.md) — AI agent capabilities and connectors
- [docs/mvp.md](docs/mvp.md) — what's in scope at MVP
- [docs/safe-scope.md](docs/safe-scope.md) — file scope rules and examples
- [docs/operator-workflow.md](docs/operator-workflow.md) — TUI / CLI operator guide
- [docs/README.md](docs/README.md) — full documentation index
- [AGENTS.md](AGENTS.md) — coding-agent operating contract

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
flow-healer doctor
flow-healer start --once
```
