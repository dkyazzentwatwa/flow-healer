# Repository Guidelines

## Project Structure & Module Organization
Core Python code lives in `src/flow_healer/`. The CLI entry point is [`src/flow_healer/cli.py`](src/flow_healer/cli.py), while service orchestration, scanning, tracking, locks, and SQLite state handling are split into focused modules such as `service.py`, `healer_loop.py`, and `store.py`. Tests live in `tests/` and mirror the module layout with files like `test_healer_runner.py` and `test_healer_scan.py`. Use `config.example.yaml` as the template for local configuration; keep machine-specific secrets and repo paths out of version control.

## Build, Test, and Development Commands
Create a local environment and install in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Run the full test suite with `pytest`. Run a focused test with `pytest tests/test_healer_loop.py -v`. Smoke-test the CLI with `flow-healer doctor` or a one-pass run via `flow-healer start --once`. Use `flow-healer scan --dry-run` when you want to inspect scan behavior without opening issues.

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, `snake_case` for functions and modules, `PascalCase` for classes, and explicit type hints on public methods. Keep modules small and responsibility-driven, matching the current pattern of one concern per file. Prefer standard-library tools, `dataclass(slots=True)` where it improves clarity, and short docstrings only when behavior is not obvious. No formatter or linter is configured yet, so keep changes PEP 8-compliant and consistent with neighboring code.

## Testing Guidelines
Tests use `pytest` with discovery rooted at `tests/`. Name files `test_*.py` and test functions `test_*`. Add or update tests alongside any behavior change, especially around CLI commands, repo state transitions, and scanner or tracker logic. Favor small fake objects and fixtures, following `tests/conftest.py`.

## Commit & Pull Request Guidelines
This repository currently has no commit history, so use Conventional Commit-style messages such as `feat: add repo health check` or `fix: close store after scan`. Keep pull requests small and reviewable. Include a short summary, test evidence (`pytest`, CLI smoke commands), linked issues, and terminal output or screenshots when changing user-visible CLI behavior.

## Security & Configuration Tips
Do not commit tokens, local repo paths, or generated state. Store GitHub credentials in environment variables such as `GITHUB_TOKEN`, and keep runtime data under `~/.flow-healer/` as intended by the sample config.
