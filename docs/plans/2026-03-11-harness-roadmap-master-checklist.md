# Harness Roadmap Master Checklist

This is the living execution tracker for the harness-engineering roadmap.

Update rules:

- Mark a task complete only after code lands and focused verification passes.
- Add the exact smoke issue, PR, or test command to the relevant section when a slice is proven live.
- Keep the "Current Snapshot" and "Immediate Next Tasks" sections current at the end of each meaningful slice.
- If a task is intentionally deferred, add a short note instead of silently leaving it stale.

## Status Legend

- `Done`: implemented and verified
- `Partial`: some plumbing exists, but the end-to-end behavior is not complete
- `Next`: highest-value unstarted work
- `Later`: important, but not on the immediate critical path

## Current Snapshot

Last updated: `2026-03-12`

| Ultimate goal capability | Status | Notes |
| --- | --- | --- |
| Validate the current state of the codebase | Done | Existing runner, verifier, preflight, and task-contract flow are in place. |
| Reproduce a reported bug | Partial | Strong for explicit app-scoped `repro_steps` on `node-next`; not yet broad across app types. |
| Record a video demonstrating the failure | Partial | Best-effort capture exists, but video is no longer a merge gate. |
| Implement a fix | Done | Core Flow Healer behavior. |
| Validate the fix by driving the application | Done | Browser-driven validation exists for app-scoped tasks. |
| Record a second video demonstrating the resolution | Partial | Best-effort only; screenshots are the required proof path. |
| Open a pull request | Done | Existing PR open/update loop works. |
| Respond to agent and human feedback | Partial | Core feedback loop exists; app-proof + CI-aware iteration still needs hardening. |
| Detect and remediate build failures | Partial | Local failures are handled, remote CI is visible, transient infra failures are separated from deterministic code failures, deterministic CI failures now requeue automatically on the same PR, failure buckets are classified, and promotion state now surfaces in status views; live GitHub CI remediation proof is still pending. |
| Escalate to a human only when judgment is required | Done | Conservative judgment routing now classifies and persists `judgment_reason_code`, renders escalation packets/comments, pauses or preserves the PR lane appropriately, and now has live GitHub judgment proof via issue `#924`. |
| Merge the change | Partial | Auto-merge waits for local promotion readiness, screenshot proof on browser-backed app runs, green remote CI, and the absence of a `judgment_reason_code`; judgment-blocked issues now resume cleanly after human issue-body guidance in e2e coverage, and live GitHub judgment blocking is proven via issue `#924`. |

## Coordination

- [x] Convert the roadmap into one repo-tracked master checklist
- [x] Record current completion state for Phase 1 and Phase 2
- [x] Capture a live inline-evidence GitHub smoke proof
- [ ] Keep this file updated after every meaningful harness slice
- [x] Add links to real smoke PRs as Phase 3 lands

## Live Proof Log

- [x] Live browser validation against `e2e-apps/node-next`
- [x] Live issue smoke for inline GitHub evidence: `#913`
- [x] Confirm GitHub inline rendering uses the raw asset URL, not `blob?...raw=1`
- [x] Live PR-body smoke with before/after gallery rendered on a real PR
- [x] Live end-to-end issue -> repro -> fix -> PR -> CI -> merge smoke
- [x] Live app-backed PR smoke: issue `#918` -> PR `#919` with inline before/after screenshots and green remote CI
- [x] Live code-only promotion smoke: issue `#920` -> PR `#921` -> green CI -> merged

## Phase 1: Harness Foundation

### Task contract and config

- [x] Add app-scoped task fields to `HealerTaskSpec`
- [x] Parse runtime profile selectors from issue/task input
- [x] Support named app runtime profiles in repo config
- [x] Provide config examples for app-scoped execution

### Runtime harness

- [x] Add `AppHarness` contract
- [x] Boot one isolated app runtime per worktree
- [x] Wait on an explicit ready signal / ready URL
- [x] Persist runtime boot summaries into attempt data
- [x] Tear down runtime cleanly after the attempt
- [x] Re-check workspace hygiene after runtime shutdown

### Backward compatibility

- [x] Keep code-only issues on the existing repo-healing lane
- [x] Keep app behavior opt-in via explicit task contract fields
- [x] Preserve existing runner/verifier/reviewer foundations

### Verification

- [x] Focused unit tests for task parsing and runner behavior
- [x] E2E mixed-repo sandbox regression coverage still passing

## Phase 2: Browser + Evidence

### Browser harness

- [x] Add `BrowserHarness` abstraction
- [x] Use Playwright as the first concrete browser backend
- [x] Preflight missing browser runtime / Playwright install
- [x] Support `goto`, `click`, `fill`, `press`, `wait_text`, `expect_text`, and `fetch` repro steps
- [x] Persist step transcript data
- [x] Make `node-next` the reference app sandbox

### Artifact contract

- [x] Capture failure screenshot
- [x] Capture resolution screenshot
- [x] Capture console log
- [x] Capture network log
- [x] Persist browser artifact bundle into attempt/test summary data
- [x] Make screenshots required for app-scoped evidence gating
- [x] Make video optional and best-effort only
- [x] Keep transcript/logs even when video is absent

### Runner integration

- [x] Run failure capture before code mutation for app-scoped tasks
- [x] Fail fast if the reported bug cannot be reproduced
- [x] Re-run the browser journey after the fix
- [x] Block success when required screenshots are missing
- [x] Thread artifact state through issue attempts and status comments

### Dashboard and local surfaces

- [x] Expose artifact bundle and links in persisted attempts
- [x] Render artifact links in the local dashboard
- [x] Serve local artifact files through the dashboard
- [x] Show evidence details in issue status comments
- [x] Include evidence sections in PR bodies

### GitHub trust surface

- [x] Publish evidence files to a dedicated artifact branch
- [x] Return both HTML and raw/download URLs for published artifacts
- [x] Use raw hosted image URLs for inline GitHub markdown rendering
- [x] Update existing PR bodies on reruns so evidence does not go stale
- [x] Prove inline rendering live on GitHub issue `#913`
- [x] Prove the same inline gallery on a real PR body

### Verification

- [x] Focused browser harness tests
- [x] Focused runner browser-evidence tests
- [x] Live `node-next` browser smoke
- [x] Live GitHub inline-evidence issue smoke
- [ ] Live multi-app smoke beyond `node-next`

## Phase 3: Promotion Engine

Status: `Done`

### Remote CI ingestion

- [x] Read check runs for the open PR
- [x] Read commit status checks for the open PR
- [x] Read workflow conclusions for the open PR
- [x] Persist normalized CI state into attempts / issue status
- [x] Add `ci_status_summary` to service and dashboard payloads

### CI failure classification

- [x] Define normalized CI failure buckets: `setup`, `lint`, `typecheck`, `test`, `flake`, `deploy_blocked`, `unknown`
- [x] Map GitHub checks/workflows into those buckets
- [x] Distinguish transient infra failures from deterministic code failures
- [x] Preserve raw CI evidence for operator debugging

### CI remediation loop

- [x] Feed deterministic CI failures back into the retry prompt
- [x] Update the same branch and same PR after CI remediation
- [x] Prevent duplicate PR creation during CI-driven retries
- [x] Stop retrying once CI remediation budget is exhausted

### Promotion state machine

- [x] Define stable promotion states: `local_validated`, `failure_artifacts_captured`, `resolution_artifacts_captured`, `pr_open`, `ci_green`, `promotion_ready`, `merge_blocked`
- [x] Persist promotion state transitions
- [x] Surface promotion state in dashboard/service/status output
- [x] Require app proof + screenshots + local validation + green CI before promotion
- [x] Keep the lighter path for code-only issues where appropriate

### Merge and approval policy

- [x] Gate auto-merge on `promotion_ready`
- [x] Block merge when screenshots are missing
- [x] Block merge while CI is red or pending
- [x] Block merge while judgment is required
- [x] Verify label-based approval behavior still composes cleanly with promotion states

### Verification

- [x] Tracker tests for CI/check-run ingestion
- [x] Loop tests for CI failure remediation
- [x] Service/dashboard tests for promotion-state surfacing
- [x] Live PR smoke with remote CI observed and reflected in status
- [x] Live end-to-end issue -> PR -> green CI -> merge smoke

## Phase 4: Judgment Routing

Status: `Done`

### Judgment model

- [x] Add `judgment_reason_code` taxonomy
- [x] Define categories: `product_ambiguity`, `unsafe_data_migration`, `non_deterministic_visual_result`, `conflicting_feedback`, `security_or_privacy_risk`, `repro_not_stable`
- [x] Separate judgment-required failures from normal deterministic build/test failures

### Escalation packets

- [x] Generate structured escalation payloads with attempted fixes, evidence, and precise human decision needed
- [x] Persist escalation packets in attempt data
- [x] Surface escalation packets in dashboard issue detail views
- [x] Post human-readable escalation comments back to GitHub when needed

### Feedback-loop alignment

- [x] Ensure review comments, review bodies, and PR comments all re-enter the same healing loop
- [x] Carry artifact/evidence context into feedback retries
- [x] Prevent escalation when the next deterministic action is obvious

### Verification

- [x] Focused tests for judgment classification
- [x] Focused tests for escalation packet rendering
- [x] E2E resume-after-human-guidance scenario for blocked judgment issues
- [x] Live smoke for one judgment-required scenario
- [x] Live GitHub judgment-required smoke: issue `#924` blocked with `judgment_required`, `judgment_reason_code=product_ambiguity`, and the issue-first escalation comment

## Phase 5: Reliability and Garbage Collection

Status: `Done`

### Artifact lifecycle

- [x] Define artifact retention policy
- [x] Clean stale local artifact directories
- [x] Define cleanup strategy for the remote artifact branch
- [x] Add size/volume guardrails for published artifacts

### Browser/app harness reliability

- [x] Detect flaky repro journeys
- [x] Record browser failure families separately from code-fix failures
- [x] Clean orphaned browser sessions and app runtimes
- [x] Add canary runs for app harness boot + browser proof
- [x] Add alertable counters for artifact publishing failures

### Ongoing coherence / drift control

- [x] Detect stale runtime profiles
- [x] Detect broken repro contracts in issue templates/examples
- [x] Detect doc drift between roadmap, checklist, and actual behavior
- [x] Add recurring reliability review of harness metrics

### Verification

- [x] Reliability runbook for harness failures
- [x] Periodic smoke checklist for artifact publishing
- [x] Canary dashboard surface for harness health

Notes:

- Artifact retention and guardrails now land through config + tracker publication metadata, including per-run `_meta.json` and expired remote evidence pruning.
- Reconciler cleanup now reaps orphan app-runtime process groups, detects stale runtime profiles, cleans stale local artifact roots, and reports those families in resource audit.
- Service/dashboard payloads now expose `harness_health`, additive harness rollups, browser failure family counts, and canary-profile state from `kv_state`.
- Operator docs now live in `docs/harness-reliability-runbook.md` and `docs/harness-smoke-checklist.md`.
- Repro-contract validation now runs through `scripts/validate_repro_contract_examples.py` against `docs/harness-repro-contract-examples.json`, with focused coverage in `tests/test_harness_validation_scripts.py`.
- Harness roadmap drift checks now run through `scripts/check_harness_doc_drift.py`, also covered by `tests/test_harness_validation_scripts.py`.
- Canary dashboard surface remains covered in `tests/test_service.py` and `tests/test_web_dashboard.py`.
- Browser-session cleanup now tracks and prunes stale browser-session roots alongside app-runtime cleanup, with coverage in `tests/test_healer_reconciler.py`, `tests/test_healer_reconciler_resource_audit.py`, `tests/test_service.py`, and `tests/test_web_dashboard.py`.
- Live GitHub harness canary proof landed on March 11, 2026 / March 12, 2026 UTC for runtime profile `node-next-web`, publishing screenshot + console + network logs to `flow-healer/evidence/issue-canary-node-next-web/canary-20260312041820` on branch `flow-healer-artifacts`.

## App Coverage Expansion

Status: `Later`

- [x] Establish `e2e-apps/node-next` as the reference sandbox
- [ ] Add a second reference app target
- [ ] Document how to onboard a new app target/runtime profile
- [ ] Add fixture-profile guidance for deterministic repro data
- [ ] Support richer auth/session flows where needed
- [ ] Validate the browser-evidence lane across more than one stack

## Open Decisions

- [x] Screenshots are required; videos are optional
- [x] Inline GitHub markdown should use raw hosted asset URLs
- [x] Console/network logs are always published for app-backed runs
- [ ] Decide how long the artifact branch should retain evidence
- [ ] Decide whether PR bodies should show a compact gallery or full-size screenshots by default
- [ ] Decide whether app-scoped issues should require explicit `artifact_requirements` forever or whether screenshots become the default expectation

## Immediate Next Tasks

### Critical path

- [x] Implement GitHub check-run / status-check ingestion in `healer_tracker.py`
- [x] Persist `ci_status_summary` in attempts and status surfaces
- [x] Classify remote CI failures into normalized buckets
- [x] Add the first CI-aware retry/remediation loop in `healer_loop.py`
- [x] Surface current promotion states in dashboard/service/status views
- [x] Persist explicit promotion-state transitions beyond the current merge gate
- [x] Require screenshot proof + local validation + green CI before final promotion
- [x] Run a live PR-body smoke with inline before/after evidence

### Right after that

- [x] Implement `judgment_reason_code` routing
- [x] Build escalation packet rendering
- [x] Add dashboard surfaces for promotion + judgment state
- [ ] Add artifact retention / cleanup policy

## Done Log

- [x] Harness foundation landed
- [x] Browser + evidence landed for `node-next`
- [x] Screenshot-first evidence contract adopted
- [x] Inline GitHub evidence proven live on issue `#913`
- [x] Remote CI visibility landed across tracker/store/service/dashboard payloads
- [x] Auto-merge now waits for green remote CI plus local promotion readiness
- [x] CI summaries now include normalized failure buckets and per-check detail
- [x] Deterministic remote CI failures now requeue the issue with CI feedback context
- [x] E2E proof that CI-driven retries update the same PR without duplicates
- [x] Promotion state now surfaces in service rows and dashboard issue views
- [x] Browser-backed app runs now need screenshot proof before promotion or auto-merge
- [x] Promotion-state transitions now persist in runner/loop attempt summaries
- [x] Approval-gated PRs stay out of `promotion_ready` until the human label path resumes them
- [x] Transient infra CI failures no longer trigger the deterministic repair loop
- [x] Auto-merge now respects `judgment_reason_code` and stays blocked when human judgment is required
- [x] E2E proof that a judgment-blocked issue resumes after human issue-body guidance and opens a PR cleanly
- [x] Live app-backed smoke issue `#918` opened PR `#919` with inline screenshot evidence and green observed remote CI
