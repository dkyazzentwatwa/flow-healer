# Queue Scaling Playbook

## Purpose
This playbook defines how to scale Flow Healer queue capacity during load spikes and recovery windows while minimizing retry debt and worker churn.

## Scope
- High scan volume from new repo onboarding
- Burst event patterns from backlogged connector failures
- Temporary GitHub API or webhook lag causing queue buildup

## Scaling signals
Use these indicators before changing capacity:

| Signal | Healthy threshold | Action |
| --- | --- | --- |
| Queue depth (pending) | `< 200` items | No change |
| Queue depth (pending) | `200-800` items | Increase workers by 1 |
| Queue depth (pending) | `> 800` items | Add a secondary worker batch |
| Avg retry age | `< 30m` | Normal operation |
| Avg retry age | `30-90m` | Pause low-priority scans |
| Avg retry age | `> 90m` | Enable incident drill immediately |

## Step-by-step scaling sequence
1. Freeze noncritical feature branches from being tracked during the incident.
2. Verify the tracker database is writable and lock state has not fragmented.
3. Increase active worker count in small steps (not above 2x the baseline).
4. Recheck queue depth every 10 minutes for three intervals.
5. If depth does not trend down, run an `incident drill` from the checklist.
6. If retries still age up, apply failure taxonomy fixes before adding more scale.

## Roll-forward play
| Stage | Capacity change | Expected effect | Exit condition |
| --- | --- | --- | --- |
| Stage 1 | +1 worker | Drain small backlog | Pending drops under 500 |
| Stage 2 | +2 workers | Aggressive catch-up | Avg retry age < 60m |
| Stage 3 | +4 workers + retry cap | Clear backlog spikes | Oldest retry < 45m |

## Rollback guardrails
- Keep scaling changes logged with a timestamp and operator note.
- If error-rate increases for three checks in a row, revert one increment immediately.
- Do not exceed memory/CPU utilization guard values in deployment config.

## Incident coordination
- Use this playbook with the [Incident Drill Checklist](incident-drill-checklist.md).
- Pair any rollback with the [Retry Failure Taxonomy](retry-failure-taxonomy.md) to avoid repeating the same root cause.
- Keep notes in one location per run for post-incident review.

## How this helps Flow Healer
This playbook turns queue pressure into a repeatable operation: scaling is incremental, reversible, and tied to concrete thresholds. It keeps backlog handling safe under pressure while reducing random, high-risk operator actions.
