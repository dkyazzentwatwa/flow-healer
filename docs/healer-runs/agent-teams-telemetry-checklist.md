# Agent-Team Telemetry Checklist

## Purpose
Use this checklist to validate a codex agent-team or native multi-agent run before handing results to operators or incident follow-up.

## Pre-run checks
- Confirm the run has a stable identifier such as issue number, branch, or worktree path.
- Capture the requested scope: target files, validation command, and expected deliverable.
- Record which execution mode is in use: codex agent-team or native multi-agent.

## Telemetry checks
- Start signal present: a run-start event, log line, or status row exists before any worker activity.
- Role activity visible: planner, proposer, verifier, or equivalent roles emit distinct progress events.
- Artifact path recorded: output targets and any generated artifact paths are visible in logs or metadata.
- Validation result attached: the final validation command, exit status, and timestamp are captured.
- Outcome handoff complete: final state is clearly marked as success, retry-needed, or failed with next action.

## Success criteria
- Every required role transition can be traced from start to finish without guessing.
- Operators can identify which artifacts were produced and where they were written.
- Validation evidence is attached to the same run context as the artifacts.
- The final handoff makes the next operator action obvious.

## Escalate when
- Worker activity appears without a matching run-start record.
- Artifact files exist but no telemetry links them to the run.
- Validation output is missing, truncated, or detached from the final status.
- The run ends without a clear owner, terminal state, or retry instruction.
