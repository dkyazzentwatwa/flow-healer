# Python Smoke Lanes

This guide covers `e2e-smoke/python`, `python-app`, `py-fastapi`, `py-django`, `py-flask`, `py-data-pandas`, and `py-ml-sklearn`.

## Execution Root

- Use the exact fixture directory named by the issue.
- Keep validation and edits inside that root unless the runner explicitly widens scope to address a safe baseline blocker.

## Readiness Expectations

- Python fixtures should have a runnable local environment or a configured Docker fallback when the lane allows it.
- Respect the fixture’s own dependency and app layout rather than imposing repo-level assumptions.

## Allowed Mutation Scope

- Limit edits to app code, tests, and fixture-local config needed by the declared issue.
- Avoid changing shared harness files from a fixture issue unless the failure clearly belongs to the harness.

## Validation Commands

- Prefer fixture-local `pytest` commands from the issue body.
- Data and ML fixtures may have narrower validation commands than web fixtures; keep them as declared.

## Evidence And Fixture Expectations

- Most Python smoke lanes are not browser-evidence tasks.
- Browser-backed Python app targets belong under [browser-apps.md](browser-apps.md), not this guide.

## Common Failure Modes

- Running validation at repo root instead of the fixture.
- Silent virtualenv or dependency drift.
- Broad repo-wide pytest runs masking the real fixture contract.

## Lane-Specific Guardrails

- Add the narrowest regression test that proves the issue contract.
- Do not widen a pure fixture issue into a general dependency cleanup unless the baseline blocker is safe and inside the same execution root.
