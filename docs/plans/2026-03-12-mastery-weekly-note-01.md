# Mastery Weekly Note 01

Date: `2026-03-12`

This is the first recorded weekly mastery note for the horizontal-hardening window. It fixes the issue pack, captures the exact commands used, and records the first post-Phase-2 / Phase-3 scorecard deltas.

## Fixed Issue Pack

These issue bodies are now frozen for weekly determinism checks until the mastery window is deliberately reset:

- `#926` `Phase 2 eval: Node smoke add contract`
- `#927` `Phase 2 eval: Node Next auth session normalization`
- `#928` `Phase 2 eval: Ruby Rails dashboard flow`
- `#929` `Phase 2 eval: Java Spring login flow`
- `#930` `Phase 2 eval: Python smoke math contract`
- `#931` `Phase 2 eval: Node Next todo service contract`

Execution lanes covered by the fixed pack:

- mixed-root code lanes: `e2e-smoke/node`, `e2e-smoke/python`
- app-backed lanes: `node-next-web`, `ruby-rails-web`, `java-spring-web`

## Commands Used

The exact commands used for this baseline note were:

```bash
pytest tests/test_healer_task_spec.py tests/test_healer_loop.py tests/test_healer_runner.py tests/test_issue_generation.py -q
pytest tests/test_browser_harness.py tests/test_healer_preflight.py tests/test_reliability_canary.py -q
pytest tests/test_healer_task_spec.py tests/test_healer_loop.py tests/test_healer_runner.py tests/test_issue_generation.py tests/test_browser_harness.py tests/test_healer_preflight.py tests/test_reliability_canary.py -q
pytest tests/test_service.py -k 'staleness_from_recent_activity or harness_health' -q
python -m flow_healer.cli --config /Users/cypher-server/.flow-healer/config.yaml status --repo flow-healer-self
python -m flow_healer.cli --config /Users/cypher-server/.flow-healer/config.yaml doctor --repo flow-healer-self --preflight
gh issue view 926 --json number,title,body,labels
gh issue view 927 --json number,title,body,labels
gh issue view 928 --json number,title,body,labels
gh issue view 929 --json number,title,body,labels
gh issue view 930 --json number,title,body,labels
gh issue view 931 --json number,title,body,labels
```

Snapshot artifacts captured during this note:

- `/tmp/flow-healer-phase3-status.json`
- `/tmp/flow-healer-phase3-doctor.json`
- `/tmp/flow-healer-phase3-doctor-2.json`
- `/tmp/flow-healer-final-live.json`
- `/tmp/flow-healer-preflight-after-runtimes-1.json`
- `/tmp/flow-healer-preflight-after-runtimes-2.json`

## Scorecard Delta

Compared against the Phase 1 baseline snapshot:

| Metric | Phase 1 Baseline | Current | Delta |
| --- | --- | --- | --- |
| `first_pass_success_rate` | `0.2727` | `0.5185` | `+0.2458` |
| `wrong_root_execution_rate` | `0.0` | `0.0` | `0.0` |
| `no_op_rate` | `0.4828` | `0.0` | `-0.4828` |
| `retries_per_success` | `0.4` | `0.0667` | `-0.3333` |
| `mean_time_to_valid_pr_minutes` | `2.31` | `3.24` | `+0.93` |

## Harness And Canary Readout

Current runtime-profile status from `/tmp/flow-healer-final-live.json`:

- `node-next-web`: healthy, `last_canary_at=2026-03-12 08:03:50`
- `ruby-rails-web`: healthy, `last_canary_at=2026-03-12 08:04:04`
- `java-spring-web`: healthy, `last_canary_at=2026-03-12 08:10:06`

Current browser-evidence/harness notes:

- `artifact_publish.failures = 2`
- `browser_failure_families = {"runtime_readiness": 1}`
- stale runtime profiles are now `[]`

## Preflight Readout

After installing the missing native runtimes and forcing two consecutive preflight refreshes, the cached summary is:

- `35` ready roots
- `0` blocked roots
- `35` `stably_ready_roots`, including:
  - `e2e-smoke/python`
  - `e2e-smoke/node`
  - `e2e-smoke/swift`
  - `e2e-smoke/go`
  - `e2e-smoke/rust`
  - `e2e-smoke/java-gradle`
  - `e2e-smoke/ruby`
  - `e2e-apps/node-next`
  - `e2e-apps/ruby-rails-web`
  - `e2e-apps/java-spring-web`

## Current Drift Notes

- No wrong-root drift is visible in the current rolling sample; `wrong_root_execution_rate` remains `0.0`.
- The CI-status reconciliation bug was real and is now repaired:
  - PR `#932` merged at `2026-03-12T08:03:43Z` after the tracker stopped counting superseded cancelled runs as active failures.
- The missing runtime/toolchain gap from earlier in the night is closed on this host:
  - `go`, `rust`, and `openjdk` are installed locally
  - the Java reference app now passes `./gradlew test`
  - the Java reference app smoke flow passes in `tests/test_e2e_apps_sandboxes.py`
- Historical artifact publish failures are still present in the rolling window, so browser-evidence mastery is not yet “green” even though the completeness checks and failure taxonomy are now implemented.

## Verification Wave (Balanced 6)

Date: `2026-03-12`

Restart + gate commands executed:

```bash
launchctl kickstart -k gui/$(id -u)/local.flow-healer
flow-healer resume --repo flow-healer-self
flow-healer recycle-helpers --repo flow-healer-self --idle-only
flow-healer status --repo flow-healer-self > /tmp/verify-wave-baseline.json
flow-healer status --repo flow-healer-self > /tmp/verify-wave-final.json
```

Verification issues created (`campaign:verify-2026-03-12`):

- `#941` Node Next screenshot evidence completeness
- `#942` Ruby Rails screenshot evidence completeness
- `#943` Java Spring screenshot evidence completeness
- `#944` Go determinism (`AddMany`)
- `#945` Rust determinism (`add_many`)
- `#946` Java Gradle determinism (`add3`)

Terminal outcomes:

- `#944` resolved (PR `#947` merged; CI green)
- `#946` resolved (PR `#949` merged; CI green)
- `#941` failed (`browser_step_failed`)
- `#942` failed (`browser_step_failed`)
- `#943` failed (`browser_step_failed`)
- `#945` failed (`ci_failed`, PR `#948` left open/unstable)

Browser evidence checks (`#941/#942/#943`, latest attempts):

- `failure_screenshot` present
- `resolution_screenshot` present
- artifact paths were non-empty on disk at verification time
- no `missing_screenshot` failure classification observed

Code-lane checks:

- expected execution roots confirmed from latest attempts:
  - `#944` -> `e2e-smoke/go`
  - `#945` -> `e2e-smoke/rust`
  - `#946` -> `e2e-smoke/java-gradle`
- no wrong-root or no-op failure family observed in this wave

Drift/remediation follow-ups opened:

- `#950` app-backed resolution text determinism for screenshot TCs
- `#951` rust lockfile/scope drift on retry lane

## Next Review Questions

- Does the fixed issue pack produce the same execution root and validation command choices on the next weekly replay?
- Do browser-evidence failure counts decay as the rolling window fills with post-hardening attempts?
