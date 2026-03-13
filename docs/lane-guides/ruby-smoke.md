# Ruby Smoke Lanes

This guide covers the Ruby smoke fixtures under `e2e-smoke/ruby`.

## Execution Root

- Use `e2e-smoke/ruby` or the narrower fixture path named by the issue.
- Keep work inside the declared root.

## Readiness Expectations

- `bundle exec rspec` should be the default validation anchor unless the issue body declares a narrower command.
- Ruby lane issues often rely on correct working-directory selection; validate the execution root before changing code.

## Allowed Mutation Scope

- Limit edits to the declared fixture’s Ruby source and specs.
- Avoid widening scope to unrelated Rails or app-backed targets; those are browser-app lanes.

## Validation Commands

- Prefer `cd e2e-smoke/ruby && bundle exec rspec` or the issue-specific equivalent.

## Evidence And Fixture Expectations

- Ruby smoke fixtures are code-and-spec lanes, not browser-evidence lanes.
- If the task is browser-backed, treat it as `ruby-rails-web` under [browser-apps.md](browser-apps.md).

## Common Failure Modes

- Validation accidentally runs from repo root.
- The issue body points at Rails behavior while the required outputs target the Ruby smoke fixture.
- Baseline spec drift exists inside the fixture and must be addressed before the requested change can verify cleanly.

## Lane-Specific Guardrails

- Keep smoke-fixture docs and specs aligned when changing expectations.
- Escalate contract ambiguity early; Ruby fixtures are sensitive to execution-root mistakes.
