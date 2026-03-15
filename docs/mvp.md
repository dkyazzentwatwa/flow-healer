# Flow Healer MVP

Flow Healer opens draft PRs for two classes of issues: flaky test repair and safe CI/config/doc fixes. It attaches validation evidence to every PR so you can review and decide in one place.

## What It Does at MVP

1. Watches GitHub issues labeled `healer:ready`
2. Proposes a fix via configured connector (default: `codex`)
3. Runs validation (local test suite and/or Docker)
4. Attaches evidence: files changed, diff summary, validation commands, pass/fail
5. Opens a draft PR with a human-readable summary
6. Operator reviews from TUI (`flow-healer tui`) or CLI (`flow-healer status`)

## Issue Classes Accepted at MVP

### Class A — Flaky Test Repair

Accepted when the issue describes a test that fails intermittently and the proposed fix only changes test files or test helpers.

**Example issue title:** `test_retry_backoff flakes on CI — timing sensitive`

Rejected if the test failure is caused by a production bug. Flow Healer will comment with `needs_clarification`.

### Class B — Safe CI / Config / Doc Fixes

Accepted when the issue targets:
- `.github/` workflow files
- `Makefile`, `pyproject.toml`, `setup.cfg`, `tox.ini`
- `requirements*.txt`
- `*.md` documentation

Rejected if the fix would touch production source files under `src/`.

## What Is Out of Scope at MVP

- Broad refactors
- Fixes to production bugs
- Dependency version bumps that require code changes
- CI restructuring
- Multi-repo fleet management (supported but not the MVP headline)

## How to Know It's Working

Run `flow-healer doctor` after setup. A green result means:

- GitHub token present and valid
- Connector binary found and responds
- Git repo accessible
- State database accessible

Then run `flow-healer start --once` against a repo with a labeled issue. Check `flow-healer status` for the result.

## Rejection States

| State | Meaning | What to do |
|---|---|---|
| `needs_clarification` | Issue body lacks required outputs or validation | Add `Required code outputs:` and `Validation command:` sections to the issue |
| `judgment_required` | Diff too large or scope unclear | Narrow the issue scope |
| `failed` | Fix applied but validation did not pass | See attempt details in TUI → retry or close |
| `blocked` | Circuit breaker open or repo paused | Run `flow-healer doctor` to diagnose |

## Metrics

See [docs/superpowers/specs/2026-03-14-mvp-design.md](superpowers/specs/2026-03-14-mvp-design.md) for target success metrics.
