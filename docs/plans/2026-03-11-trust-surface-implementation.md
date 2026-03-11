# Trust Surface Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship the first trust-and-adoption slice by adding a canonical repo trust payload and surfacing it consistently in status, doctor, and the web dashboard.

**Architecture:** Build a single trust summarizer in `service.py` that composes existing readiness, pause, circuit-breaker, tracker, connector, and reliability metrics into a stable `trust` object. Expose that object through existing status and doctor rows, then render the same trust state in the dashboard so operators see one explanation everywhere.

**Tech Stack:** Python 3.11, pytest, existing Flow Healer service/status JSON payloads, server-rendered dashboard HTML/JS.

---

### Task 1: Save the canonical trust contract

**Files:**
- Modify: `src/flow_healer/service.py`
- Test: `tests/test_service.py`

**Step 1: Write the failing tests**

Add service tests that expect:
- `status_rows()` returns `trust.state`, `trust.score`, `trust.summary`, `trust.why_runnable`, `trust.why_blocked`, `trust.recommended_operator_action`, `trust.dominant_failure_domain`, and `trust.evidence`.
- `doctor_rows()` returns the same `trust` payload.
- trust state changes correctly for:
  - healthy repo
  - paused repo
  - open circuit breaker
  - blocked/degraded preflight
  - tracker or connector availability failure

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_service.py -k trust -v`
Expected: FAIL because trust payload does not exist yet.

**Step 3: Write minimal implementation**

Add small private helpers in `service.py` to:
- summarize dominant failure domain from existing retry/failure metrics
- compute a normalized trust state and score from current repo signals
- generate concise runnable/blocked explanations and a recommended next action
- attach the resulting `trust` object to both status and doctor rows

Keep the implementation read-only over existing store/runtime data; do not add schema changes in this slice.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_service.py -k trust -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/flow_healer/service.py tests/test_service.py
git commit -m "feat: add canonical repo trust payload"
```

### Task 2: Surface trust in the dashboard

**Files:**
- Modify: `src/flow_healer/web_dashboard.py`
- Test: `tests/test_web_dashboard.py`

**Step 1: Write the failing tests**

Add dashboard tests that expect:
- overview payload rows include `trust`
- rendered HTML contains trust-state copy and operator recommendation text
- dashboard JS safely reads `row.trust` without breaking existing cards

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_dashboard.py -k trust -v`
Expected: FAIL because the dashboard does not render trust yet.

**Step 3: Write minimal implementation**

Update the dashboard to:
- display repo trust state, score, summary, and operator recommendation in a visible repo-level surface
- reuse the service-provided `trust` object instead of recomputing logic in JS
- keep existing scoreboard/telemetry cards intact

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_dashboard.py -k trust -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/flow_healer/web_dashboard.py tests/test_web_dashboard.py
git commit -m "feat: expose trust state in dashboard"
```

### Task 3: Integrate and verify the slice

**Files:**
- Modify: `docs/plans/2026-03-11-trust-surface-checklist.md`
- Verify: `tests/test_service.py`
- Verify: `tests/test_web_dashboard.py`
- Verify: `pytest`

**Step 1: Reconcile agent changes**

Review both slices together and make any integration fixes needed so the dashboard and service share the same trust contract.

**Step 2: Run focused verification**

Run:
- `pytest tests/test_service.py -v`
- `pytest tests/test_web_dashboard.py -v`

Expected: PASS

**Step 3: Run full verification**

Run: `pytest`
Expected: PASS

**Step 4: Update progress tracker**

Mark completed items in `docs/plans/2026-03-11-trust-surface-checklist.md`, record any deferred follow-ups, and note the next roadmap slice.

**Step 5: Commit**

```bash
git add docs/plans/2026-03-11-trust-surface-checklist.md
git commit -m "docs: update trust surface progress tracker"
```
