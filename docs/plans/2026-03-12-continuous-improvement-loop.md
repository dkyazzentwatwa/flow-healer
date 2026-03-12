# Continuous Improvement Loop

Date started: `2026-03-12`

This document is the always-on operating contract for the horizontal mastery push. We keep iterating until the codebase is stable, well-documented, and high-priority bugs are fixed and verified.

## Charter

- Aggressively inspect for bugs, regressions, broken flows, weak error handling, UX issues, and missing edge-case coverage.
- Create actionable issues for each meaningful bug/weakness with:
  - title
  - severity/priority
  - affected files/components
  - reproduction
  - expected vs actual
  - proposed fix
- For UI/UX issues, include screenshots whenever possible.
- Do not stop at issue creation. Pick highest-impact open issue, fix, verify, then continue.
- After each fix:
  - run relevant tests
  - add/improve tests where coverage is missing
  - verify resolution
  - update issue status and results
- Continue without approval unless direction is ambiguous, destructive/irreversible, or blocked by missing credentials/permissions.
- Prioritize: crashes and broken core flows first, then data integrity/security/major UX, then lower-priority polish.

## Stop Conditions

Stop only when one of these is true:

- all reproducible high- and medium-priority issues are fixed and verified
- only low-priority/speculative issues remain
- a real blocker prevents further progress

## Done Criteria

- critical paths work
- major bugs are fixed
- tests pass
- regressions are checked
- issues are documented
- the project is in a defensible state

## Completion Score

- Current self-score: `95/100`
- Exit target: `>=95/100`
- Remaining to sustain `95+`:
  - keep weekly fixed-pack replays and drift notes current
  - maintain canary/preflight freshness evidence across review windows
  - continue closing or evidencing remaining high/medium open lanes

## Running Log

| Timestamp (UTC) | Type | Item | Result | Evidence |
| --- | --- | --- | --- | --- |
| `2026-03-12T08:28:00Z` | Fix | Keep open PR CI/promotion maintenance active during long-running processing | Implemented in `healer_loop`; tests added and passing | `pytest tests/test_healer_loop.py -k 'maintain_open_prs_during_processing or lease_heartbeat_runs_open_pr_maintenance_hook or auto_merge_open_pr_refreshes_stale_pending_ci_before_merging' -q` |
| `2026-03-12T08:31:00Z` | Improvement | Added fixed issue-pack determinism snapshot and drift-comparison primitives | New module + tests passing | `pytest tests/test_mastery_determinism.py -q` |
| `2026-03-12T08:31:15Z` | Evidence | Captured fixed-pack snapshot `run02a` | Snapshot recorded for 926-931 | `/tmp/mastery-pack-snapshot-2026-03-12-run02a.json` |
| `2026-03-12T10:34:00Z` | Fix | Prevent scope-limited swarm outcomes from triggering global infra pause | Swarm classifier hardened; redirect/scope failures stay `swarm_quarantine` | `pytest tests/test_healer_loop.py -k 'swarm_quarantine_scope_limited_redirect_failure_stays_issue_scoped' -q` |
| `2026-03-12T10:34:00Z` | Fix | Ruby local gate now bootstraps/falls back cleanly and excludes generated `bin/rspec` contamination | Added local bundle bootstrap/fallback + generated artifact filtering + regressions | `pytest tests/test_healer_runner.py -k 'run_tests_locally_falls_back_when_bundle_exec_rspec_missing or stage_workspace_changes_excludes_ruby_bundle_binstub_artifacts' -q` |
| `2026-03-12T10:51:55Z` | Evidence | Replayed Issue `#928` end-to-end after hardening | Lane progressed to `pr_open` (`PR #940`), no global infra pause | `flow-healer start --repo flow-healer-self --once` |
| `2026-03-12T10:55:44Z` | Evidence | Completed Java/Go/Rust native and live-smoke validation on this host | Go/Rust/Java commands green; Java `/healthz`, `/login`, `/dashboard` contract confirmed | `go test ./...`, `cargo test`, Java `./gradlew test --no-daemon`, Java `./gradlew bootRun` + `curl` transcript |
| `2026-03-12T10:58:00Z` | Fix | Preserve numeric zeroes in fixed-pack drift markdown output | `retry_count=0` now renders as `0` (not `-`) | `pytest tests/test_mastery_determinism.py -q` |
| `2026-03-12T11:04:00Z` | Fix | Stabilized healer-attempt ordering to prevent CI/e2e nondeterminism | `list_healer_attempts` now sorts by `attempt_no DESC` with deterministic tie-breakers | `pytest tests/test_healer_reconciler.py tests/e2e/test_flow_healer_e2e.py -k 'list_healer_attempts_prefers_attempt_no_when_started_at_ties or judgment_block_resumes_after_human_guidance' -q` |
