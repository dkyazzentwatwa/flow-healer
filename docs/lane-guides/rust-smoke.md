# Rust Smoke Lanes

This guide covers the Rust smoke fixtures under `e2e-smoke/rust`.

## Execution Root

- Use the Rust fixture path declared in the issue body.
- Keep edits scoped to that crate or fixture.

## Readiness Expectations

- A working local Rust toolchain is required.

## Allowed Mutation Scope

- Restrict edits to the declared crate sources, tests, and fixture-local config.

## Validation Commands

- Prefer `cd e2e-smoke/rust && cargo test` unless the issue body declares a narrower command.

## Evidence And Fixture Expectations

- Rust smoke lanes are code/test fixtures only.

## Common Failure Modes

- Cargo commands executed outside the intended crate root.
- Touching shared harness files to compensate for a fixture-local problem.

## Lane-Specific Guardrails

- Keep changes crate-local.
- Add or update the narrowest regression test possible.
