# Trust Follow-Ups Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the next trust-and-adoption slices after the canonical trust payload: issue-level explainability, contract lint/remediation, policy-driven throttle/quarantine, and phased validation/promotion.

**Architecture:** Reuse the existing issue parser, healer loop, status rows, issue-comment/status surfaces, and GitHub workflows. Each follow-up slice should extend the current trust model instead of introducing competing state machines.

**Tech Stack:** Python 3.11, pytest, GitHub workflows, existing Flow Healer service/loop/dashboard modules.

---

### Task 1: Issue-Level “Why This Ran / Why Not”

**Primary files:**
- `src/flow_healer/healer_loop.py`
- `src/flow_healer/service.py`
- `src/flow_healer/web_dashboard.py`
- `tests/test_healer_loop.py`
- `tests/test_service.py`
- `tests/test_web_dashboard.py`

**Deliverable:**
- Every queued, skipped, or clarification-blocked issue gets a stable reason code plus human-readable explanation.
- `status_rows()` exposes per-issue explainability fields.
- Dashboard/activity views can show why an issue ran, was skipped, or was paused.

**Checklist:**
- Add a normalized reason model for issue eligibility and skip outcomes.
- Capture reasons for at least: missing labels, low confidence, missing contract fields, paused repo, circuit breaker open, infra pause, connector/tracker unavailable.
- Reuse existing issue comment/status posting to avoid duplicate explanation logic.
- Add tests for both machine-readable reason codes and human-readable summaries.

### Task 2: Contract Linter + Remediation Flow

**Primary files:**
- `src/flow_healer/healer_task_spec.py`
- `src/flow_healer/healer_loop.py`
- `tests/test_healer_task_spec.py`
- `tests/test_healer_loop.py`
- `.github/workflows/`
- `.github/ISSUE_TEMPLATE/`

**Deliverable:**
- A first-class contract linter that validates issue bodies before healing.
- A remediation path that comments with a corrected skeleton instead of silently failing or only labeling `needs_clarification`.

**Checklist:**
- Extract contract validation into a reusable helper with structured error categories.
- Define contract lint outcomes for: missing required outputs, missing validation, ambiguous execution root, low parse confidence, unsafe scope.
- Add a GitHub workflow or script entrypoint to lint issue contracts on issue open/edit/label changes.
- Upgrade the clarification/remediation comment to include a minimally corrected contract skeleton based on the current issue body.
- Add tests for strict and lenient contract modes, including remediation copy.

### Task 3: Policy-Driven Throttle / Quarantine Engine

**Primary files:**
- `src/flow_healer/healer_loop.py`
- `src/flow_healer/service.py`
- `src/flow_healer/config.py`
- `tests/test_healer_loop.py`
- `tests/test_service.py`

**Deliverable:**
- Replace “retry happened” with explicit policy outcomes such as retry, throttle, pause, quarantine, or require-human-fix.
- Surface the chosen policy in status rows and trust evidence.

**Checklist:**
- Define a small stable policy vocabulary and precedence order.
- Drive policy decisions from existing signals: failure domain, retry playbook metrics, failure fingerprints, infra pause, needs clarification, and breaker state.
- Add repo-level throttle/backpressure when repeated infra or contract failures dominate.
- Expose current policy outcome and recommendation through `status_rows()` and the dashboard trust surface.
- Add tests for infra-heavy, contract-heavy, repeated no-op, and repeated wrong-root scenarios.

### Task 4: Phased Validation / Promotion States

**Primary files:**
- `src/flow_healer/healer_runner.py`
- `src/flow_healer/healer_verifier.py`
- `src/flow_healer/healer_loop.py`
- `src/flow_healer/service.py`
- `src/flow_healer/web_dashboard.py`
- `.github/workflows/03-verify-pr.yml`
- `.github/workflows/04-merge-close.yml`
- `tests/test_healer_runner.py`
- `tests/test_healer_loop.py`
- `tests/test_service.py`

**Deliverable:**
- Separate fast validation from full validation and expose promotion-oriented states instead of one flat pass/fail model.

**Checklist:**
- Add a minimal validation lane model: `fast_pass`, `full_pass`, `promotion_ready`, `merge_blocked`.
- Keep existing verification behavior intact while introducing a cheap-first lane selection strategy.
- Expose lane/status details in recent attempts, status rows, and dashboard trust/evidence surfaces.
- Gate merge/promotion behavior on the phased state instead of raw PR-open success.
- Add tests covering lane selection, promotion readiness, and merge-blocked reporting.

### Verification Order

1. Implement Task 1 and Task 2 first; they improve explainability and contract quality before changing runtime behavior.
2. Implement Task 3 next; it depends on clear reason codes and contract categories.
3. Implement Task 4 last; it depends on the policy layer and should reuse the newer explainability surfaces.
4. After each task, run focused module tests, then `pytest -p no:cacheprovider -q` before closing the slice.
