# E2E Smoke Note

`e2e-smoke/` is the sandbox area for supported language strategy testing.

Current sandboxes:
- `python`
- `node`
- `swift`

Each sandbox is intentionally minimal and is meant to match the default test command shape for its language strategy.

Practical pointer: `cd` into the sandbox first, run the issue's `Validation:` line verbatim when present, and only then fall back to the sandbox's default test command so failures stay local before widening the scope. Keep `Required code outputs:` in that same sandbox so execution-root inference does not drift. If the run fails, paste that exact `cd ... && <test>` command back into the issue so the next pass reuses the same scope.
