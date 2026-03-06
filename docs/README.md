# Flow Healer Docs

Flow Healer is a Python CLI tool for autonomous GitHub maintenance. It watches issues, creates isolated worktrees, runs guarded fixes through an AI connector, verifies the result with pytest in Docker, and stores durable state in SQLite.

Flow Healer includes an autonomous PR feedback loop that monitors GitHub comments on open PRs and incorporates them as feedback for iterative healing attempts.

## Quick Start

~~~bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export GITHUB_TOKEN=your_token_here
flow-healer doctor
flow-healer start --once
~~~

## Doc Map

- [installation.md](installation.md): local environment setup and config
- [usage.md](usage.md): CLI flows and examples
- [architecture.md](architecture.md): control loop and module map
- [operations.md](operations.md): common maintenance tasks and troubleshooting
- [contributing.md](contributing.md): development and review expectations

## Notes

- Project type: CLI automation service
- Tech stack: Python 3.11+, SQLite, GitHub, Docker, pytest
- Target audience: repository maintainers and contributors
- Review feedback addressed: this initial docs scaffold is intended as a starting point for iterative refinement.
