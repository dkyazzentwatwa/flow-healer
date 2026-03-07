# Path Prediction And Lock Scoping Research Plan

## Goal

Improve Flow Healer's path prediction and lock scoping so concurrent fixes can start earlier, collide less often, and avoid wasting proposer turns on lock conflicts discovered after edits are already made.

## Current Baseline In This Repo

The current system is safe, but it leaves throughput on the table:

- [`src/flow_healer/healer_locks.py`](src/flow_healer/healer_locks.py) predicts locks from path-like tokens in issue text, then escalates mostly by path count.
- [`src/flow_healer/healer_loop.py`](src/flow_healer/healer_loop.py) compiles a richer task spec and extracts targeted tests, but it still calls the text-only predictor before the run and upgrades locks only after the proposer has already edited files.
- [`src/flow_healer/healer_dispatcher.py`](src/flow_healer/healer_dispatcher.py) acquires predicted locks one key at a time and rolls back if a later key conflicts.
- [`src/flow_healer/store.py`](src/flow_healer/store.py) stores lock rows in SQLite and checks overlap in Python after loading all live locks.
- [`src/flow_healer/healer_memory.py`](src/flow_healer/healer_memory.py) already records predicted and actual lock sets, which gives phase 1 enough telemetry to measure prediction quality without introducing ML.

## Research Findings

### 1. Treat file scope as a pathset problem, not a token problem

Git's `pathspec` model is the right mental model here: the unit of scoped work is a deliberate set of paths, not just any token in free-form issue text. That points toward a predictor that merges several deterministic signals into one scored pathset before acquiring locks.

Why it matters here:

- `compile_task_spec(...)` already gives explicit `output_targets` for artifact and doc tasks.
- The loop already extracts targeted tests from the issue body.
- Historical successful diffs can be reused as a deterministic prior without introducing stochastic behavior.

Source:

- Git glossary on `pathspec`: <https://git-scm.com/docs/gitglossary>

### 2. Use stable machine-readable Git outputs when adding repo-aware heuristics

If prediction logic grows beyond literal path mentions, it should still rely on script-stable Git interfaces. Git documents `status --porcelain` and `worktree list --porcelain` specifically for scripting, so those are safe inputs for future repo-area heuristics, workspace safety checks, and worktree-aware planning.

Why it matters here:

- A planning pass can safely reason about repo state without parsing human-oriented output.
- Worktree-aware lock planning can stay deterministic and testable.

Sources:

- Git status porcelain: <https://git-scm.com/docs/git-status>
- Git worktree porcelain: <https://git-scm.com/docs/git-worktree>

### 3. Repo-area priors should look more like CODEOWNERS than regex soup

GitHub's `CODEOWNERS` pattern model is useful even if ownership itself is not the goal. It provides a clean precedent for grouping a repo into stable path families such as `docs/`, `tests/`, `src/flow_healer/`, and root configuration files.

Why it matters here:

- Lock escalation should depend on spread across repo areas, not only on file count.
- The predictor can assign lightweight priors to common source-test-doc clusters without becoming opaque.

Source:

- GitHub CODEOWNERS: <https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners>

### 4. SQLite should own atomicity, while Python keeps overlap semantics

SQLite transactions are the right place to guarantee all-or-nothing multi-key acquisition. `BEGIN IMMEDIATE` is useful when the system wants to reserve the write transaction up front rather than discover write contention late. WAL mode and partial indexes are relevant if concurrency rises and lock or attempt queries become a bottleneck.

Why it matters here:

- The store can preserve the current Python overlap logic in phase 1.
- The dispatcher should stop looping through one key at a time.
- Active-lock queries can later narrow to live rows instead of scanning the whole table.

Sources:

- SQLite transactions: <https://www.sqlite.org/lang_transaction.html>
- SQLite WAL: <https://www.sqlite.org/wal.html>
- SQLite partial indexes: <https://www.sqlite.org/partialindex.html>

## What The Research Points To

### Recommended design principles

- Predict from multiple deterministic signals before the proposer edits anything.
- Prefer narrow path locks when confidence is high.
- Escalate on repo spread, not raw path count.
- Keep late lock upgrades as an exception path, not the normal path.
- Persist prediction metadata so precision, recall, and over-breadth can be measured from real attempts.
- Treat `repo:*` as a last resort.

### Recommended signals, in order

1. `task_spec.output_targets`
2. Explicit path mentions in the issue title, body, and feedback context
3. Targeted tests found in the issue body
4. Inferred source-test sibling paths
5. Historical successful diff paths from healer memory
6. Small hardcoded repo-area priors for `docs/`, `tests/`, `src/flow_healer/`, and root config files

### Recommended reduction rules

- One explicit artifact target should stay a single `path:` lock.
- A matched source file and its direct test file should usually remain two `path:` locks.
- Many files inside one subtree should reduce to one `dir:` lock.
- A small number of disjoint files in different areas should remain multiple precise locks if they are still narrow.
- Escalate to `repo:*` only when predicted edits span several top-level areas or mix broad root config with source and test changes.

## Best Fit For Flow Healer

### Phase 1 recommendation

Keep the current exclusive lock model, but make it smarter:

1. Predict a scored pathset from deterministic signals.
2. Reduce that pathset into spread-aware lock keys.
3. Acquire the whole set atomically.
4. Run the proposer only after that lock set is held.
5. Record predicted paths versus actual diff paths for later tuning.

This is the highest-leverage path because it improves concurrency without changing the core safety model.

### Explicitly not recommended in phase 1

- Shared locks
- Intent locks with later promotion
- Sparse checkout enforcement
- Learned or probabilistic models
- Full semantic retrieval over past diffs

Those ideas may become useful later, but they add complexity before the deterministic path planning loop has been measured.

## Proposed Data Shapes

### Richer prediction result

```python
@dataclass(slots=True, frozen=True)
class LockPrediction:
    keys: list[str]
    source: str
    predicted_paths: list[str]
    explanation: list[str]
    confidence: int
```

### Optional reducer metadata

```python
@dataclass(slots=True, frozen=True)
class LockScopeSummary:
    keys: list[str]
    scope_family: str
    scope_roots: list[str]
```

The exact storage shape can stay modest in phase 1. If schema churn needs to stay light, `predicted_paths`, `explanation`, and reducer metadata can first live in attempt JSON fields or summaries before being normalized into dedicated columns.

## Implementation Plan

### Task 1: Expand deterministic path prediction

**Files**

- Modify `src/flow_healer/healer_locks.py`
- Modify `src/flow_healer/healer_task_spec.py` only if a small helper is needed for prediction inputs
- Add tests in `tests/test_healer_locks.py`

**Steps**

1. Add failing tests for:
   - output-target-only artifact tasks
   - root config files
   - source plus mirrored test prediction
   - broad mixed-scope escalation
2. Introduce a richer predictor entry point that accepts:
   - issue text
   - `output_targets`
   - `targeted_tests`
   - optional historical paths
3. Normalize and score paths with explanation labels such as `output_target`, `explicit_path`, `targeted_test`, `source_test_pair`, and `history_match`.
4. Keep `predict_lock_set(...)` as a compatibility wrapper if other call sites still expect the older shape.
5. Run `pytest tests/test_healer_locks.py -v`.

**Definition of done**

- Artifact-only doc tasks predict their explicit target directly.
- Source-test pairs are inferred deterministically.
- The predictor returns both chosen lock keys and the underlying predicted paths.

### Task 2: Make lock reduction spread-aware

**Files**

- Modify `src/flow_healer/healer_locks.py`
- Add tests in `tests/test_healer_locks.py`

**Steps**

1. Add failing tests that distinguish:
   - many files in one subtree
   - two narrow disjoint files
   - cross-area source plus docs plus root-config changes
2. Add helper functions such as:
   - `_top_level_area(path: str) -> str`
   - `_shared_scope_root(paths: list[str]) -> str`
   - `reduce_predicted_paths_to_lock_keys(paths: list[str]) -> list[str]`
3. Replace count-only escalation with spread-aware rules.
4. Run `pytest tests/test_healer_locks.py -k spread -v`.

**Definition of done**

- Small, disjoint edits no longer escalate unnecessarily.
- Wide repo-spread changes still escalate conservatively.
- Reducer choices are easy to explain in logs and tests.

### Task 3: Feed real run signals into the predictor

**Files**

- Modify `src/flow_healer/healer_loop.py`
- Modify `src/flow_healer/healer_memory.py`
- Add tests in `tests/test_healer_loop.py`

**Steps**

1. Add failing tests showing that:
   - `task_spec.output_targets` influence prediction
   - targeted tests influence prediction
   - recent successful paths can be offered as a deterministic prior
2. In the loop, pass the predictor:
   - issue title and body
   - compiled `task_spec.output_targets`
   - extracted targeted tests
   - a lightweight historical path bundle from memory
3. Persist `prediction_source`, predicted lock keys, and either predicted paths or explanation text in attempt metadata.
4. Run `pytest tests/test_healer_loop.py -v`.

**Definition of done**

- The loop stops throwing away signals it already has.
- Attempt records become useful for measuring prediction quality.

### Task 4: Move the decisive lock boundary before editing

**Files**

- Modify `src/flow_healer/healer_runner.py`
- Modify `src/flow_healer/healer_loop.py`
- Add tests in `tests/test_healer_runner.py`
- Add tests in `tests/test_healer_loop.py`

**Steps**

1. Add failing tests for:
   - final lock acquisition before the main edit pass
   - rejection of obviously out-of-scope diffs
   - a narrowly allowed sibling expansion path if the repo wants one
2. Add a lightweight planning boundary before editing. The first version should stay deterministic:
   - build the predicted pathset
   - reduce it to final lock keys
   - acquire that full set
   - only then allow the proposer to edit
3. Treat out-of-scope diffs as validation failure unless they are inside a tiny, explicitly allowed sibling expansion rule.
4. Run `pytest tests/test_healer_runner.py tests/test_healer_loop.py -v`.

**Definition of done**

- Late lock upgrades stop being the common case.
- Conflict discovery happens before the expensive edit phase.

### Task 5: Make multi-key lock acquisition atomic

**Files**

- Modify `src/flow_healer/healer_dispatcher.py`
- Modify `src/flow_healer/store.py`
- Add tests in `tests/test_healer_locks.py`
- Add tests in `tests/test_service.py`

**Steps**

1. Add failing tests showing that a lock set is acquired all-or-nothing.
2. Add a store method such as:

```python
def acquire_healer_locks_atomically(
    self,
    *,
    issue_id: str,
    lease_owner: str,
    lease_seconds: int,
    lock_keys: list[str],
) -> tuple[bool, str]:
    ...
```

3. Run conflict detection and inserts in one SQLite transaction.
4. Consider `BEGIN IMMEDIATE` so write intent is reserved at transaction start.
5. Update the dispatcher to use the atomic store method instead of per-key looping.
6. Run `pytest tests/test_healer_locks.py tests/test_service.py -v`.

**Definition of done**

- No partial acquisition survives a later conflict.
- Conflict reporting still returns the offending scope key.

### Task 6: Add lock telemetry that helps tuning

**Files**

- Modify `src/flow_healer/store.py`
- Modify `src/flow_healer/healer_loop.py`
- Modify `src/flow_healer/healer_memory.py`
- Add tests in `tests/test_healer_loop.py`
- Add tests in `tests/test_service.py`

**Steps**

1. Add failing tests for:
   - predicted path persistence
   - conflict reason persistence
   - late-upgrade counters or out-of-scope counters
   - a simple precision or over-breadth signal
2. Add the cheapest useful metadata first:
   - prediction explanations in attempt records
   - actual diff-derived lock keys
   - conflict scope and conflict phase
3. If store-side queries start to get hot, add scope-family metadata and partial indexes for active rows.
4. Run `pytest tests/test_healer_loop.py tests/test_service.py -v`.

**Definition of done**

- Operators can see whether prediction was too broad, too narrow, or accurate.
- Future tuning decisions come from attempt data instead of guesswork.

## Rollout Order

Recommended execution order:

1. Task 1
2. Task 2
3. Task 5
4. Task 3
5. Task 4
6. Task 6

This order improves prediction quality and acquisition safety before changing the editing boundary.

## Success Metrics

Track these after rollout:

- percentage of attempts that require no late lock upgrade
- percentage of attempts that hit prediction lock conflicts before edit start
- ratio of predicted paths to actual diff paths
- number of `repo:*` locks per 100 attempts
- average concurrent issues processed without collision

## Recommended First Slice

If only one small slice ships first, it should be:

1. multi-signal deterministic prediction
2. spread-aware reduction
3. atomic multi-key acquisition

That combination improves concurrency quickly while keeping the rest of the architecture intact.
