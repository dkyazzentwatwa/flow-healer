# Workflows

This doc defines the active GitHub Actions workflows in Flow Healer and the guardrails every workflow file must follow.

## Active Workflow Set

- `01-triage.yml`: scheduled issue triage and label maintenance
- `02-lint-issue-contract.yml`: validates healer-ready issue bodies
- `03-verify-pr.yml`: PR verification flow
- `04-merge-close.yml`: controlled merge-and-close helper
- `05-workflow-lint.yml`: workflow linting, ShellCheck, and policy validation
- `06-dependency-review.yml`: dependency review on package-manifest changes
- `07-codeql.yml`: CodeQL analysis for Python and JavaScript/TypeScript
- `08-nightly-e2e.yml`: nightly smoke and reliability checks
- `09-release.yml`: tagged release packaging and publishing
- `10-docs-guard.yml`: verifies docs coverage for protected surfaces
- `ci.yml`: main test, packaging, dashboard, and canary validation

## Required Guardrails

Every file under `.github/workflows/` must declare:

- top-level `permissions`
- top-level `concurrency`
- `timeout-minutes` on every job

These rules are enforced by `05-workflow-lint.yml`. New or edited workflows should be checked against the existing files before merging.

## Change Expectations

When workflow behavior changes:

- update this doc in the same change
- keep the workflow purpose summary aligned with the current file set
- preserve the existing guardrails unless the policy itself is being intentionally changed

Workflow edits also trigger `10-docs-guard.yml`, so changes under `.github/workflows/` should always include the matching documentation update here.
