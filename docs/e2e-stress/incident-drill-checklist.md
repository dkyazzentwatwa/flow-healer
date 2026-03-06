# Incident Drill Checklist

## Purpose
Run this checklist when queue backlog, repeated failures, or stale retries indicate a control-plane or execution failure.

## Drill trigger
- Queue depth over 800 for 20 minutes or more.
- Retry attempts cycling without progress.
- Multiple connectors entering degraded state at once.

## Pre-drill checklist
| Item | Owner | Status |
| --- | --- | --- |
| Confirm current runbook selected | On-call | ☐ |
| Snapshot queue metrics | On-call | ☐ |
| Notify incident channel | Operations | ☐ |
| Identify top failing repo(s) | SRE | ☐ |
| Capture logs for 15 minutes | SRE | ☐ |

## Execution checklist
- Step 1: Validate one repo can still complete a full healing cycle.
- Step 2: Apply rollback-safe scaling per [Queue Scaling Playbook](queue-scaling-playbook.md).
- Step 3: Classify failures in the taxonomy before requeueing.
- Step 4: If needed, isolate noisy repositories by temporarily pausing tracking.
- Step 5: Rerun only a narrow scope until successful signal returns.

## Failure-type quick table
| Failure class | Immediate action | Recheck condition |
| --- | --- | --- |
| Scanner timeout | Lower concurrency, rerun targeted scan | Same repo succeeds twice in row |
| Auth/credential error | Stop writes, rotate credentials, validate token scope | Token scope matches minimal required set |
| DB lock contention | Reduce writer parallelism | Lock wait duration stabilizes |
| Flaky connector | Disable connector retry loop | Connector returns stable responses |

## Post-drill wrap-up
- Record root cause and the action taken per repository.
- Confirm backlog slope normalized for at least one full observation window.
- Publish a short retrospective note with next-run checks.

## How this helps Flow Healer
This checklist narrows incidents into safe, ordered steps and captures evidence while actions are being taken. It reduces randomness during stress events and improves repeatability across operators.

## Cross-links
- Queue control guidance: [Queue Scaling Playbook](queue-scaling-playbook.md)
- Failure classification: [Retry Failure Taxonomy](retry-failure-taxonomy.md)
