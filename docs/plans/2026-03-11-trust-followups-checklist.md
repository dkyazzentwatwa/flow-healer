# Trust Follow-Ups Checklist

## Coordination

- [x] Review [2026-03-11-trust-followups-implementation.md](/Users/cypher-server/Documents/code/flow-healer/docs/plans/2026-03-11-trust-followups-implementation.md)
- [x] Choose execution order for Tasks 1-4
- [x] Keep this checklist updated as slices land

## Task 1: Issue-Level “Why This Ran / Why Not”

- [x] Add normalized issue eligibility / skip reason codes
- [x] Expose per-issue reason summaries in `status_rows()`
- [ ] Reuse issue status/comment surfaces for human-readable explanations
- [x] Show issue-level run/skip reasons in the dashboard or activity views
- [ ] Add focused tests in `tests/test_healer_loop.py`
- [x] Add focused tests in `tests/test_service.py`
- [x] Add focused tests in `tests/test_web_dashboard.py`

## Task 2: Contract Linter + Remediation Flow

- [x] Extract reusable issue-contract validation helper(s)
- [x] Define lint categories for missing outputs, missing validation, ambiguous root, low confidence, and unsafe scope
- [x] Add an issue-contract lint workflow or script entrypoint
- [x] Upgrade clarification comments into remediation comments with a corrected contract skeleton
- [x] Update issue templates if needed to match the lint contract
- [x] Add focused tests in `tests/test_healer_task_spec.py`
- [x] Add focused tests in `tests/test_healer_loop.py`

## Task 3: Policy-Driven Throttle / Quarantine Engine

- [x] Define stable policy outcomes: retry, throttle, pause, quarantine, require-human-fix
- [x] Drive policy outcomes from existing failure-domain and retry signals
- [x] Add repo-level backpressure for repeated infra or contract failures
- [x] Surface policy outcome in trust/status payloads
- [ ] Add focused tests in `tests/test_healer_loop.py`
- [x] Add focused tests in `tests/test_service.py`

## Task 4: Phased Validation / Promotion States

- [x] Define phased validation states: `fast_pass`, `full_pass`, `promotion_ready`, `merge_blocked`
- [x] Add cheap-first lane selection without breaking current verification
- [x] Surface phased validation state in recent attempts and status rows
- [x] Update verify/merge workflow expectations if needed
- [x] Add focused tests in `tests/test_healer_runner.py`
- [ ] Add focused tests in `tests/test_healer_loop.py`
- [x] Add focused tests in `tests/test_service.py`

## Final Verification Per Slice

- [x] Run focused tests for the slice being implemented
- [x] Run `pytest -p no:cacheprovider -q`
- [x] Request code review before closing the slice
