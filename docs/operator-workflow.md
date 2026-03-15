# Operator Workflow

This document explains the review queue, what each state means, and how to take action from the TUI or CLI.

## The Review Queue

Flow Healer maintains a queue of issues in SQLite. States visible in the TUI:

| State | Meaning |
|---|---|
| `queued` | Issue is waiting to be processed |
| `claimed` / `running` | Fix is in progress |
| `verify_pending` | Fix applied, running validation |
| `pr_open` | Draft PR opened, awaiting your review |
| `failed` | Fix failed validation — see failure reason |
| `blocked` | Repo paused or circuit breaker open |
| `merged` / `closed` | Work complete |

## Opening the TUI

```bash
flow-healer tui
```

The TUI has four tabs:

| Tab | What it shows |
|---|---|
| **Review Queue** | Issues with open draft PRs ready for your review |
| **Blocked** | Issues stuck in `failed` or `blocked` — need attention |
| **Repo Health** | Circuit breaker state, success rate, recent activity |
| **History** | All resolved issues (merged, closed, cancelled) |

## Row Actions

With a row selected in the TUI:

| Key | Action |
|---|---|
| `r` | Retry the issue (re-queue with current context) |
| `p` | Pause the entire repo (stops new work) |
| `o` | Open the draft PR link in your browser |
| `q` | Quit |

## CLI Actions

```bash
# See queue state
flow-healer status

# Pause a repo
flow-healer pause --repo my-repo

# Resume a repo
flow-healer resume --repo my-repo

# Retry a specific issue (re-label it healer:ready on GitHub)
# Flow Healer will pick it up on next poll

# Export queue data for analysis
flow-healer export --formats csv,jsonl
```

## Reviewing a Draft PR

Flow Healer opens PRs in **draft** state. Each PR body includes:

- Summary of intended fix
- Files changed
- Validation commands run and their pass/fail result
- Risk level assessment from the AI reviewer

To approve: convert draft to ready-for-review, then merge normally.
To retry: close the PR and re-label the issue `healer:ready`. Flow Healer will re-attempt with feedback from the PR comments.
To reject: close the PR and close the issue (or remove the label).

## Understanding Failure Reasons

| Failure | Meaning | Action |
|---|---|---|
| `validation_failed` | Tests did not pass after fix | Check test output in PR body; retry or edit issue |
| `diff_too_large` | Too many files or lines changed | Narrow the issue scope |
| `scope_violation` | Fix touched disallowed files | Update issue's Required outputs section |
| `no_confident_fix` | Connector could not produce a fix | Add more context to issue body; retry |
| `repo_blocked` | Circuit breaker open | Run `flow-healer doctor`; check recent failure rate |
| `review_required` | AI reviewer flagged for human attention | Read PR body reviewer section; decide manually |

## Circuit Breaker

Flow Healer tracks failure rate per repo. If > 50% of recent attempts fail, it opens the circuit breaker and stops attempting new work. Run `flow-healer doctor` to see the current state and reset if needed.

## Pausing a Repo

```bash
flow-healer pause --repo my-repo
```

This stops Flow Healer from claiming new issues for that repo. In-progress work completes normally. Resume with `flow-healer resume --repo my-repo`.
