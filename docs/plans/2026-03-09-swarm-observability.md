# Swarm Observability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add live swarm telemetry so Flow Healer exposes swarm lifecycle progress through healer events, runtime status, and short issue comments.

**Architecture:** Keep the swarm recovery behavior unchanged and add observability through callback-style telemetry emitted from `healer_swarm.py` and translated into runtime status, `healer_events`, and GitHub issue comments inside `healer_loop.py`. Extend focused tests around the existing swarm failure and verifier-recovery paths, and update dashboard normalization so new swarm events surface as live activity instead of generic event rows.

**Tech Stack:** Python, pytest, SQLite-backed observability tables, GitHub issue comments

---

### Task 1: Add swarm telemetry hooks

**Files:**
- Modify: `src/flow_healer/healer_swarm.py`
- Test: `tests/test_healer_swarm.py`

**Step 1: Write the failing test**

Add a swarm test that passes an event callback into `HealerSwarm.recover(...)` and asserts the callback receives `swarm_started`, analyzer `swarm_role_completed` events, `swarm_plan_ready`, repair `swarm_role_completed`, and `swarm_finished`.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_healer_swarm.py -k telemetry -v`
Expected: FAIL because `recover()` does not accept or emit telemetry callbacks yet.

**Step 3: Write minimal implementation**

Add callback support to `HealerSwarm.recover(...)` plus `run_parallel(...)` result callbacks so analyzer role completions can be emitted as they finish.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_healer_swarm.py -k telemetry -v`
Expected: PASS

### Task 2: Translate telemetry into events, status, and comments

**Files:**
- Modify: `src/flow_healer/healer_loop.py`
- Test: `tests/test_healer_loop.py`

**Step 1: Write the failing test**

Extend the existing swarm loop tests to assert:
- `healer_events` contains `swarm_started`, `swarm_role_completed`, `swarm_plan_ready`, and `swarm_finished`
- runtime status transitions through `swarm_analyzing` and `swarm_repairing`
- short issue comments are posted when swarm starts and when it recovers or gives up

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_healer_loop.py -k swarm -v`
Expected: FAIL because loop telemetry currently records only worker pulses and persists swarm summaries after the fact.

**Step 3: Write minimal implementation**

Add loop helpers that convert swarm telemetry callbacks into:
- `create_healer_event(...)` rows
- immediate runtime/heartbeat updates
- short `_post_issue_status(...)` comments for swarm start and finish

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_healer_loop.py -k swarm -v`
Expected: PASS

### Task 3: Surface swarm activity in observability views

**Files:**
- Modify: `src/flow_healer/web_dashboard.py`
- Test: `tests/test_web_dashboard.py`

**Step 1: Write the failing test**

Add a dashboard activity test that inserts a `swarm_started` or `swarm_finished` event and asserts the normalized row is treated as running swarm activity rather than a generic ok event.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_dashboard.py -k swarm -v`
Expected: FAIL because only `worker_pulse` is currently treated as live runtime activity.

**Step 3: Write minimal implementation**

Teach event normalization to classify `swarm_*` events as running activity and label the subsystem as swarm telemetry.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_dashboard.py -k swarm -v`
Expected: PASS

### Task 4: Run focused regression coverage

**Files:**
- Test: `tests/test_healer_swarm.py`
- Test: `tests/test_healer_loop.py`
- Test: `tests/test_web_dashboard.py`
- Test: `tests/test_service.py`

**Step 1: Run focused regression coverage**

Run: `pytest tests/test_healer_swarm.py tests/test_healer_loop.py tests/test_web_dashboard.py tests/test_service.py -q`
Expected: PASS

**Step 2: Summarize runtime implications**

Document which live signals now appear during swarm execution and note that the existing isolated smoke issues can be rerun afterward to confirm end-to-end visibility.
