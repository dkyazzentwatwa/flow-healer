# Go Smoke Lanes

This guide covers the Go smoke fixtures under `e2e-smoke/go`.

## Execution Root

- Use the Go fixture path declared in the issue.
- Keep work inside that root.

## Readiness Expectations

- The host must have a working Go toolchain because the current lane is local-only.

## Allowed Mutation Scope

- Limit edits to Go sources, tests, and fixture-local modules required by the issue.

## Validation Commands

- Prefer `cd e2e-smoke/go && go test ./...` or the narrower command declared by the issue body.

## Evidence And Fixture Expectations

- Go smoke lanes are code/test fixtures, not browser evidence targets.

## Common Failure Modes

- Running `go test` at the wrong root.
- Accidental mutation of generated files or unrelated modules.

## Lane-Specific Guardrails

- Keep module boundaries intact.
- Do not widen a Go smoke issue into general repo cleanup.
