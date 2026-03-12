# PRD: Flow Healer Horizontal Mastery To Completion

Date: `2026-03-12`

Owner: `flow-healer-self`

## Goal

Drive Flow Healer to a stable, defensible “horizontal mastery” state with continuous testing, log monitoring, and iterative bug fixing until high- and medium-priority defects are resolved and reliability signals stay green.

## Success Criteria

- critical execution paths are stable (`start`, `status`, PR reconciliation, issue processing)
- high/medium bugs are fixed with regression tests
- deterministic scorecard loop is automated and repeatable
- browser evidence, preflight, and canary health remain continuously observable
- issue-pack drift is measured and explained
- documentation and logs provide operator-grade traceability

## Scope

- In scope:
  - reliability and determinism hardening for existing supported lanes
  - CI/promotion freshness, contamination control, and preflight rigor
  - fixed-pack replay and drift automation
  - continuous health monitoring artifacts (status snapshots, drift notes, progress logs)
- Out of scope:
  - adding new language strategies
  - adding new app runtime profiles
  - major architecture redesign unrelated to reliability/determinism

## User Stories

### US-001: Keep Open PR Promotion Fresh During Long Runs

As an operator, I want open PR CI/promotion status to stay fresh while another issue is running so that successful PRs are not stuck in stale pending state.

Acceptance criteria:

- open PR maintenance runs during long processing windows
- CI summaries are force-refreshed on a throttled cadence
- promotion actions (requeue/approve/merge) continue while another issue is processing
- regression tests cover heartbeat maintenance behavior and throttling

### US-002: Prevent Ruby Lockfile Contamination Loops

As an operator, I want Ruby lockfile noise to be treated as generated runtime artifacts (unless explicitly requested), so retries do not stall on deterministic contamination.

Acceptance criteria:

- `Gemfile.lock` is classified consistently with other lockfiles for generated-artifact filtering
- unstaged regenerated lockfile noise is tolerated only as runtime artifact noise, not staged scope changes
- regression tests cover recurring Ruby lockfile regeneration

### US-003: Force Fresh Preflight For App Roots

As an operator, I want app-root issues to bypass stale preflight cache so runtime readiness is rechecked before mutation attempts.

Acceptance criteria:

- app-root execution (`e2e-apps/*`) calls preflight with `force=True`
- failure remains deterministic (`preflight_failed`) when readiness is broken
- regression tests verify force behavior for app roots

### US-004: Automate Fixed Issue-Pack Snapshots

As an operator, I want one command to snapshot fixed issue-pack determinism signals.

Acceptance criteria:

- snapshot export records body fingerprint, execution root, validation commands, failure family, retry count
- missing issue IDs are explicitly reported
- deterministic module + tests cover extraction behavior

### US-005: Automate Week-over-Week Drift Comparison

As an operator, I want machine-generated drift reports for fixed issue-pack snapshots.

Acceptance criteria:

- snapshot compare command outputs markdown and JSON
- drift includes execution root, validation commands, failure family, retry count, and body fingerprint changes
- enforce mode exits non-zero on unexpected drift

### US-006: Continuous Monitoring Log + Completion Score

As an operator, I want one living document tracking issue creation, fixes, tests, and remaining risks until completion score is `>=95/100`.

Acceptance criteria:

- dedicated continuous loop doc exists and is linked in docs index
- running log entries include timestamp, issue/fix item, test evidence, and remaining blockers
- completion score is explicitly tracked and updated as work lands

## Risks

- long-running issue processing can still mask unrelated lane regressions without periodic maintenance
- nondeterministic app dependencies can produce repeated retries without clear operator guidance
- weekly drift claims can be misleading without consistent snapshot commands

## Validation Plan

- code-level regressions:
  - `pytest tests/test_healer_loop.py tests/test_healer_runner.py tests/test_mastery_determinism.py -q`
- reliability slices:
  - `pytest tests/test_browser_harness.py tests/test_healer_preflight.py tests/test_reliability_canary.py -q`
- live ops evidence:
  - `python -m flow_healer.cli --config ~/.flow-healer/config.yaml status --repo flow-healer-self`
  - `python scripts/export_mastery_issue_pack_snapshot.py ...`
  - `python scripts/compare_mastery_issue_pack_snapshots.py ...`
