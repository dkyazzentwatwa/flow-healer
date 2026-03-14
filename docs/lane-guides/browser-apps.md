# Browser App Lanes

This guide covers browser-backed app targets under `e2e-apps/`: `node-next`, `python-fastapi`, `ruby-rails-web`, `java-spring-web`, `prosper-chat`, and `nobi-owl-trader`.

## Execution Root

- Use the app directory named in the issue body, for example `e2e-apps/node-next` or `e2e-apps/java-spring-web`.
- Keep `Required code outputs` inside the declared app unless the runner explicitly widens scope for a safe baseline blocker.

## Readiness Expectations

- The runtime profile and `entry_url` must match a supported browser-backed app.
- Repro steps should describe what the browser harness must do, not what a human remembers from prior runs.
- If auth or fixture state matters, declare it with a fixture profile or issue-body context instead of assuming ambient state.

## Allowed Mutation Scope

- Prefer the smallest possible app-local file set.
- UI-only copy, styling, and component changes are safe when they do not alter dashboard data contracts, API payload shape, or server control endpoints.
- Changes that alter runtime profile behavior, app boot scripts, API proxying, or artifact publication semantics are control-plane changes and must stay aligned with [../dashboard.md](../dashboard.md) and [../evidence-contract.md](../evidence-contract.md).

## Validation Commands

- Prefer the app-owned validation command declared in the issue body.
- Use the app-local helper when present, for example `./scripts/healer_validate.sh`.
- Browser evidence issues should still validate the app plus artifact outputs; a passing page alone is not sufficient.

## Evidence And Fixture Expectations

- Browser issues should publish the exact named evidence artifacts required by the issue.
- When a task is constructive rather than a regression, use `browser_repro_mode: allow_success`.
- Failure and resolution screenshots, console logs, and network logs should follow [../evidence-contract.md](../evidence-contract.md).

## Common Failure Modes

- `entry_url` and `goto` combine into the wrong path when the issue body is malformed.
- The page renders the requested UI but artifact files never land at the exact required paths.
- App-local validation is red because of an unrelated baseline failure inside the same app.
- Fixture state drift causes the harness to miss the target route, auth gate, or expected text.
- Browser-backed Node apps can render static HTML before client bundles hydrate. The harness now retries one headless page load when same-origin JS/CSS assets fail to load, but repeated bootstrap failures should be treated as runtime readiness problems, not app logic regressions.

## Lane-Specific Guardrails

- Do not edit unrelated apps to satisfy a single app issue.
- Do not change artifact naming ad hoc; update the issue contract or evidence doc instead.
- If a baseline blocker is outside the allowed app root, stop and escalate instead of widening scope manually.
