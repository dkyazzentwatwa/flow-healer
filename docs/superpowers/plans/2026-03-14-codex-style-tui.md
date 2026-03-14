# Codex Style TUI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `flow-healer tui` into a genuinely interactive terminal UI with Codex-like compact panes, selection, wrapped detail views, and keyboard navigation while preserving `--once` text output.

**Architecture:** Keep the existing `curses` runtime for live mode and layer a small view-state model on top of the telemetry snapshot. Split responsibilities between snapshot formatting helpers, pane/tab selection state, and curses drawing so the interactive behavior is testable without a real terminal.

**Tech Stack:** Python, `curses`, pytest

---

## Chunk 1: View State And Text Rendering

### Task 1: Add failing tests for compact pane rendering

**Files:**
- Modify: `tests/test_tui.py`
- Modify: `src/flow_healer/tui.py`

- [ ] **Step 1: Write the failing test**

Add tests that cover:
- compact queue row rendering with truncated single-line summaries
- wrapped detail output for long event/log text
- footer/help text for interactive mode

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tui.py -v`
Expected: FAIL because the new helpers/layout text do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add formatting helpers in `src/flow_healer/tui.py` for:
- pane row summarization
- wrapped detail text
- interactive footer text

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tui.py -v`
Expected: PASS for the new rendering tests.

### Task 2: Add failing tests for pane and selection state

**Files:**
- Modify: `tests/test_tui.py`
- Modify: `src/flow_healer/tui.py`

- [ ] **Step 1: Write the failing test**

Add tests that cover:
- moving queue selection up/down within bounds
- switching between inspector tabs
- computing detail text from the selected pane item

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tui.py -v`
Expected: FAIL because there is no interactive state model yet.

- [ ] **Step 3: Write minimal implementation**

Add a small state object and pure helper functions for:
- active pane/tab
- selected row indices
- bounded navigation
- detail panel data lookup

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tui.py -v`
Expected: PASS for state behavior and existing tests.

## Chunk 2: Interactive Curses Layout

### Task 3: Build the multi-pane live renderer

**Files:**
- Modify: `src/flow_healer/tui.py`
- Test: `tests/test_tui.py`

- [ ] **Step 1: Write the failing test**

Add a focused test for producing pane-oriented screen lines from a snapshot and interactive state.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tui.py -v`
Expected: FAIL because the screen composer is still a flat text dump.

- [ ] **Step 3: Write minimal implementation**

Implement:
- summary header strip
- left queue pane
- right inspector pane with `Attempts`, `Events`, `Logs`
- bottom detail panel
- compact footer help bar

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tui.py -v`
Expected: PASS with pane-oriented output.

### Task 4: Wire keyboard controls into curses

**Files:**
- Modify: `src/flow_healer/tui.py`

- [ ] **Step 1: Write the failing test**

Extend the state tests to cover key handling for:
- `Up` / `Down`
- `Tab`
- `Left` / `Right`
- `r`

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tui.py -v`
Expected: FAIL because the key handlers do not map to state transitions yet.

- [ ] **Step 3: Write minimal implementation**

Update `_curses_main` and helper functions to:
- dispatch keys into state transitions
- refresh snapshot on demand
- keep painting within terminal width/height limits

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tui.py -v`
Expected: PASS for the new key handling tests.

## Chunk 3: Docs And Verification

### Task 5: Document the interactive TUI controls

**Files:**
- Modify: `docs/dashboard.md`
- Modify: `docs/usage.md`

- [ ] **Step 1: Write the doc change**

Describe the interactive live TUI layout, keybindings, and the difference between live mode and `--once`.

- [ ] **Step 2: Run focused verification**

Run: `pytest tests/test_tui.py -v`
Expected: PASS

Run: `pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 3: Summarize residual risk**

Note any terminal-size or curses-environment limitations if they cannot be covered by automated tests.
