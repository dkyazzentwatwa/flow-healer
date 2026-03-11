# Roadmap

This roadmap outlines the next areas of investment for Flow Healer. It is intentionally directional rather than date-bound so the project can prioritize reliability and operator trust over shipping volume.

Execution tracker: `docs/plans/2026-03-11-harness-roadmap-master-checklist.md`

## Guiding Themes

- Keep autonomous changes safe, reviewable, and easy to audit.
- Expand deterministic signals before widening the scope of AI-generated fixes.
- Make multi-repo operations easier to observe, pause, tune, and recover.
- Improve the learning loop so each failed attempt sharpens the next one.

## Near-Term Priorities

### 1. Safer Healing Decisions

- Add richer policy controls for which issues, labels, authors, and file paths are eligible for autonomous work.
- Improve path prediction and lock scoping so concurrent fixes can move faster with less collision risk.
- Introduce stronger preflight checks before a proposal runs, including repo cleanliness, branch safety, and environment readiness.
- Build on the new verifier guardrails for docs-only, config-only, and high-risk code changes with clearer evidence capture and repo-specific tuning.

### 2. Better Verification and Review

- Support configurable test gates per repository, including targeted commands, smoke tests, and fallback verification strategies.
- Enrich reviewer feedback with clearer failure summaries, likely root causes, and suggestions for the next retry.
- Capture structured verification artifacts so operators can inspect why a change passed or failed.
- Improve PR follow-up handling so human comments can trigger narrower, better-scoped revisions.

### 3. Stronger Scanner Coverage

- Add more deterministic scan rules for common repo breakage, stale automation, and missing project hygiene files.
- Make scan findings easier to deduplicate across runs and easier to map back to prior healing attempts.
- Support severity tuning so teams can choose which findings should open issues automatically.
- Expand dry-run reporting so maintainers can preview scanner impact before enabling write actions.

## Mid-Term Priorities

### 4. Operator Visibility

- Add richer `status` output with attempt history, retry budgets, pause reasons, and current lock ownership.
- Produce more actionable doctor diagnostics for missing tools, invalid config, and broken repository state.
- Add exportable run summaries for CI or scheduled reporting.
- Improve local state introspection for SQLite-backed issues, attempts, scans, and lessons.

### 5. Learning and Retry Intelligence

- Store lessons in more structured forms so repeated failures can be categorized and reused more effectively.
- Distinguish transient failures from true fix-quality problems when deciding whether to retry.
- Feed reviewer comments, verifier results, and scan context into a more consistent retry prompt.
- Add controls for per-repo retry budgets, cooldown windows, and circuit-breaker thresholds.

### 6. Multi-Repo Operations

- Improve fairness and scheduling when many repositories compete for worker time.
- Add per-repo concurrency controls and clearer repo-level pause and maintenance modes.
- Support shared policy templates so fleets of repositories can inherit common healer settings.
- Make reconciliation more robust for orphaned worktrees, expired claims, and interrupted runs.

## Longer-Term Opportunities

### 7. Extensibility

- Introduce a cleaner plugin story for scanners, verifiers, and approval policies.
- Support repository-specific healer profiles without duplicating the entire config surface.
- Add integration points for external alerting, chat notifications, and incident systems.
- Provide a machine-readable event stream for dashboards and downstream tooling.

### 8. Developer Experience

- Improve onboarding with opinionated starter configs for common repo types.
- Add example environments and reproducible local demo flows.
- Strengthen CLI ergonomics with clearer progress output and operator-focused help text.
- Expand documentation for architecture, failure modes, and day-two operations.

### 9. Trust and Governance

- Add clearer audit trails for who approved work, what policy allowed it, and what evidence supported the PR.
- Support finer-grained approval workflows for sensitive repositories and protected file areas.
- Improve redaction and secret-safety handling for issue context, logs, and stored lessons.
- Define operational guardrails for running Flow Healer in more regulated environments.

## Definition of Progress

The roadmap is working if Flow Healer can safely process more issues, across more repositories, with less operator babysitting and more predictable verification outcomes. Progress should be measured by fix quality, recovery behavior, and operator confidence, not just by throughput.
