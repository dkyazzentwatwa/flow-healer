# Harness Smoke Checklist

Run this checklist after harness-health changes, before declaring the reliability lane green, or during periodic maintenance.

## 1. Service And Dashboard

- Verify `flow-healer status --repo <repo-name>` shows `harness_health`.
- Verify the dashboard overview includes harness rollups and canary-profile visibility.
- Verify issue detail exposes repo-level `harness_health`.

## 2. Runtime Profile Freshness

- Confirm configured runtime profiles appear in `harness_health.runtime_profiles`.
- Confirm active profiles have a recent `last_seen_at` or `last_canary_at`.
- Confirm `stale_runtime_profiles.profiles` is empty unless a profile is intentionally offline.

## 3. Canary Execution

- Force or wait for one runtime-profile canary pass.
- Confirm `healer_app_runtime_canary_last_success_at:<profile>` updates.
- Confirm a failed canary increments `healer_harness_canary_failures` and records `healer_app_runtime_canary_last_failure_reason:<profile>`.

## 4. Browser Evidence

- Run one app-backed issue or canary that captures:
  - screenshot
  - console log
  - network log
- Confirm local files exist under the recorded `artifact_root`.
- Confirm the published artifact branch contains the expected evidence and `_meta.json`.

## 5. Artifact Retention

- Confirm a fresh artifact folder remains present after publication.
- Confirm an expired artifact folder is pruned on the next publish cycle.
- Confirm legacy folders without `_meta.json` are preserved.

## 6. Failure Counters

- Confirm artifact publication failures increment `healer_artifact_publish_failures`.
- Confirm browser capture failures increment `healer_browser_artifact_capture_failures`.
- Confirm reconciler cleanup increments orphan runtime and artifact cleanup counters.

## 7. Regression Guard

- Run the focused reliability suite:

```bash
pytest tests/test_config.py tests/test_healer_reconciler.py tests/test_healer_reconciler_resource_audit.py tests/test_healer_runner.py tests/test_healer_tracker.py tests/test_service.py tests/test_web_dashboard.py tests/test_healer_loop.py tests/test_reliability_canary.py -q
```

## 8. Repo Validation Scripts

- Run `python scripts/validate_repro_contract_examples.py`.
- Run `python scripts/check_harness_doc_drift.py`.
