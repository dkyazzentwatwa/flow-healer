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
- lock escalation is currently performed by acquiring predicted keys first, then upgrading via diff results.
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

```python
@dataclass(frozen=True, slots=True)
class PredictedPath:
    path: str
    score: float
    reasons: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class LockPrediction:
    lock_keys: list[str]
    paths: list[PredictedPath]
    confidence: int  # 0-100
    missed_paths: tuple[str, ...] = ()
```

### Scoring contract

- `output_targets`: +100 each (max 300)
- explicit path mentions: +50 each (max 200)
- targeted tests: +45 each (max 135)
- sibling-inferred companion path: +20
- same family/cluster signal: +15
- successful historical sibling: +12 (max 60)
- unknown/untrusted signal: +0

Apply family penalty terms:

- path already covered by a parent lock candidate: cap marginal gain to avoid runaway duplication
- repeated path family signals: logarithmic decay
- cross-family dispersion penalty: +7 per unique family beyond first

Confidence score:

- `min(100, 100 - 5 * predicted_unique_families + 0.25 * total_unique_scored_paths)`
- clamp at >= 10 for any non-empty deterministic candidate set
- downgrade to `< 10` only if no direct signal was found (fallback plan)

### Candidate path extraction details

- explicit path extraction should normalize (`./`, duplicate slashes, trailing `*`, code fences) before scoring.
- normalize to POSIX-style paths.
- reject empty strings, non-existent local paths unless they are likely globs from issue text.
- deduplicate after normalization.

## Reduction policy (recommended)

The goal is minimal safe lock sets, where spread across repo families carries more weight than raw file count.

### Families

- `root` (config, lockfile, pyproject, setup, docs index, etc.)
- `src`
- `tests`
- `docs`
- `scripts`
- `deploy`
- `other`

### Family-aware reduction rules

1. if all paths in one family and `len(paths)<=3`, lock exact file keys
2. if one family and `len(paths)<=8`, lock nearest shared directory (max depth 3)
3. if two families and no root files, lock one family-level key per family plus explicit root files
4. if `len(unique_families) > 2` or `len(paths) > 8`, consider `src/* + tests/*` style family locks and explicit root lock for root files
5. if any root-config files are present, always include root lock key
6. if no high-confidence signal and no parseable path, keep conservative minimal fallback: `['repo_root']` and mark for telemetry review

Escalation behavior:

- never auto-escalate after edits in phase 1;
- diff-vs-prediction comparison drives telemetry and plan updates only.

## Implementation plan (phase 1)

### Phase 1A: prediction input shape and order of operations

1. In task compilation, extract/propagate:
   - `output_targets`
   - explicit target tests
   - issue body/title path mentions
2. Reorder flow so prediction happens after these signals are available but before proposer edits.
3. Add `PredictedPath`/`LockPrediction` dataclasses and return values from `predict_lock_set`.
4. Tag each predicted path with reasons for future auditability.

### Phase 1B: reduce and acquire atomically

1. Replace incremental key-by-key lock acquisition with one all-or-nothing transaction in store layer.
2. Use `BEGIN IMMEDIATE` for lock-set reservation.
3. Detect any conflicting lock in transaction and rollback once, returning one consolidated conflict summary.
4. On success, persist exact predicted lock keys and reasons atomically.

### Phase 1C: telemetry and learning hook

1. After propose/apply, map actual edited paths to lock keys.
2. Persist prediction envelope:
   - predicted keys
   - actual keys
   - coverage/recall metrics
   - missing and extra keys
   - confidence and reasons
3. Add a structured reconciliation artifact for offline tuning:
   - `prediction_recall`, `prediction_precision`, `lock_expansion_ratio`.

### Phase 1D: tests

1. Update lock prediction unit tests for:
   - ordered signal precedence
   - explicit path handling
   - targeted test-aware reduction
   - family-spread escalation
   - fallback behavior on low-signal/no-signal issue
2. Update lock transaction tests for all-or-nothing behavior.
3. Keep focused regression tests for upgrade paths (ensures no post-run escalation in normal flow).

## Acceptance criteria

1. For `>90%` of tasks with explicit `output_targets`, predicted lock set includes all target paths without broadening beyond 2 family-level keys in normal spread conditions.
2. In deterministic scenarios, conflict detection is single-pass and not key-by-key.
3. Post-run lock expansion occurs only on conflict/validation fallback, not as default control flow.
4. Coverage telemetry can show per-run:
   - recall at path level
   - recall at lock-key level
   - top 10 missed-path causes
5. Existing successful behavior remains stable (no mandatory changes to healer contract semantics outside path prediction).

## Rollout plan (safe order)

1. Add docs and scoring contracts.
2. Update only prediction inputs and reduction algorithm in lock path module.
3. Move lock acquisition to atomic store transaction.
4. Add telemetry output and reconciliation.
5. Increase test coverage for edge cases and conflict cases.
6. Review metrics after 200 runs before any cross-file escalation policy expansion.

## Open risks

- Test extraction false positives from issue snippets could over-narrow or over-broaden.
- Family heuristics might be too aggressive for monorepo-like repo layouts.
- Single-writer SQLite contention in very short tasks may increase retry loops; implement backoff around acquire attempt.

## Non-goals (phase 1)

- No ML/learned ranking in stage 1.
- No new lock backends.
- No behavioral changes to proposer output format.
- No speculative repo-wide scans beyond deterministic path derivation from task signals.

## Evidence-backed rationale

- Git pathspec supports intentional path subset modeling.
- Git porcelain output is stable for machine consumption.
- CODEOWNERS-style path precedence supports deterministic family-reduction decisions.
- SQLite transactions provide the atomicity needed for all-or-nothing lock reservation.
- Historical predictors improve hit-rate but should be bounded and explainable in phase 1.

References:

- Git glossary pathspec: <https://git-scm.com/docs/gitglossary>
- Git status porcelain: <https://git-scm.com/docs/git-status>
- SQLite transaction docs: <https://www.sqlite.org/lang_transaction.html>
- SQLite WAL docs: <https://sqlite.org/wal.html>
- CODEOWNERS docs: <https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners>
- Musco et al. 2015: <https://arxiv.org/abs/1512.07435>
- Sangle et al. 2020: <https://arxiv.org/abs/2011.03449>
