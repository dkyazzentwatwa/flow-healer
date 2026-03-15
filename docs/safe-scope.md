# Safe Scope Contract

This document defines exactly what files Flow Healer is allowed to modify at MVP, and what causes an issue to be rejected.

## Allowed Target Files

### Class A — Test Files Only

```text
tests/**
test_*.py
*_test.py
spec/**
__tests__/**
*.test.js
*.test.ts
*.spec.js
*.spec.ts
```

### Class B — Safe Config / CI / Doc Files

```text
.github/**
Makefile
pyproject.toml
setup.cfg
tox.ini
requirements*.txt
*.md
docs/**/*.md
```

## Always-Rejected Target Files

Any file matching these patterns causes immediate rejection with `scope_violation`:

```text
src/**           (except test files inside src/tests/ or src/**/*test*)
lib/**
app/**
*.py             (root-level, non-test)
```

The rejection comment on the issue will explain exactly which file triggered the violation.

## Issue Body Requirements

Every accepted issue must include:

```
## Required code outputs

- `path/to/file.py` (description of what changes)

## Validation command

pytest tests/test_specific.py -v
```

Missing either section causes `needs_clarification`. Flow Healer comments on the issue explaining what to add.

## Diff Size Limits

- Max files changed: 8 (configurable via `max_diff_files`)
- Max lines changed: 400 (configurable via `max_diff_lines`)

Exceeding either triggers `judgment_required`.

## Examples

### Accepted: Class A

```
Title: test_cache_invalidation flakes on CI

Required code outputs:
- `tests/test_cache.py` (remove time.sleep dependency, use mock timer)

Validation command:
pytest tests/test_cache.py -v
```

### Accepted: Class B

```
Title: CI fails on Python 3.12 — missing tomllib import guard

Required code outputs:
- `pyproject.toml` (add python_requires constraint)
- `.github/workflows/ci.yml` (add 3.12 to matrix)

Validation command:
python -m pytest tests/ -q
```

### Rejected: production file in outputs

```
Required code outputs:
- `src/flow_healer/healer_runner.py`  ← triggers scope_violation
```

### Rejected: no validation command and none detectable

```
Title: update README badges

Required code outputs:
- `README.md`

(no Validation command section)  ← triggers needs_clarification
```

## Lenient vs Strict Contract Mode

Flow Healer supports two parsing modes, configured per repo:

- `lenient` (default): infers outputs and validation from issue body; gates on low confidence only
- `strict`: requires explicit `Required code outputs` and `Validation command` sections; no inference

For MVP and new users, `lenient` is recommended. Switch to `strict` once your issue templates are established.

## Scope Checking at Runtime

Scope is checked at two points:

1. **Pre-run (triage):** Issue body is parsed for output targets. Targets outside allowed scope → issue is rejected before work begins.
2. **Post-run (verification):** Actual diff is inspected. Any file outside the declared outputs → `scope_violation` failure.
