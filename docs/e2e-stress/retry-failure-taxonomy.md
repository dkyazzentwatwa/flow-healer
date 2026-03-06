# Retry Failure Taxonomy

## Purpose
Classify retry failures quickly so automation can adjust behavior instead of repeatedly reprocessing the same broken states.

## Root-cause mapping
| Class | Typical symptom | Recommended handling | Escalation |
| --- | --- | --- | --- |
| Transient transport | Timeout, 5xx bursts, intermittent DNS failures | Exponential backoff + jitter, then retry cap | Retry windows persist beyond 90m |
| Permanent config | Missing fields, schema mismatch, bad path | Stop auto-retry and create issue | Manual fix required |
| Permission / auth | 401/403, token revoked, scope mismatch | Pause target integration and refresh credentials | Same credential errors across repos |
| External limit | API rate limit, throttle headers | Hold retries, widen interval, then resume | Rate limit remains after 2 windows |
| Data race / lock | SQLite lock contention, transaction retries | Reduce write concurrency | Locking persists during single writer tests |

## Decision matrix
| Symptom count in 15m window | Queue pressure | Recommended action |
| --- | --- | --- |
| 1-5 | Low | Continue normal retry cadence |
| 6-15 | Moderate | Temporarily isolate affected repos |
| >15 | High | Trigger incident drill and stop broad retries |

## Operating patterns
1. Group failures by class before adjusting global settings.
2. Prefer targeted remediation over global queue flush.
3. Tag retries with class and timestamp for postmortem visibility.
4. Compare class spread every 15 minutes during incidents.

## Guardrails
- Never auto-raise retry caps for permanent config failures.
- Do not clear retry history as a first response; that destroys diagnostic signal.
- Keep a short annotation in the work log for each class transition.

## How this helps Flow Healer
This taxonomy keeps retries strategic: transient failures recover automatically, while persistent failures are funneled into operational review. It protects the system from wasting cycles on non-recoverable issues.

## Cross-links
- Apply this taxonomy during an [Incident Drill](incident-drill-checklist.md).
- Combine class handling with scaling changes from the [Queue Scaling Playbook](queue-scaling-playbook.md).
