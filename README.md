<div align="center">

# Flow Healer

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](docs/installation.md)
[![Interface](https://img.shields.io/badge/interface-CLI%20%2B%20TUI-111111?style=for-the-badge&logo=gnubash&logoColor=white)](docs/dashboard.md)
[![State](https://img.shields.io/badge/state-SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](docs/runtime-state.md)
[![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)](docs/test-strategy.md)
[![GitHub](https://img.shields.io/badge/automation-GitHub-181717?style=for-the-badge&logo=github&logoColor=white)](docs/issue-contracts.md)

**Trusted issue-to-PR automation with guarded fixes, isolated worktrees, validation gates, and an operator-first control plane.**

[Documentation](docs/README.md) · [Installation](docs/installation.md) · [Usage](docs/usage.md) · [Dashboard](docs/dashboard.md) · [Operations](docs/operations.md)

</div>

## Why Flow Healer

Flow Healer helps repositories automate issue-driven repairs without turning the repo into an opaque agent sandbox. It watches GitHub issues, creates isolated worktrees, asks the configured connector to propose a fix, runs validation gates, verifies artifacts and evidence when needed, and only then opens or updates a pull request.

It is built as an operations loop, not just a patch generator. Durable SQLite state, retry and quarantine handling, feedback ingestion, lane-aware validation, and export-first operator visibility are all first-class parts of the product.

## What It Does

- Monitors one or many repositories from a single config file.
- Processes only issues that match the repo's required labels, `healer:ready` by default.
- Parses issue bodies into an explicit task contract: outputs, input-only context, execution root, runtime profile, evidence requirements, and validation commands.
- Creates isolated git worktrees per attempt.
- Runs guarded local and Docker-backed validation where the lane supports it.
- Tracks queue state, attempts, locks, lessons, events, and runtime health in SQLite.
- Opens or updates PRs only after verification and evidence checks pass.
- Re-queues work when humans leave PR feedback comments.
- Exposes export-first telemetry, a built-in read-only TUI, and a Python control plane for operator visibility and integrations.

## Start Here

- [docs/README.md](docs/README.md): canonical documentation index
- [docs/issue-contracts.md](docs/issue-contracts.md): issue-body semantics and scope rules
- [docs/healing-state-machine.md](docs/healing-state-machine.md): claim-to-resolution runtime flow
- [docs/runtime-state.md](docs/runtime-state.md): SQLite state model, attempts, and locks
- [docs/dashboard.md](docs/dashboard.md): dashboard and control-plane boundaries
- [docs/lane-guides/README.md](docs/lane-guides/README.md): lane-safe editing guides for `e2e-smoke/` and `e2e-apps/`
- [docs/evidence-contract.md](docs/evidence-contract.md): browser artifact and evidence rules
- [AGENTS.md](AGENTS.md): coding-agent operating contract for this repo

## Core Workflow

```text
GitHub issue labeled healer:ready
                |
                v
      Flow Healer claims work
                |
                v
  Issue body becomes a task contract:
  outputs, context, execution root,
  runtime profile, evidence, validation
                |
                v
  Isolated worktree + connector attempt
                |
                v
    Local and/or Docker validation
                |
                v
   Verifier + evidence completeness
                |
        +-------+-------+
        |               |
        v               v
   open/update PR    retry, quarantine,
   and await review  or clarification
```

For the full decision flow, read [docs/healing-state-machine.md](docs/healing-state-machine.md). For the durable state model behind retries, claims, and locks, read [docs/runtime-state.md](docs/runtime-state.md).

## Documentation Model

The repo now separates product overview from canonical operating docs:

- `README.md` is the short product-facing overview.
- [docs/README.md](docs/README.md) is the canonical index.
- [docs/issue-contracts.md](docs/issue-contracts.md), [docs/evidence-contract.md](docs/evidence-contract.md), [docs/runtime-state.md](docs/runtime-state.md), and [docs/healing-state-machine.md](docs/healing-state-machine.md) define how the system is expected to operate.
- [docs/lane-guides/README.md](docs/lane-guides/README.md) defines how to work safely inside `e2e-smoke/` and `e2e-apps/`.
- Planning documents under [docs/plans/](docs/plans/) are historical references, not the source of truth for current behavior.

## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
mkdir -p ~/.flow-healer
cp config.example.yaml ~/.flow-healer/config.yaml
export GITHUB_TOKEN=your_token_here
flow-healer doctor
flow-healer start --once
flow-healer status
```

## Development

High-value verification commands:

```bash
pytest tests/test_healer_task_spec.py -v
pytest tests/test_healer_runner.py -v
pytest tests/test_healer_loop.py -v
pytest tests/e2e/test_flow_healer_e2e.py -k mixed_repo_sandbox -v
python scripts/validate_repro_contract_examples.py
python scripts/check_harness_doc_drift.py
```
