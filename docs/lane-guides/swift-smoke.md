# Swift Smoke Lanes

This guide covers the Swift smoke fixtures under `e2e-smoke/swift`.

## Execution Root

- Use the Swift fixture directory named by the issue.

## Readiness Expectations

- Swift lanes require a working local Swift toolchain; there is no Docker fallback.

## Allowed Mutation Scope

- Restrict edits to the fixture’s package sources, tests, and manifest as needed by the issue.

## Validation Commands

- Prefer `cd e2e-smoke/swift && swift test` or the narrower issue-body command.

## Evidence And Fixture Expectations

- Swift smoke lanes are not browser-evidence tasks.

## Common Failure Modes

- Local toolchain drift.
- Validation run at the wrong directory level.

## Lane-Specific Guardrails

- Keep changes local to the Swift package.
- Do not compensate for host toolchain issues by weakening tests.
