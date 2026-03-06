# Contributing

## Development Workflow

1. Create a virtual environment.
2. Install the package in editable mode.
3. Run `pytest` before opening a PR.
4. Keep changes small, reviewable, and aligned with the existing module boundaries.

## Commands

~~~bash
pytest
pytest tests/test_healer_loop.py -v
flow-healer scan --dry-run
~~~

## Style

- Use 4-space indentation.
- Prefer explicit type hints on public interfaces.
- Keep modules responsibility-focused.

## PR Expectations

- Summarize the change clearly.
- Include test evidence.
- Link the motivating issue.

- [TODO: Verify] Whether future contribution docs should mention release/versioning steps
