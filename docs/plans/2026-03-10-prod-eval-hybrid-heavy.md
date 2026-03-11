# Prod Eval Hybrid Heavy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a concrete 10-issue hybrid-heavy production-evaluation draft family and clear the quarantined Node Next healer worktree that contains merge-conflict contamination.

**Architecture:** Extend the existing issue-family catalog in `src/flow_healer/issue_generation.py` with a new 10-draft family that renders hybrid, control, and messy issue bodies while preserving existing validation and draft validation rules. Cover the new family with focused unit tests in `tests/test_issue_generation.py` and `tests/test_create_sandbox_issues.py`, then remove the stale issue-800 healer worktree using the existing git worktree workflow.

**Tech Stack:** Python, pytest, git worktree, existing sandbox issue generator.

---

### Task 1: Add failing tests for the new issue family

**Files:**
- Modify: `tests/test_issue_generation.py`
- Modify: `tests/test_create_sandbox_issues.py`

**Step 1:** Add a failing unit test that expects a new issue family to exist and emit exactly 10 drafts.
**Step 2:** Add assertions that the family includes the intended control, hybrid, and messy labels plus realistic human-readable body content.
**Step 3:** Add CLI validation coverage that accepts the new family.
**Step 4:** Run the focused tests and confirm they fail for the missing family.

### Task 2: Implement the issue family

**Files:**
- Modify: `src/flow_healer/issue_generation.py`

**Step 1:** Add a new family constant and expose it through `available_issue_families()` and `get_issue_templates()`.
**Step 2:** Extend issue rendering so templates can optionally provide richer body text instead of the default strict contract-only format.
**Step 3:** Add 10 concrete drafts matching the agreed 2 control / 6 hybrid / 2 messy split.
**Step 4:** Keep target paths and validation commands within existing sandbox validation rules.

### Task 3: Verify generator behavior

**Files:**
- Modify: `tests/test_issue_generation.py`
- Modify: `tests/test_create_sandbox_issues.py`

**Step 1:** Run focused pytest for the touched tests.
**Step 2:** Dry-run the new family through `scripts/create_sandbox_issues.py`.
**Step 3:** Confirm all 10 drafts validate and parse into task specs with execution roots and validation commands.

### Task 4: Clear the quarantined issue-800 healer worktree

**Files:**
- No source edits expected.

**Step 1:** Confirm the quarantine root cause is merge-conflict markers in the issue-800 healer worktree.
**Step 2:** Remove the stale/corrupt worktree with `git worktree remove --force`.
**Step 3:** Verify the worktree path is gone and no longer appears in `git worktree list`.
