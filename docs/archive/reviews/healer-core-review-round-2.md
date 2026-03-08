# healer-core-review-round-2

## Summary
- Reviewed `healer_runner.py`, `healer_loop.py`, `service.py`, and `healer_verifier.py` against the provided diff summary.
- The proposal correctly identifies the major artifact-only and gating gaps and keeps recommendations focused on preventing silent false positives.
- No source code was modified; this is a **code-review artifact** only.
- Test status in the proposal is limited to artifact-guardrail pass (`{"mode": "skipped_artifact_only", "failed_tests": 0}`), so runtime behavior was not exercised in this run.

## Findings
1. [high] Artifact-only verifier short-circuit removes all semantic validation for docs/config outputs.
   - `HealerVerifier.verify` returns success immediately when `_can_short_circuit_artifact_verification` is true.
   - In `artifact_only` mode this can mark malformed or wrong scope artifacts as passing without model review.

2. [high] `_recover_artifact_from_diff` cannot faithfully reconstruct deletions.
   - In `healer_runner.py`, `_recover_artifact_from_diff` drops `-` lines entirely and keeps context (` `) + additions (`+`).
   - A proposer-supplied diff that removes lines can silently produce a reconstructed file that still contains deleted content.

3. [medium] `_extract_artifact_content` fallback is too permissive with mixed fences.
   - For single-target artifacts, `require_explicit_path=False`, so the first non-diff fenced block (or plain text) can be materialized even if it is not the intended target content.
   - This can overwrite the target artifact with unintended prose/snippets.

4. [medium] Targeted test extraction misses common pytest node-id forms.
   - `_TARGETED_TEST_RE` in `healer_loop.py` only matches file-like patterns (e.g., `tests/..test.py`).
   - `tests/test_file.py::test_fn` and similar node ids are not captured, which weakens precision and causes broader test execution.

5. [medium] Test failure counting conflates targeted/full gate failures.
   - `_run_test_gates` increments `failed_tests` across both targeted and full checks.
   - In mixed failure modes the same issue can contribute to multiple increments, and this can trigger hard-stop behavior more aggressively than intended.

6. [low] `FlowHealerService.start(once=True)` has fragile per-repo cleanup.
   - `service.py` loops repos and calls `runtime.loop._tick_once()` directly without per-repo `try/finally`.
   - If one repo raises, later repos are skipped and runtime resources for prior repos may remain open.

7. [low] Single-run artifact extraction still lacks explicit content-shape checks.
   - `_materialize_artifact_from_output` validates only “looks like status update” heuristics before write.
   - A non-empty but structurally wrong artifact body can be accepted and staged.

## Low-risk Improvements
1. [high] Keep artifact-only fast path but enforce deterministic content checks before success.
   - Require required sections/format for expected report files (for example headings and scope markers) in addition to `verification_profile` and path checks.

2. [medium] Tighten artifact extraction requirements.
   - For any artifact mode, require explicit `path=` when multiple fenced blocks are present.
   - For single target, prefer explicit path marker when available and fail closed when no explicit marker matches.

3. [medium] Improve `PATH`-fenced diff recovery behavior.
   - Extend `_recover_artifact_from_diff` to preserve deletions in update mode where appropriate, or reject diffs for artifact-only writes unless they are strictly additive.

4. [low] Normalize targeted test parsing and gating semantics.
   - Expand regex to accept node-id syntax and quoted/path variants used by reporters.
   - Track failure buckets (`targeted_failed`, `full_failed`, `duplicate_failures`) so gate policy is explicit in each mode.

5. [low] Harden `FlowHealerService.start(once=True)` execution.
   - Use per-repo `try/finally` and aggregated error handling so one repo failure does not block the remaining repos and stores are always closed.

6. [low] Improve proposer-content classifier for artifact writes.
   - Add stronger guards before write: schema check (expected headings), language/header sanity, and disallow status-like prose even when not currently matched.

## Suggested Tests
1. `tests/test_healer_verifier.py`: add regression for `artifact_only` mode rejecting wrong/empty doc content when paths are docs/config.
2. `tests/test_healer_runner.py`: ensure `_materialize_artifact_from_output` refuses mixed-prose + fences unless explicit target path marker is provided for single-target writes.
3. `tests/test_healer_runner.py`: add deletion-sensitive `_recover_artifact_from_diff` case showing removed lines are not preserved unintentionally.
4. `tests/test_healer_runner.py`: `_run_test_gates` local_then_docker policy test covering targeted node-id (`::`) extraction and avoiding double-count inflation.
5. `tests/test_service.py`: `FlowHealerService.start(once=True)` resilience test where one repo raises and verify remaining repos still process + store close is called.
6. `tests/test_healer_loop.py`: targeted-tests detection edge-case test for `tests/foo.py::test_bar` and full-path issue body mentions.
