# Ralph Major Audit Master Checklist

This is the living execution tracker for the March 12 full-repo audit follow-up.

Update rules:

- Mark a task complete only after code lands and focused verification passes.
- Add the exact command or CI job name to the verification log when a slice is proven.
- Keep the "Current Snapshot" and "Immediate Next Tasks" sections current at the end of each meaningful slice.
- If a task is intentionally deferred, add a short note instead of leaving it ambiguous.

## Status Legend

- `Done`: implemented and verified
- `Partial`: code or tests changed, but the full target lane is not yet proven
- `Next`: highest-value unstarted work
- `Later`: valuable follow-up, but not on the critical path

## Current Snapshot

Last updated: `2026-03-12`

| Audit capability | Status | Notes |
| --- | --- | --- |
| Save one repo-tracked audit checklist | Done | This file is the source of truth for the audit follow-up. |
| Stabilize `prosper-chat` chat widget identity handling | Done | Duplicate-key regression test added and the full `prosper-chat` suite is green. |
| Remove `prosper-chat` formatter flake symptoms | Done | The formatter lane is green and now fails on any unexpected `console.error`. |
| Add tracked app/frontend tests to CI | Done | Workflow jobs added, `prosper-chat` lockfile refreshed, `node-next` uses `npm install` because its lockfile is intentionally gitignored, and PR `#952` proved the jobs on real GitHub runners. |
| Harden the SQL auto-pause test lane | Done | Targeted SQL tests and the full root `pytest -q` lane are green. |
| Fix app-backed text determinism for `#941/#942/#943` | Done | Node Next, Ruby Rails, and Java Spring now expose deterministic `Evidence TC` text on the verified routes. |
| Fix Rust lockfile/scope suppression for `#945` | Done | `Cargo.lock` is filtered like other generated lockfiles and the smoke lane now covers `add_many`. |
| Keep package build and CLI install healthy | Done | `python -m build`, fresh wheel reinstall, and `flow-healer --help` all succeeded after the determinism patches landed. |
| Keep operator-facing status/doctor healthy | Done | `flow-healer status` and `flow-healer doctor` both reran successfully on the host after the latest fixes. |
| Refresh stale runtime-profile warnings | Done | The canary script now loads stored runtime-profile success timestamps, and the rerun canary/gate pair passed without stale-profile warnings. |

## Verified Evidence

- `pytest -q` previously reproduced the SQL flake as `778 passed, 1 failed`
- `pytest tests/test_sql_validation.py -q` passed
- `pytest -q` now passes with `779 passed`
- `cd apps/dashboard && npm test` passed
- `#941` replay passed on an isolated local port and `cd e2e-apps/node-next && npm test` passed
- `cd e2e-apps/ruby-rails-web && bundle exec rspec` passed with the new `Evidence TC 2` marker assertion
- `cd e2e-apps/java-spring-web && ./gradlew test --no-daemon` passed with the new `Evidence TC 3` marker assertion
- `cd e2e-smoke/rust && cargo test` passed with `add_many`
- `cd e2e-apps/prosper-chat && npm test` now passes
- isolated worktree reran the dashboard, node-next, and prosper-chat CI install/test lanes successfully
- `pytest tests/test_e2e_apps_sandboxes.py -q` passed
- GitHub PR `#952` completed `dashboard-tests`, `node-next-tests`, `prosper-chat-tests`, `package`, `test (3.11)`, `test (3.12)`, and `reliability-canary` successfully
- `pytest tests/test_reliability_canary.py -q` passed with the new config-backed runtime freshness coverage
- `python scripts/run_reliability_canary.py --output /tmp/flow-healer-reliability-canary-report.json --config config.yaml --repo flow-healer-self` passed with no stale runtime profiles
- `python scripts/evaluate_reliability_canary_gate.py --report /tmp/flow-healer-reliability-canary-report.json --policy .github/reliability-canary-policy.json --mode enforce --summary-output /tmp/flow-healer-reliability-canary-summary.md` passed
- `python -m build` passed on the host
- fresh wheel install and `flow-healer --help` passed
- `flow-healer --config config.yaml status --repo flow-healer-self` passed
- `flow-healer --config config.yaml doctor --repo flow-healer-self` passed

## Findings Queue

### Finding 1: `prosper-chat` chat message IDs collided under fake time

- [x] Add a failing regression test that catches duplicate-key warnings during the booking flow
- [x] Replace timestamp-based message IDs with monotonic local IDs
- [x] Re-run the focused formatter test file
- [x] Re-run the full `prosper-chat` suite

### Finding 2: tracked app/frontend test lanes were missing from root CI

- [x] Confirm tracked test commands exist for `apps/dashboard`, `e2e-apps/node-next`, and `e2e-apps/prosper-chat`
- [x] Add separate GitHub Actions jobs for each app/frontend lane
- [x] Fix job assumptions around package-lock state (`node-next` uses `npm install`, `prosper-chat` lockfile refreshed)
- [x] Verify the new jobs in GitHub after push/PR

### Finding 3: SQL auto-pause test was sensitive to ambient suite state

- [x] Confirm the failing test passes in isolation
- [x] Pin the SQL auto-pause env expectation inside the affected tests
- [x] Re-run the full root `pytest -q` lane and confirm the flake is gone
- [x] If the root lane still flakes, isolate the contaminating order dependency

### Finding 4: app-backed browser TCs `#941/#942/#943` needed deterministic success text

- [x] Confirm the expected `Evidence TC` markers exist on the target routes
- [x] Add focused regression coverage for the Ruby and Java login routes
- [x] Re-run the Node Next, Ruby Rails, and Java Spring issue lanes

### Finding 5: Rust TC `#945` drifted on `Cargo.lock` and build artifact scope noise

- [x] Add failing runner regressions for `Cargo.lock` staging, `target/` build noise, and retry cleanup
- [x] Treat `Cargo.lock` as Rust runtime lockfile noise unless explicitly requested
- [x] Implement `add_many(left, right, extra)` and cover it in the Rust smoke tests
- [x] Re-run the Rust issue lane

## Immediate Next Tasks

- [ ] Decide whether to merge or close PR `#952` now that the runner verification is complete

## Verification Log

- [x] `npx vitest run src/test/chat-widget-formatters.test.ts`
- [x] `cd e2e-apps/prosper-chat && npm test`
- [x] `isolated worktree CI preflight: apps/dashboard npm ci && npm test`
- [x] `isolated worktree CI preflight: e2e-apps/node-next npm ci && npm test`
- [x] `isolated worktree CI preflight: e2e-apps/prosper-chat npm ci && npm test`
- [x] `cd apps/dashboard && npm test`
- [x] `pytest -q`
- [x] `pytest tests/test_sql_validation.py -q`
- [x] `pytest tests/test_healer_runner.py -q -k 'rust_lockfile or rust_target_artifacts'`
- [x] `pytest tests/test_reliability_canary.py -q`
- [x] `#941 isolated port replay: curl http://127.0.0.1:3311/ for Evidence TC 1 + cd e2e-apps/node-next && npm test`
- [x] `cd e2e-apps/ruby-rails-web && bundle exec rspec`
- [x] `cd e2e-apps/java-spring-web && ./gradlew test --no-daemon`
- [x] `cd e2e-smoke/rust && cargo test`
- [x] `python -m build`
- [x] `fresh-venv wheel install + flow-healer --help`
- [x] `python scripts/run_reliability_canary.py --output /tmp/flow-healer-reliability-canary-report.json --config config.yaml --repo flow-healer-self`
- [x] `python scripts/evaluate_reliability_canary_gate.py --report /tmp/flow-healer-reliability-canary-report.json --policy .github/reliability-canary-policy.json --mode enforce --summary-output /tmp/flow-healer-reliability-canary-summary.md`
- [x] `flow-healer --config config.yaml status --repo flow-healer-self`
- [x] `flow-healer --config config.yaml doctor --repo flow-healer-self`
- [x] `GitHub PR #952: dashboard-tests, node-next-tests, prosper-chat-tests, package, test (3.11), test (3.12), reliability-canary`
