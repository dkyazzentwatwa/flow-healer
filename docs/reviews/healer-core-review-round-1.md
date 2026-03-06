# healer-core-review-round-1

## Summary
- Reviewed `src/flow_healer/healer_runner.py`, `src/flow_healer/healer_loop.py`, `src/flow_healer/service.py`, and `src/flow_healer/healer_verifier.py` for code-review-only issues.
- No source files were edited.
- This artifact contains **high-priority, behavior-impacting, and low-risk** findings with suggested follow-up tests.
- High findings exist in this pass; there is no statement of “no high findings”.

## Findings
1. [high] Artifact-only verifier is effectively a bypass with no semantic checks.
   - `src/flow_healer/healer_verifier.py:22-31` returns `passed=True` immediately for `artifact_only` via `_can_short_circuit_artifact_verification`, skipping model-based confirmation entirely.
   - This means wrong content, scope drift, or malformed docs can be accepted without independent verification.

2. [high] Single-target artifact extraction can capture the wrong fenced block.
   - `src/flow_healer/healer_runner.py:390-463` sets `require_explicit_path=False` when only one target output path exists.
   - `_extract_artifact_content` then falls back to the first non-diff fenced block, so unrelated prose/code fences can be written to the requested artifact if the proposer response contains multiple sections.

3. [medium] Targeted test discovery misses standard pytest node-id formats.
   - The regex in `src/flow_healer/healer_loop.py:31` only matches plain `tests/...test*.py` file paths.
   - Extracted selection at `src/flow_healer/healer_loop.py:506` therefore ignores `tests/test_file.py::test_fn` or `::` selectors, weakening precision and potentially running broader tests than requested.

4. [medium] Test failure accounting conflates gate runs and can overcount failures.
   - In `src/flow_healer/healer_runner.py:254-285`, failed targeted and full gates both increment a shared `failed_tests` counter.
   - In `local_then_docker` mode, a single underlying issue can increment multiple times, causing false negatives against `healer_max_failed_tests_allowed`.

5. [medium] Full test suite still runs even after targeted test execution, with no mode to skip full when targeted was requested.
   - `src/flow_healer/healer_runner.py:254-285` always runs `pytest -q` for full suite after optional targeted runs.
   - This can add unnecessary runtime and amplify failure-count pressure for narrow artifact-only or patch-limited tasks.

6. [medium] One-shot run path has fragile cleanup and can leave repo state unclosed.
   - `src/flow_healer/service.py:51-60` runs `_tick_once()` in a loop without per-repo `try/finally`.
   - If one repo raises, later repos are skipped and `runtime.store.close()` may be skipped for that path, leaving open DB handles.

7. [low] Diff extraction is limited to strict fenced/split-git formats.
   - `src/flow_healer/healer_runner.py:206-214` only recognizes first ` 
