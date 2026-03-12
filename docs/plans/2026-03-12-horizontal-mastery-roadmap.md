# Horizontal Mastery Roadmap

This is the master checklist for the next `60-90 days` of horizontal hardening.

The goal is to master the current supported lanes before expanding further. During this roadmap window, prioritize reliability and determinism over breadth.

## Update Rules

- Mark a task complete only after code lands and focused verification passes.
- Record the exact test command, smoke run, or canary proof that closed the task.
- Do not add new language strategies or browser-backed runtime profiles during this roadmap unless required for a break/fix on an already-supported lane.
- Treat this file as the living execution tracker for the horizontal-mastery push.

## Status Legend

- `Done`: implemented and verified
- `Partial`: useful plumbing exists, but the target outcome is not yet consistently true
- `Next`: highest-value unstarted work in the current mastery window
- `Later`: important, but not on the immediate critical path

## Current Snapshot

Last updated: `2026-03-12`

| Objective | Primary metric(s) | Status | Target | Notes |
| --- | --- | --- | --- | --- |
| Consistent first-pass success on current lanes | `first_pass_success_rate` | Partial | `>= 0.80` rolling 14-day cohort | Improve reliability on current lanes before widening support. |
| Reliable browser-evidence publishing | artifact-publish success, missing required screenshot failures | Partial | `>= 0.98` publish success and `0` missing-screenshot failures across the latest 20 app-backed mastery runs | App-backed trust should fail on completeness, not on surprise gaps. |
| Stable preflight and canary health | preflight readiness class, per-profile canary freshness | Partial | all active mastery roots are `ready` in two consecutive refreshes; all active runtime profiles have a successful canary within 7 days | Health needs to stay green without manual babysitting. |
| Low wrong-root execution rate | `wrong_root_execution_rate` | Partial | `<= 0.03` rolling 14-day cohort | Mixed-root repos must stop leaking misrouting. |
| Strong issue-to-fix determinism across multiple repos | `no_op_rate`, `retries_per_success`, `mean_time_to_valid_pr_minutes` | Partial | `no_op_rate <= 0.05` and `retries_per_success <= 0.75` on the mastery cohort | Success should come from clearer contracts, not retry churn. |

## Operating Rules

- Freeze vertical expansion for the mastery window:
  - no new language strategies
  - no new browser-backed app targets
  - no new artifact types or proof requirements unless needed to stabilize existing lanes
- Optimize for the current supported surfaces:
  - code lanes: `python`, `node`, `swift`, `go`, `rust`, `ruby`, `java_gradle`
  - app-backed runtime profiles: `node-next-web`, `ruby-rails-web`, `java-spring-web`
- Use existing repo metric names and health surfaces; do not invent parallel reliability terminology.

## Mastery Cohort

The roadmap will measure progress against this fixed starting cohort:

- self-host/core repo lane:
  - `flow-healer-self`
- app-backed browser-evidence lane:
  - `flow-healer-self` with runtime profile `node-next-web`
- mixed-root or issue-scoped routing lane:
  - `flow-healer-self` issues targeting `e2e-smoke/python`, `e2e-smoke/node`, `e2e-smoke/swift`, `e2e-smoke/go`, `e2e-smoke/rust`, `e2e-smoke/java-gradle`, and `e2e-smoke/ruby`

Supported app-backed profiles for this mastery window remain:

- `node-next-web`
- `ruby-rails-web`
- `java-spring-web`

Current local config baseline note:

- The initial baseline snapshot only had `node-next-web` active in the local `flow-healer-self` runtime-profile config.
- The live `~/.flow-healer/config.yaml` runtime-profile config now includes `node-next-web`, `ruby-rails-web`, and `java-spring-web`, and the status proofs in Phase 3 reflect that cutover.

## Weekly Review Ritual

- Review the scorecard once per week using the latest `flow-healer status --repo flow-healer-self` snapshot.
- Record the dominant failure families, preflight blockers, and runtime-profile freshness in this document.
- Treat any metric movement without a corresponding code or environment change as determinism drift that needs explanation.

## Scoring Exclusions

Exclude failures from mastery scoring only when the primary cause is clearly outside Flow Healer's current supported surface:

- missing local toolchains for already-modeled but not yet installed environments, such as `go` and `rust` on this machine
- host-level outages that prevent all issue work equally, such as unavailable GitHub auth, broken network access, or a missing `codex` binary
- intentional profile downtime during planned maintenance, when the profile is explicitly marked offline in the weekly review note

Do not exclude:

- wrong-root routing
- no-op edits
- incomplete browser evidence
- fixture/auth-state drift
- app/runtime contract breakage inside supported lanes

## Phase 1 Baseline Snapshot

Captured on `2026-03-12` from:

- `python -m flow_healer.cli --config config.yaml status --repo flow-healer-self`
- snapshot file: `/tmp/flow-healer-phase1-status.json`

Baseline summary:

- mastery repo: `flow-healer-self`
- configured active runtime profiles: `node-next-web`
- `first_pass_success_rate`: `0.2727`
- `retries_per_success`: `0.4`
- `wrong_root_execution_rate`: `0.0`
- `no_op_rate`: `0.4828`
- `mean_time_to_valid_pr_minutes`: `2.31`
- preflight summary: `33 ready`, `2 blocked`, `0 unknown`, overall class `blocked`
- blocked execution roots: `e2e-smoke/go`, `e2e-smoke/rust`
- harness artifact publish failures: `0`
- harness artifact capture failures: `0`
- stale runtime profiles: `0`
- latest app-backed attempts considered for the baseline slice: `4`
- app-backed attempts with artifact proof ready: `2`
- app-backed attempts with missing required artifacts: `2`
- active canary freshness: `node-next-web` last success at `2026-03-12 04:18:20`

Phase 1 interpretation:

- routing quality is promising on the current sample because `wrong_root_execution_rate` is `0.0`
- first-pass success is not yet mastery-grade at `0.2727`
- determinism is the biggest immediate weakness because `no_op_rate` is `0.4828`
- preflight is not stable yet because `go` and `rust` are blocked by missing local toolchains
- browser evidence is not yet reliable enough for mastery because only `2` of the latest `4` app-backed attempts had artifact proof ready

## Phase 1: Baseline And Freeze

Status: `Partial`

### Coordination

- [x] Freeze new language/runtime expansion for the mastery window
- [x] Name the exact mastery cohort repos and keep them fixed for the roadmap
- [x] Add a weekly review ritual for scorecard metrics and dominant failure families
- [x] Define which environment-only failures are excluded from mastery scoring

### Baseline

- [x] Record the latest baseline for `first_pass_success_rate`
- [x] Record the latest baseline for `no_op_rate`
- [x] Record the latest baseline for `wrong_root_execution_rate`
- [x] Record the latest baseline for `retries_per_success`
- [x] Record app-backed artifact publish success and missing-screenshot failure counts
- [x] Record preflight readiness and canary freshness for all active mastery roots and profiles

### Verification

- [x] Capture one status/dashboard snapshot for the baseline
- [x] Link the exact commands or screenshots used for the baseline readout

## Phase 2: First-Pass Success And Wrong-Root Reduction

Status: `Done`

### Kickoff Notes

- Initial live baseline shows `wrong_root_execution_rate` is already `0.0` on the current sample, so the first Phase 2 risk is silent contract drift rather than a visibly high wrong-root rate.
- Initial live baseline shows `no_op_rate` at `0.4828`, so Phase 2 should prioritize tighter issue contracts and earlier clarification over extra retries.
- Current persisted no-op evidence is concentrated in `serialized_patch` mode: the latest store fingerprint is `execution_contract|serialized_patch|no_patch`, and the current local `healer_attempts` table contains `6` recorded `no_patch` failures.
- Recent app-backed evidence is still mixed: the Phase 1 baseline slice had `2` attempts with artifact proof ready and `2` attempts with missing required artifacts.
- First landed Phase 2 hardening slice:
  - normalize nested sandbox `cd` paths back to the known sandbox root when inferring `execution_root`
  - flag `Validation:` command roots that conflict with declared output targets as clarification-worthy contract mismatches
  - expanded regression coverage so explicit Node validation commands using `pnpm`, `yarn`, and `bun` remain preserved as issue-contract signals
  - captured the no-op audit in this roadmap so future parser/prompt changes can be measured against the same baseline
- Second landed Phase 2 hardening slice:
  - add a replay-style runner test for serialized-patch narrative-only output on a code-change task
  - reclassify serialized-patch summary-only output from generic `no_patch` / masked `no_code_diff` outcomes into explicit `no_workspace_change:narrative_only`
  - preserve the stronger execution-contract fingerprint for this lane: `execution_contract|serialized_patch|no_workspace_change:narrative_only`
- Third landed Phase 2 hardening slice:
  - generate explicit `Execution root:` contract lines for browser-backed and mixed-root issue drafts instead of relying on targets plus validation alone
  - require browser-backed issue drafts to round-trip an explicit `Runtime profile:` through `compile_task_spec(...)`
  - prove the runtime-contract surface across all active browser-backed roots: `node-next-web`, `ruby-rails-web`, and `java-spring-web`
  - keep sandbox issue creation compatible with the stricter Node app contract by accepting `Execution root:` and `Runtime profile:` lines in the Python/JS-only draft filter
  - ignore slash-heavy non-contract bullets when deciding whether a draft stays within the Python/JS-only cohort
- Fourth landed Phase 2 hardening slice:
  - extend the serialized-patch replay pack beyond plain status summaries to cover connector turns that end with a final answer but no workspace edits
  - add a dedicated replay for commentary-only detailed connector turns so `connector_noop` stays distinct from narrative-only no-op behavior
  - keep the failure fingerprints stable for the highest-repeat no-op cluster in this phase: `execution_contract|serialized_patch|no_workspace_change:narrative_only` and `execution_contract|serialized_patch|no_workspace_change:connector_noop`
- Fifth landed Phase 2 hardening slice:
  - draft validation now rejects issue bodies whose `Validation:` commands are not explicitly rooted to the parsed `execution_root`
  - this turns focused validation from a convention into an enforced generator invariant for active sandbox and app-backed drafts
- Sixth landed Phase 2 replay-pack slice:
  - add an explicit wrong-root replay pack at the contract-lint layer covering ambiguous roots, validation-root mismatch, and explicit execution-root resolution
  - add an explicit no-op replay pack at the runner layer covering narrative-only output, final-answer-without-edits, commentary-only turns, and runtime-artifact-only workspace changes
  - verify both replay packs inside the broader Phase 2 routing/no-op slice so they stay coupled to the real parser, loop, and runner behaviors instead of living as isolated helper checks
- Seventh landed Phase 2 measurement slice:
  - re-ran the live `status` snapshot after the contract and no-op hardening landed
  - current reliability rates are unchanged on the same live cohort: `first_pass_success_rate = 0.2727`, `wrong_root_execution_rate = 0.0`, and `no_op_rate = 0.4828`
  - this confirms the current Phase 2 work is guardrail coverage so far; the live metrics will only move after new attempts run through the tightened paths

### Contract And Routing

- [x] Audit the top wrong-root and no-op failure families from recent attempts
- [x] Tighten issue-contract generation for mixed-root and app-backed issues
- [x] Tighten task-spec parsing where execution-root ambiguity remains
- [x] Require focused validation commands for every high-value mixed-root reference issue

### Replay And Regression Guards

- [x] Build a replay pack of known wrong-root scenarios
- [x] Build a replay pack of known no-op / low-determinism scenarios
- [x] Add or extend focused regression tests for the highest-repeat routing failures

### Verification

- [x] `pytest tests/test_healer_task_spec.py tests/test_healer_loop.py -q`
- [x] `pytest tests/e2e/test_flow_healer_e2e.py -k mixed_repo_sandbox -v`
- [x] `pytest tests/test_healer_runner.py -k serialized_patch_mode_reclassifies_narrative_only_no_patch -q`
- [x] `pytest tests/test_healer_runner.py -k 'patch_apply_failure or malformed_diff or no_workspace_change or narrative_only or serialized_patch_mode_reclassifies' -q`
- [x] `pytest tests/test_issue_generation.py tests/test_create_sandbox_issues.py -q`
- [x] `pytest tests/test_healer_task_spec.py -k 'explicit_execution_root_field or runtime_profile' -q`
- [x] `pytest tests/test_healer_runner.py -k 'serialized_patch_mode_reclassifies or final_answer_without_edits or commentary_only_turn_as_connector_noop' -q`
- [x] `pytest tests/test_healer_task_spec.py tests/test_healer_runner.py -k 'phase2_wrong_root_replay_pack or phase2_noop_replay_pack' -q`
- [x] `pytest tests/test_healer_task_spec.py tests/test_healer_loop.py tests/test_healer_runner.py tests/test_issue_generation.py tests/test_create_sandbox_issues.py -q`
- [x] `pytest tests/test_healer_task_spec.py tests/test_healer_loop.py tests/test_healer_runner.py tests/test_issue_generation.py -q`
- [x] `python -m flow_healer.cli --config config.yaml status --repo flow-healer-self`
- [x] Re-run the replay pack after each routing improvement
- [x] Record whether each improvement moved `wrong_root_execution_rate` or `no_op_rate`

## Phase 3: Browser Evidence, Preflight, And Canary Hardening

Status: `Done`

### Current Proof Notes

- Browser evidence completeness now has first-class code-level checks for missing screenshots, missing logs, and auth/session drift classification in [browser_harness.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/browser_harness.py).
- Two consecutive preflight refreshes now preserve prior state and expose `stably_ready_roots`; the current cached summary shows all `35` mastery roots as `ready`, with `35` `stably_ready_roots` and no remaining blockers on this host.
- Live runtime-profile status after the repo-identity/runtime-profile cutover:
  - `node-next-web`: healthy, `last_canary_at=2026-03-12 08:03:50`
  - `ruby-rails-web`: healthy, `last_canary_at=2026-03-12 08:04:04`
  - `java-spring-web`: healthy, `last_canary_at=2026-03-12 08:10:06`
- The final live blocker from earlier in the night is now resolved:
  - `go`, `rust`, and `openjdk` are installed locally
  - the Java reference app now boots under the shipped `./gradlew` contract
  - PR `#932` merged after the CI-status reconciliation fix stopped treating superseded cancelled runs as live failures

### Browser Evidence

- [x] Create a mastery-specific browser-evidence checklist for app-backed runs
- [x] Verify screenshot, console-log, and network-log completeness on all active app-backed mastery profiles
- [x] Track fixture/auth-state drift separately from generic browser flake
- [x] Track missing-screenshot failures as a first-class mastery blocker

### Preflight

- [x] Review preflight readiness for every active mastery root
- [x] Turn recurring preflight blockers into explicit remediation tasks instead of ad hoc fixes
- [x] Require two consecutive `ready` preflight refreshes before calling a root stable

### Canary Health

- [x] Verify all active app runtime profiles have a successful canary within 7 days
- [x] Verify stale runtime profiles remain empty unless intentionally offline
- [x] Review canary failure reasons weekly and bucket them into deterministic vs environment drift

### Verification

- [x] Run the focused reliability/canary suite for each completed slice
- [x] Link one recent proof item for each active runtime profile

Phase 3 verification proof:

- Focused slice suite:
  - `pytest tests/test_browser_harness.py tests/test_healer_preflight.py tests/test_reliability_canary.py -q`
- Phase 2 + Phase 3 regression:
  - `pytest tests/test_healer_task_spec.py tests/test_healer_loop.py tests/test_healer_runner.py tests/test_issue_generation.py tests/test_browser_harness.py tests/test_healer_preflight.py tests/test_reliability_canary.py -q`
- Service/runtime freshness regression:
  - `pytest tests/test_service.py -k 'staleness_from_recent_activity or harness_health' -q`
- Live status proof:
  - snapshot file: `/tmp/flow-healer-final-live.json`
  - `node-next-web`: healthy, `last_canary_at=2026-03-12 08:03:50`
  - `ruby-rails-web`: healthy, `last_canary_at=2026-03-12 08:04:04`
  - `java-spring-web`: healthy, `last_canary_at=2026-03-12 08:10:06`
- Live preflight proof:
  - first refresh: `/tmp/flow-healer-preflight-after-runtimes-1.json`
  - second refresh: `/tmp/flow-healer-preflight-after-runtimes-2.json`
  - cached stable summary after the second refresh: `35` stably ready roots, no blocked roots
- Live PR reconciliation proof:
  - PR `#932` merged at `2026-03-12T08:03:43Z` after the CI summarizer fix

## Phase 4: Multi-Repo Determinism

Status: `Partial`

### Fixed Issue Pack Definition

The fixed weekly mastery issue pack is now locked to these issue bodies and IDs until the mastery window ends:

- `#926` Node smoke add contract
- `#927` Node Next auth session normalization
- `#928` Ruby Rails dashboard flow
- `#929` Java Spring login flow
- `#930` Python smoke math contract
- `#931` Node Next todo service contract

The first recorded weekly note for this pack is:

- [2026-03-12-mastery-weekly-note-01.md](/Users/cypher-server/Documents/code/flow-healer/docs/plans/2026-03-12-mastery-weekly-note-01.md)

### Fixed Weekly Issue Pack

- [x] Define a fixed issue pack across the mastery cohort
- [ ] Re-run the same issue pack weekly without changing the issue bodies
- [ ] Compare execution root, validation command, failure family, and retry count week-over-week
- [ ] Investigate any drift that appears without an intentional code change

### Determinism Targets

- [ ] Hold `first_pass_success_rate >= 0.80` for two consecutive weekly reviews
- [ ] Hold `wrong_root_execution_rate <= 0.03` for two consecutive weekly reviews
- [ ] Hold `no_op_rate <= 0.05` for two consecutive weekly reviews
- [ ] Hold `retries_per_success <= 0.75` for two consecutive weekly reviews
- [ ] Hold browser-evidence publishing at `>= 0.98` success with no missing required screenshots in the latest 20 mastery runs

### Verification

- [x] Publish a short weekly mastery note with the scorecard deltas
- [x] Capture the exact issue pack and commands used for each weekly run

## Expansion Unlock Gate

Status: `Later`

Do not reopen vertical expansion until all of the following are true:

- [ ] the mastery cohort is fixed and has remained stable for the review window
- [ ] all five scorecard targets are green for two consecutive weekly reviews
- [x] all three app-backed runtime profiles have recent successful canaries
- [x] all active mastery roots show stable preflight `ready`
- [ ] the latest fixed issue pack shows no unexpected routing or determinism drift

## Mastery Review Questions

Use these prompts in every weekly review:

- Are we improving first-pass success by clarifying contracts or only by retrying more?
- Which failure family is currently dominating wrong-root or no-op behavior?
- Which runtime profile is closest to becoming stale or flaky?
- Did any app-backed run publish incomplete evidence this week?
- Is there any pressure to add a new lane before current-lane metrics are green?
