# Path Prediction and Lock Scoping: Research-Driven Delivery Plan

## Scope

- Task: expand and harden the path prediction plan in this file only.
- Constraint: keep all behavioral changes scoped to the path-prediction workstream (`path:create-plan-docs-for-path-prediction.md`) and preserve existing verified behavior.
- Run mode: artifact-only docs/research.

## Goal

Improve Flow Healer’s path prediction and lock scoping so proposer runs:

1. predict lock scope from trusted contract signals before editing begins,
2. acquire the smallest safe key set up front,
3. avoid post-edit lock escalation whenever possible,
4. preserve an auditable explainable trail for calibration.

## Research Synthesis

### 1) Path prediction should be a first-class pathset decision

Git defines `pathspec` as the explicit mechanism to limit operations to subsets of the tree, including directory prefixes and wildcard/glob matching. This is stronger than informal text extraction and maps directly to a deterministic pathset model: a task should first become a set of intentional paths, then a reduced lock key set.

- Source: Git glossary `pathspec` semantics (directory-prefix scope and matching behavior).
- Practical implication: prioritize explicit paths first; reduce by deterministic path families.

### 2) Scriptability depends on stable machine-parsable outputs

Git documents `--porcelain` formats as stable and safe for scripts, unlike human-readable status output. That avoids lock predictions drifting due to output formatting changes.

- Source: `git status --porcelain` guarantees stable output between versions/config.
- Practical implication: if runtime hints ever use git state, only consume stable formats.

### 3) Family-like precedence and specificity patterns are proven and durable

GitHub’s CODEOWNERS model demonstrates predictable specificity and precedence semantics over path patterns. That model is a useful analogy for lock scoping: prioritize specific local patterns and only escalate when spread/depth increases the contention risk.

- Source: CODEOWNERS path patterns, path precedence, and wildcard behavior.
- Practical implication: prefer narrow path clusters; escalate to family-level locks by policy, not by raw path count.

### 4) Atomic lock acquisition belongs in SQLite write transactions

SQLite supports one simultaneous write transaction per database; `BEGIN IMMEDIATE` fails fast if another writer is active (`SQLITE_BUSY`) and avoids partial acquisition churn. In WAL mode, this write lock pattern coexists with reader concurrency.

- Sources: SQLite transaction docs, `BEGIN IMMEDIATE` semantics and single-writer model; WAL concurrency notes.
- Practical implication: acquire the full predicted key set in one atomic store-level transaction, and return a single conflict result.

### 5) History is useful only as bounded, deterministic prior

Change-impact literature shows historical context can improve prediction, but deterministic scoring is a safer phase-1 choice than model training.

- Sources: Musco et al. (2015) on learning change impact from history; Sangle et al. (2020) on bug localization with historical + structural context.
- Practical implication: apply history only as a bounded bump, never as a hard escalation source in phase 1.

## Current Baseline (Observed)

- `predict_lock_set(...)` exists and is currently fed primarily free-form issue text.
- `targeted_tests` extraction is late in current flow.
- lock escalation is currently performed by acquiring predicted keys first, then upgrading via actual diff results.
- `healer_memory` already stores prediction and actual lock/diff signals.
- `store.py` already has SQLite WAL and lock/attempt persistence.

This means the foundation is mostly in place; we need to change sequencing, scoring, and reduction behavior.

## Design: Deterministic Multi-Signal Pathset Predictor

### Input priority (highest to lowest)

1. `HealerTaskSpec.output_targets`
2. explicit path references in issue title/body/operator instructions
3. explicit targeted tests extracted from issue text
4. deterministic source/test sibling inference
5. bounded historical sibling paths from successful heals
6. repo-family priors for tie-breaking

### Data model (phase-1)
