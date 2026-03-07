# Repository Guidelines

## Project Structure & Module Organization
Core Python code lives in `src/flow_healer/`. The CLI entry point is [`src/flow_healer/cli.py`](src/flow_healer/cli.py), while service orchestration, scanning, tracking, locks, and SQLite state handling are split into focused modules such as `service.py`, `healer_loop.py`, and `store.py`. Tests live in `tests/` and mirror the module layout with files like `test_healer_runner.py` and `test_healer_scan.py`. Use `config.example.yaml` as the template for local configuration; keep machine-specific secrets and repo paths out of version control.

## Fast Handoff For New Agents
Current work has been focused on prompt reliability and issue-driven execution routing. If you need to pick up quickly, start with these files:

- `src/flow_healer/healer_task_spec.py`: parses issue title/body into task kind, output targets, input-only context, language hints, execution root, and validation commands.
- `src/flow_healer/healer_runner.py`: assembles the proposer prompt, resolves effective language and execution root, stages model output, and runs validation gates.
- `src/flow_healer/language_detector.py` and `src/flow_healer/language_strategies.py`: repo-level language detection plus per-language local/docker test commands.
- `tests/test_healer_task_spec.py`, `tests/test_healer_runner.py`, and `tests/e2e/test_flow_healer_e2e.py`: the clearest source of truth for intended issue-body formats and mixed-language sandbox behavior.

The current prompt-improvement direction is low-risk cleanup, not a connector redesign. Keep the existing `codex exec` flow, but make prompt sections clearer, reduce duplicated instructions, and tighten task-specific execution rules.

## Build, Test, and Development Commands
Create a local environment and install in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Run the full test suite with `pytest`. Run a focused test with `pytest tests/test_healer_loop.py -v`. Smoke-test the CLI with `flow-healer doctor` or a one-pass run via `flow-healer start --once`. Use `flow-healer scan --dry-run` when you want to inspect scan behavior without opening issues.

### High-Value Focused Tests
When working on issue parsing, prompt assembly, or language-aware validation, prefer these targeted test slices before running the whole suite:

```bash
pytest tests/test_healer_task_spec.py -v
pytest tests/test_healer_runner.py -v
pytest tests/e2e/test_flow_healer_e2e.py -k mixed_repo_sandbox -v
```

These cover:

- issue-body parsing into language, execution root, and validation commands
- prompt contract rendering and proposer instructions
- end-to-end issue-scoped language routing in mixed-language sandbox repos

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, `snake_case` for functions and modules, `PascalCase` for classes, and explicit type hints on public methods. Keep modules small and responsibility-driven, matching the current pattern of one concern per file. Prefer standard-library tools, `dataclass(slots=True)` where it improves clarity, and short docstrings only when behavior is not obvious. No formatter or linter is configured yet, so keep changes PEP 8-compliant and consistent with neighboring code.

## Testing Guidelines
Tests use `pytest` with discovery rooted at `tests/`. Name files `test_*.py` and test functions `test_*`. Add or update tests alongside any behavior change, especially around CLI commands, repo state transitions, and scanner or tracker logic. Favor small fake objects and fixtures, following `tests/conftest.py`.

## GitHub Issue Format For Language Tests
Flow Healer can infer execution root and language directly from the GitHub issue body. This is the fastest way to drive language-specific runs, especially in mixed-language repos or `e2e-smoke/` sandboxes.

Use this pattern in issues:

```md
Required code outputs:
- e2e-smoke/node/src/add.js
- e2e-smoke/node/test/add.test.js

Validation:
- cd e2e-smoke/node && npm test -- --passWithNoTests
```

Important behaviors:

- The required trigger label is `healer:ready` unless the repo config overrides `issue_required_labels`.
- Issue-scoped language hints beat repo-wide `language` config when the issue body clearly points at a language or validation command.
- `Validation:` lines are parsed for commands like `pytest`, `npm test`, `go test`, `cargo test`, `mvn test`, `./gradlew test`, and `bundle exec rspec`.
- Paths under `e2e-smoke/<language>/...` also help infer the execution root and language.
- Targeted test inference currently matters most for Python and Ruby. Other languages usually run the full configured validation command.
- If you want a repo file treated as reference material instead of an output target, mark it as input-only context in the issue body.

Useful issue-body examples:

```md
Fix the bug in e2e-smoke/ruby/add.rb and keep the sandbox green.
Validation: cd e2e-smoke/ruby && bundle exec rspec
```

```md
Required code outputs:
- e2e-smoke/java-gradle/src/main/java/example/App.java

Validation:
- cd e2e-smoke/java-gradle && ./gradlew test --no-daemon
```

## GH CLI Workflow
Prefer `gh` for creating, inspecting, and relabeling issues that should drive Flow Healer.

Inspect an issue before making assumptions:

```bash
gh issue view <number> --json title,body,labels
```

List candidate issues waiting for the healer:

```bash
gh issue list --label healer:ready --state open
```

Create a healer-ready issue directly from the terminal:

```bash
gh issue create \
  --title "Node sandbox regression" \
  --label healer:ready \
  --body $'Required code outputs:\n- e2e-smoke/node/src/add.js\n- e2e-smoke/node/test/add.test.js\n\nValidation:\n- cd e2e-smoke/node && npm test -- --passWithNoTests\n'
```

Add approval when a repo requires issue-side approval labels:

```bash
gh issue edit <number> --add-label healer:pr-approved
```

After editing or creating an issue, run one controlled pass:

```bash
flow-healer start --repo <repo-name> --once
flow-healer status --repo <repo-name>
```

If you are debugging issue parsing, compare the issue body against the expectations in `tests/test_healer_task_spec.py` and `tests/e2e/test_flow_healer_e2e.py` before changing code.

## Commit & Pull Request Guidelines
This repository currently has no commit history, so use Conventional Commit-style messages such as `feat: add repo health check` or `fix: close store after scan`. Keep pull requests small and reviewable. Include a short summary, test evidence (`pytest`, CLI smoke commands), linked issues, and terminal output or screenshots when changing user-visible CLI behavior.

## Security & Configuration Tips
Do not commit tokens, local repo paths, or generated state. Store GitHub credentials in environment variables such as `GITHUB_TOKEN`, and keep runtime data under `~/.flow-healer/` as intended by the sample config.
