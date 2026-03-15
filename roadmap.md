# Roadmap

This roadmap outlines the next areas of investment for Flow Healer. It is intentionally directional rather than date-bound so the project can prioritize reliability and operator trust over shipping volume.

## Guiding Themes

- Keep autonomous changes safe, reviewable, and easy to audit.
- Expand deterministic signals before widening the scope of AI-generated fixes.
- Make the operator experience fast and low-friction — review in 2 minutes, not 20.
- Improve the learning loop so each failed attempt sharpens the next one.

---

## Recently Shipped (2026-03-14)

MVP product baseline — the first version suitable for external users.

- **Product docs:** `docs/mvp.md`, `docs/safe-scope.md`, `docs/operator-workflow.md`, `docs/onboarding.md` — 15-minute setup guide, file scope contract, full review queue walkthrough
- **README rewrite:** product-first headline, workflow diagram, two issue classes, quick-start
- **Config annotations:** every field in `config.example.yaml` tagged `[solo dev]` or `[advanced]`
- **Evidence bundle:** standardized `EvidenceBundle` dataclass — every run produces one consistent operator-facing object feeding both PR body and TUI
- **Failure taxonomy:** 6 operator-visible failure codes (`validation_failed`, `diff_too_large`, `scope_violation`, `no_confident_fix`, `repo_blocked`, `review_required`) replacing raw internal strings in TUI
- **TUI restructure:** tab constants for Review Queue / Blocked / Repo Health / History; blocked-table for failed issues; `p` (pause repo) and `o` (open PR) key bindings
- **Doctor polish:** `flow-healer doctor` now outputs human-readable `✓`/`✗` lines with remediation hints by default; raw JSON available via `--no-plain`
- **Demo repo guide:** `docs/demo-repo-setup.md` — seeded issue templates, recording script, launch checklist

---

## Near-Term Priorities

### 1. MVP Launch Execution

Complete the launch checklist before sharing publicly:

- Set up the public demo repo (`flow-healer-demo`) with seeded Class A and B issues
- Record the 3-minute demo: issue → TUI → draft PR → operator approves
- Verify `pip install flow-healer` + `flow-healer doctor` returns green on a clean machine
- Ship ≥ 3 successful draft PRs per class on the demo repo (real GitHub PRs, public)

### 2. TUI Review-Queue-First Layout

The tab constants are defined — now wire the full layout:

- Restructure `compose()` in `FlowHealerApp` to top-level `TabbedContent` with Review Queue as the first/default tab
- Move the current queue DataTable into the Review Queue tab
- Populate Blocked tab from failed/blocked issues with operator failure codes
- Repo Health tab: circuit breaker state, success rate sparkline, recent attempt history
- History tab: closed/merged issues

### 3. Evidence Bundle Integration

`EvidenceBundle` exists — now use it:

- Wire `build_evidence_bundle()` into `healer_loop.py` at the point PRs are opened
- Feed `EvidenceBundle` into the PR body template (replace ad-hoc field extraction)
- Surface `verifier_summary` and `reviewer_summary` in the TUI detail pane

### 4. Safer Healing Decisions

- Improve path prediction and lock scoping so concurrent fixes can move faster with less collision risk
- Strengthen preflight checks before a proposal runs: repo cleanliness, branch safety, environment readiness
- Add richer policy controls for which file paths are eligible for autonomous work beyond the current scope rules

---

## Mid-Term Priorities

### 5. Better Verification and Review

- Support configurable test gates per repository, including targeted commands, smoke tests, and fallback strategies
- Enrich reviewer feedback with clearer failure summaries, likely root causes, and suggestions for the next retry
- Improve PR follow-up handling so human comments trigger narrower, better-scoped revisions

### 6. Scanner Coverage

- Add more deterministic scan rules for common repo breakage, stale automation, and missing hygiene files
- Support severity tuning so teams can choose which findings open issues automatically
- Expand dry-run reporting so maintainers can preview scanner impact before enabling write actions

### 7. Learning and Retry Intelligence

- Store lessons in more structured forms so repeated failures can be categorized and reused
- Distinguish transient failures from true fix-quality problems when deciding whether to retry
- Add per-repo retry budgets, cooldown windows, and circuit-breaker threshold controls

### 8. Multi-Repo Operations

- Improve fairness and scheduling when many repositories compete for worker time
- Support shared policy templates so fleets of repositories can inherit common healer settings
- Make reconciliation more robust for orphaned worktrees, expired claims, and interrupted runs

---

## Longer-Term Opportunities

### 9. Extensibility

- Cleaner plugin story for scanners, verifiers, and approval policies
- Repository-specific healer profiles without duplicating the entire config surface
- Integration points for external alerting, chat notifications, and incident systems
- Machine-readable event stream for dashboards and downstream tooling

### 10. Trust and Governance

- Clearer audit trails: who approved work, what policy allowed it, what evidence supported the PR
- Finer-grained approval workflows for sensitive repositories and protected file areas
- Improved redaction and secret-safety handling for issue context, logs, and stored lessons

---

## Definition of Progress

The roadmap is working if Flow Healer can safely process more issues, across more repositories, with less operator babysitting and more predictable verification outcomes. Progress should be measured by fix quality, recovery behavior, and operator confidence — not just throughput.

At MVP, the bar is simpler: a solo dev can get their first automated draft PR in 15 minutes, understand what happened and why, and trust that nothing unsafe was done without their review.
