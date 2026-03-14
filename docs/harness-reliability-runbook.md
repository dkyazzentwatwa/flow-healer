# Harness Reliability Runbook

Use this runbook when Flow Healer reports harness-health drift, app-runtime canary failures, artifact publish problems, or stale runtime profiles.

## Check First

- `flow-healer status --repo <repo-name>`
- Dashboard repo row `harness_health`
- Recent attempts with `browser_failure_family`, `artifact_publish_status`, and `runtime_summary.app_harness`
- Reconciler counters:
  - `healer_orphan_runtime_reap_events`
  - `healer_orphan_artifact_cleanup_events`
- Harness counters:
  - `healer_artifact_publish_failures`
- `healer_browser_artifact_capture_failures`
- `healer_harness_canary_failures`

## Repo Validation

- `python scripts/validate_repro_contract_examples.py`
- `python scripts/check_harness_doc_drift.py`

## Triage Order

1. Identify the failure family: `runtime_boot`, `runtime_readiness`, `journey_step`, `artifact_capture`, or `artifact_publish`.
2. Check the affected profile in `harness_health.runtime_profiles`.
3. Inspect the newest attempt's `artifact_bundle` and `runtime_summary`.
4. Review reconciler cleanup counters before retrying.

## Artifact Publish Failures

1. Confirm local evidence still exists under the attempt `artifact_root`.
2. Verify artifact branch, retention days, and guardrail settings in repo config.
3. Check the latest tracker error and confirm GitHub branch write access.
4. Re-run one controlled pass after fixing the tracker or permission issue.

Healthy state:

- `artifact_publish_status` is `published`
- `harness_health.artifact_publish.last_failure_at` is empty or old
- published artifact links resolve from PR or issue comments

## Artifact Capture Failures

1. Confirm `browser_failure_family` is `artifact_capture`.
2. Inspect the local `artifact_root` for missing screenshot, console log, or network log files.
3. Verify Playwright and the runtime profile's readiness URL.
4. Re-run once after fixing the local prerequisite.

For browser-backed Node apps, the harness now performs one headless self-heal reload when the initial page load shows same-origin client asset failures such as missing JS or CSS chunks. If the reload clears the bootstrap failure, the journey continues inside the same attempt. If the same bootstrap failure repeats, the attempt still fails and surfaces `runtime_readiness` diagnostics instead of silently looping as a product bug.

Healthy state:

- screenshots exist for app-backed runs
- console and network logs are present
- `healer_browser_artifact_capture_failures` stops increasing after the fix

## Stale Runtime Profiles

A profile is stale when either:

- its config is structurally invalid now, such as a missing working directory or empty command
- it has not been seen in an app-backed run or successful canary within the stale-day window

Operator actions:

1. Compare config to the real app path and start command.
2. Check `healer_app_runtime_profile_last_seen_at:<profile>` and `healer_app_runtime_canary_last_success_at:<profile>`.
3. Remove intentionally retired profiles from config.
4. If the profile should still be active, fix the config and force one canary or app-backed run.

## Canary Failures

Canaries boot the runtime profile, open the readiness URL in the browser harness, capture screenshot plus console/network logs, and publish those artifacts.

1. Check `healer_app_runtime_canary_last_failure_reason:<profile>`.
2. Confirm the profile has a valid `cwd`, non-empty `command`, and `readiness_url`.
3. Confirm Playwright is installed on the worker.
4. Re-run a controlled healer pass after fixing the runtime or browser prerequisite.

Healthy state:

- `healer_app_runtime_canary_last_success_at:<profile>` is recent
- `harness_health.canary_profiles.failures` is stable
- the profile is not listed in `harness_health.stale_runtime_profiles.profiles`

For Node app profiles, transient client-bundle bootstrap failures should clear on the harness self-heal reload. Repeated same-origin asset failures after that single reload are a real readiness problem and should be triaged as runtime drift or app boot instability.

## Orphan Cleanup

1. Review `healer_reconcile_reaped_orphan_app_runtimes` and `healer_reconcile_cleaned_artifact_roots`.
2. If runtimes are reaped repeatedly, inspect the runtime process owner and whether the issue is still active.
3. If artifact roots are cleaned too aggressively, check the stored retention window and issue state transitions.

Healthy state:

- orphan cleanup counters rise slowly
- active issues retain their runtime and artifact roots
- only inactive or expired resources are removed
