# Demo Repo Setup

This guide sets up a public GitHub demo repo for Flow Healer that demonstrates both Class A (flaky test repair) and Class B (safe CI/config) healing end-to-end.

## Overview

The demo repo is a minimal public Python project configured as a Flow Healer target. It has seeded issues — some accepted (Class A and B), some intentionally rejected — so the demo shows the full operator workflow: issue → TUI → draft PR → approve.

## Repo Structure

```text
flow-healer-demo/
├── pyproject.toml
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/
│   └── demo/
│       └── math_utils.py
└── tests/
    ├── test_math_utils.py
    └── test_timing.py
```

## Setup Steps

### 1. Create the GitHub repo

Create a public repo named `flow-healer-demo` under your GitHub account.

```bash
gh repo create flow-healer-demo --public --clone
cd flow-healer-demo
```

### 2. Bootstrap the project

Create a minimal Python project:

**`pyproject.toml`:**
```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "flow-healer-demo"
version = "0.1.0"
requires-python = ">=3.11"

[project.optional-dependencies]
dev = ["pytest"]
```

**`src/demo/math_utils.py`:**
```python
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
```

**`tests/test_math_utils.py`:**
```python
from demo.math_utils import add, subtract

def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(5, 2) == 3
```

**`tests/test_timing.py`:**
```python
import time

def test_timing_sensitive():
    """This test is timing-sensitive and can flake under load."""
    start = time.monotonic()
    time.sleep(0.01)
    elapsed = time.monotonic() - start
    # Flaky: uses a tight bound that CI sometimes misses
    assert elapsed < 0.1, f"Expected < 0.1s, got {elapsed:.3f}s"
```

**`.github/workflows/ci.yml`:**
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e '.[dev]'
      - run: pytest
```

Push initial commit:

```bash
git add .
git commit -m "feat: initial demo project"
git push -u origin main
```

### 3. Create GitHub labels

```bash
gh label create "healer:ready" --color "0075ca" --description "Flow Healer: ready to process"
gh label create "healer:pr-approved" --color "e4e669" --description "Flow Healer: PR approved"
```

### 4. Configure Flow Healer

Add to `~/.flow-healer/config.yaml`:

```yaml
repos:
  - name: demo
    path: /absolute/path/to/flow-healer-demo
    repo_slug: yourname/flow-healer-demo
    default_branch: main
    enable_autonomous_healer: true
    issue_contract_mode: lenient
    issue_required_labels:
      - healer:ready
    healer_mode: guarded_pr
    max_concurrent_issues: 2
    retry_budget: 2
    verifier_policy: required
    test_gate_mode: local_then_docker
    language: python
```

### 5. Seed Issues

Create these issues on GitHub and add the `healer:ready` label to issues 1 and 2 for the demo:

#### Issue 1 — Class A: Flaky Test (label: healer:ready)

**Title:** `test_timing_sensitive flakes on CI — timing bound too tight`

**Body:**
```markdown
The test `test_timing_sensitive` in `tests/test_timing.py` fails intermittently on CI when the system is under load. The 0.1s bound is too tight.

## Required code outputs

- `tests/test_timing.py` (relax the timing bound to 1.0s or mock the timer)

## Validation command

pytest tests/test_timing.py -v
```

#### Issue 2 — Class B: CI Fix (label: healer:ready)

**Title:** `CI workflow should test Python 3.12 too`

**Body:**
```markdown
The CI workflow only tests Python 3.11. We should add 3.12 to the matrix.

## Required code outputs

- `.github/workflows/ci.yml` (add python-version: ["3.11", "3.12"] matrix)

## Validation command

echo "CI config updated"
```

#### Issue 3 — Class A: Another Flaky Test (no label yet — for demo wave 2)

**Title:** `test_subtract occasionally fails with import error on fresh CI runners`

**Body:**
```markdown
Intermittent: `ImportError: cannot import name 'subtract' from 'demo.math_utils'` on fresh CI runners. Likely a missing `__init__.py`.

## Required code outputs

- `src/demo/__init__.py` (create empty file)
- `tests/__init__.py` (create empty file)

## Validation command

pytest tests/test_math_utils.py -v
```

#### Issue 4 — Intentional Reject: production file (for demo — will be rejected)

**Title:** `Refactor math_utils to use dataclasses`

**Body:**
```markdown
## Required code outputs

- `src/demo/math_utils.py` (refactor functions to use a MathUtils dataclass)

## Validation command

pytest tests/ -v
```

*Expected outcome: rejected with `scope_violation` — production file.*

#### Issue 5 — Intentional Reject: missing validation (for demo — will need clarification)

**Title:** `Update README with project description`

**Body:**
```markdown
The README is empty. Add a description of what this demo project does.

## Required code outputs

- `README.md` (add description)
```

*Expected outcome: `needs_clarification` — no Validation command section.*

### 6. Run the Demo

```bash
# Verify setup
flow-healer doctor --repo demo

# Run one healing cycle
flow-healer start --once --repo demo

# Watch the TUI
flow-healer tui --repo demo
```

## Demo Recording Script

For the 3-minute demo recording:

1. (0:00) Show the two seeded issues on GitHub with `healer:ready` label
2. (0:20) Run `flow-healer start --once --repo demo` — show logs in terminal
3. (1:00) Open TUI: `flow-healer tui --repo demo` — navigate to Review Queue
4. (1:30) Select the Class B issue (CI fix) — press `o` to open the draft PR
5. (2:00) Show the PR body: diff, validation evidence, reviewer summary
6. (2:30) Convert draft to ready-for-review and merge
7. (3:00) Return to TUI — issue moves to History tab

## Launch Checklist

- [ ] ≥ 3 successful draft PRs: at least 1 Class A, 1 Class B
- [ ] ≥ 1 intentional rejection visible (scope_violation or needs_clarification)
- [ ] Demo recording: issue → TUI → draft PR → approve — under 3 minutes
