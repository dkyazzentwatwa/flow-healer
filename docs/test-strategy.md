# Test Strategy

This doc defines the testing pyramid for Flow Healer and what kind of regression to add for each escaped failure.

## Canonical Anchors

- `tests/`
- [docs/harness-smoke-checklist.md](/Users/cypher-server/Documents/code/flow-healer/docs/harness-smoke-checklist.md)
- [docs/e2e-stress/retry-failure-taxonomy.md](/Users/cypher-server/Documents/code/flow-healer/docs/e2e-stress/retry-failure-taxonomy.md)

## Test Layers

- unit tests: narrow behavior in parser, runner helpers, state helpers, connector helpers
- integration tests: loop, store, tracker, service, export assembly, and control-plane payload assembly
- lane/sandbox tests: `e2e-smoke/*` and `e2e-apps/*` contract coverage
- browser evidence tests: artifact capture, publish rules, app runtime flows
- canary and stress docs/runbooks: operator validation and drift detection

## What Blocks What

- parser and runner regressions should block contract or execution changes
- loop/store regressions should block retry, judgment, or state changes
- export/TUI/control-plane tests should block operator-surface contract changes
- browser evidence tests should block artifact/evidence contract changes

## What To Add When A Bug Escapes

- wrong issue parsing or wrong root: add task-spec tests
- wrong file edits or prompt/path behavior: add runner tests
- blind retries or bad routing: add loop tests
- stale runtime profile or evidence drift: add harness/canary tests plus doc updates
- lane-specific breakage: add or extend the affected lane guide and its smoke regression

## Preferred Verification Commands

Use focused slices before full-suite runs:

```bash
pytest tests/test_healer_task_spec.py -v
pytest tests/test_healer_runner.py -v
pytest tests/test_healer_loop.py -v
pytest tests/e2e/test_flow_healer_e2e.py -k mixed_repo_sandbox -v
```

For harness/evidence work:

```bash
python scripts/validate_repro_contract_examples.py
python scripts/check_harness_doc_drift.py
```
