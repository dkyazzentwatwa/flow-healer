## Summary
- Reviewed `src/flow_healer/healer_runner.py`, `src/flow_healer/healer_loop.py`, `src/flow_healer/service.py`, and `src/flow_healer/healer_verifier.py` after the code-review artifact task-spec pass.
- Artifact-only mode works end-to-end, but the current verification/synthesis path has several correctness gaps that can allow malformed or unintended file content to be accepted without strong checks.

## Findings
- [high] `src/flow_healer/healer_verifier.py:_classify_change` + `src/flow_healer/healer_verifier.py:_can_short_circuit_artifact_verification`
  - Artifact-only tasks skip verifier model calls whenever the changed paths are docs/config-like and `validation_profile == "artifact_only"`.
  - This bypass removes any semantic quality gate for the review artifact, so a wrong or off-topic report can be accepted purely on patch/apply success.
- [medium] `src/flow_healer/healer_runner.py:_extract_artifact_content`
  - If no path-fenced block exists and the output is non-diff, the first fenced block is used as artifact content regardless of intent.
  - In multi-snippet responses this can capture the wrong block and write incorrect report content.
- [medium] `src/flow_healer/healer_runner.py:_materialize_artifact_from_output` + `src/flow_healer/healer_runner.py:_extract_artifact_content`
  - For a single output target, `require_explicit_path` is false, so the target file can be written from fallback text extraction even without explicit `path=` intent.
  - This increases risk of writing status/prose payloads to the target when the proposer emits mixed output.
- [medium] `src/flow_healer/healer_runner.py:_recover_artifact_from_diff`
  - Recovery for existing files rebuilds file text from context (`" "`) and additions (`"+"`) while always dropping deletions (`"-"`), so deletions in a generated diff are not reflected.
  - This can produce a false-positive “valid artifact” that silently reintroduces removed lines.
- [medium] `src/flow_healer/healer_loop.py:_process_claimed_issue` and `src/flow_healer/healer_runner.py:_run_test_gates`
  - `targeted_tests` detection is regex-limited, then both targeted and full pytest results are folded into the same failure count.
  - In mixed modes this can overcount failures and trigger unnecessary `failed_tests` hard-stops even when tests are stable but one runner fails partially.
- [low] `src/flow_healer/service.py:FlowHealerService.start` (once mode)
  - The `once` path does not use `try/finally`; a single repo failure can abort the command and leave downstream repos unprocessed, and store handles may remain open on mid-loop exceptions.

## Low-risk Improvements
- [low] `src/flow_healer/healer_verifier.py`
  - Keep artifact-only auto-path, but add a deterministic content shape check before pass (required headings, summary section, and expected scope markers) rather than hard short-circuiting all doc-only artifacts.
- [low] `src/flow_healer/healer_runner.py:_materialize_artifact_from_output`
  - Require explicit `path=` matching unless proposer output is a single fenced block with expected target language and exact `path` metadata.
- [low] `src/flow_healer/healer_runner.py:_looks_like_status_update_summary`
  - Harden the status-summary filter with stricter and broader patterns so prose-only replies are rejected before file writes.
- [low] `src/flow_healer/healer_loop.py:_TARGETED_TEST_RE` + `_run_test_gates`
  - Expand targeted test extraction to include nodeid forms (e.g., `tests/foo.py::test_bar`) and make failure counting policy explicit per mode.
- [low] `src/flow_healer/service.py:FlowHealerService.start` (once mode)
  - Add per-repo `try/finally`/error aggregation so a failure in one repo does not suppress remaining repos and all stores close deterministically.

## Suggested Tests
- Add a unit test for artifact-only verifier flow asserting a doc artifact with incorrect/empty content does not auto-pass.
- Add a unit test for `_materialize_artifact_from_output` with mixed prose + fences ensuring only intended target block is written.
- Add a unit test for `_recover_artifact_from_diff` covering deletion-heavy diffs and ensuring removals are preserved correctly.
- Add a unit test for `_run_test_gates` in `local_then_docker` to validate intended failure threshold semantics.
- Add a service-level test for `FlowHealerService.start(once=True)` where one repo raises to confirm subsequent repos still process and prior stores are closed.
