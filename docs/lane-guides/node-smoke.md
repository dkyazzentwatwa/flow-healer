# Node Smoke Lanes

This guide covers `e2e-smoke/node` and the JS framework smoke families such as `js-next`, `js-vue-vite`, `js-nuxt`, `js-angular`, `js-sveltekit`, `js-express`, `js-nest`, `js-remix`, `js-astro`, `js-solidstart`, `js-qwik`, `js-hono`, `js-koa`, `js-adonis`, `js-redwoodsdk`, `js-lit`, and `js-alpine-vite`.

## Execution Root

- Use the specific smoke directory named by the issue body.
- For framework fixtures, keep edits inside the named fixture rather than broadening to the entire `e2e-smoke/` tree.

## Readiness Expectations

- The local runtime should have a supported Node toolchain or a valid Docker fallback when the lane allows it.
- Package-manager hints in the fixture should be respected; do not rewrite a lane from `pnpm` to `npm` just to make a test pass.

## Allowed Mutation Scope

- Keep mutations inside the declared smoke fixture and its test files.
- Avoid editing shared harness scripts unless the issue is about the harness itself.

## Validation Commands

- Prefer the issue-body command, usually a lane-local `npm test`, `pnpm test`, `yarn test`, or fixture helper.
- Use Docker only where the configured strategy supports it; Node smoke lanes may use local or Docker validation depending on repo config.

## Evidence And Fixture Expectations

- Most smoke lanes are code-plus-test fixtures, not browser artifact tasks.
- When a smoke fixture drives a browser app, the browser-app lane guide still governs evidence behavior.

## Common Failure Modes

- Wrong package manager or install assumptions.
- Monorepo workspace files such as `pnpm-workspace.yaml`, `turbo.json`, or `nx.json` being ignored during execution-root selection.
- Test commands accidentally run at repo root instead of inside the fixture.

## Lane-Specific Guardrails

- Keep framework-specific config intact unless the issue explicitly targets it.
- Do not “fix” a lane by swapping frameworks or deleting tests.
- If the issue body is ambiguous, tighten the issue contract instead of teaching the runner a one-off heuristic.
