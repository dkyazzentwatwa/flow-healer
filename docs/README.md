# Flow Healer Docs

Flow Healer is a Python CLI tool for autonomous GitHub maintenance. It watches issues, creates isolated worktrees, runs guarded fixes through an AI connector, verifies them with language-aware test gates, and stores durable state in SQLite.

Flow Healer includes an autonomous PR feedback loop that monitors GitHub comments on open PRs and incorporates them as feedback for iterative healing attempts.

## Quick Start

~~~bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export GITHUB_TOKEN=your_token_here
flow-healer doctor
flow-healer start --once
~~~

## Doc Map

- [installation.md](installation.md): local environment setup and config
- [usage.md](usage.md): CLI flows and examples
- [usage.md - Failure Recovery](usage.md#failure-recovery): handling `no_patch` and `verifier_failed` retries
- [architecture.md](architecture.md): control loop and module map
- [operations.md](operations.md): common maintenance tasks and troubleshooting
- [operations.md - Failure Recovery](operations.md#failure-recovery): incident response for failed healing attempts
- [reliability-improvement-feedback.md](reliability-improvement-feedback.md): reliability feedback roadmap and prioritized hardening sequence
- [contributing.md](contributing.md): development and review expectations
- [e2e-smoke/](../e2e-smoke/): Multi-language test sandboxes for validating language strategies

Historical planning, review, and smoke-test artifacts live under [archive/](archive/README.md).

## Failure Recovery

For production runs, use the dedicated recovery sections when a healing attempt ends with `no_patch` or `verifier_failed`:

- [Usage Failure Recovery](usage.md#failure-recovery)
- [Operations Failure Recovery](operations.md#failure-recovery)

~~~bash
flow-healer start --repo demo --once
~~~

## E2E Reliability

- [reliability-retest-plan.md](e2e/reliability-retest-plan.md): retest scope, acceptance criteria, and completion check
- [reliability-risk-review.md](e2e/reliability-risk-review.md): eight-point reliability risk review for artifact completeness
- [reliability-runbook.md](e2e/reliability-runbook.md): operator validation sequence for the artifact pack

## Notes

- Project type: CLI automation service
- Tech stack: Python 3.11+, SQLite, GitHub, Docker, pytest, Node.js, Swift
- Target audience: repository maintainers and contributors
- Review feedback addressed: this initial docs scaffold is intended as a starting point for iterative refinement.
