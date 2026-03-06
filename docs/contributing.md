# Contributing

## Development Workflow

1. **Virtual Env**: Use Python 3.11+.
2. **Editable Install**: `pip install -e '.[dev]'`.
3. **Tests**: Run `pytest` and ensure 100% pass rate.
4. **Performance Journal**: Record significant performance insights or rejected optimizations in `.jules/bolt.md`.
5. **PR Submissions**: Use short, descriptive branch names and Conventional Commit-style messages.

## Commands

~~~bash
# Run all tests
pytest

# Run focused tests
pytest tests/test_healer_loop.py -v

# Smoke-test CLI
flow-healer doctor
flow-healer scan --dry-run
~~~

## Coding Style

- Follow **PEP 8**.
- **Indentation**: 4-space.
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes.
- **Types**: Explicit type hints on public methods and complex logic.
- **Docs**: Keep docstrings short and relevant.

## Performance-First Mentality

Flow Healer aims for high write throughput and concurrency. When modifying `SQLiteStore` or the processing loop:
- Benchmark changes if they impact critical paths.
- Document performance impacts in your PR.
- Record learnings in `.jules/bolt.md` using the standard format:
  ~~~markdown
  ## YYYY-MM-DD - [Title]
  **Learning:** [Insight]
  **Action:** [How to apply next time]
  ~~~

## PR Expectations

- **Clear Summary**: Explain the *why* and *how*.
- **Test Evidence**: Include CLI output or test logs.
- **Link Issues**: Use GitHub keywords like `Closes #123`.

> **Note**: For now, release versioning is handled manually by maintainers. Automated versioning is planned for future iterations.
