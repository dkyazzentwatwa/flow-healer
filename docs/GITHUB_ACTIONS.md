# Essential GitHub Actions for Flow Healer

This document describes the 5 essential GitHub Actions workflows that power Flow Healer's CI/CD pipeline and automation.

## 1. CI (Continuous Integration)

**Workflow:** `.github/workflows/ci.yml`

**Purpose:** Runs the primary test suite and validation checks on every pull request and push to main.

**Key Features:**
- Tests across multiple Python versions (3.11, 3.12, 3.13)
- Runs full pytest suite
- Tests Node.js e2e applications (`node-next`, `prosper-chat`)
- Builds distribution packages to verify packaging integrity
- Runs reliability canary benchmarks to detect performance regressions
- Caches dependencies for faster runs

**When it triggers:**
- On pull requests (excluding documentation-only changes)
- On pushes to main
- Manual trigger via `workflow_dispatch`

**Status:** Must pass before merging to main.

---

## 2. Triage (Issue Automation)

**Workflow:** `.github/workflows/01-triage.yml`

**Purpose:** Automatically ensures GitHub labels exist and triages ready issues for the healer service.

**Key Features:**
- Runs on a scheduled 30-minute interval
- Ensures all required agent labels exist in the repo
- Evaluates issues and applies triage labels
- Prepares issues for autonomous healing workflow

**When it triggers:**
- Every 30 minutes (scheduled)
- Manual trigger via `workflow_dispatch`

**Status:** Enables the automated healing pipeline.

---

## 3. Lint Issue Contract

**Workflow:** `.github/workflows/02-lint-issue-contract.yml`

**Purpose:** Validates that issues marked as `healer:ready` conform to the required contract structure (title/body format).

**Key Features:**
- Triggers on issue open, edit, reopen, or label change
- Checks strict contract compliance when `healer:ready` label is present
- Posts remediation comments with validation errors
- Clears comments when issues leave the ready queue or become valid
- Uploads lint artifacts for debugging

**When it triggers:**
- When an issue is opened, edited, reopened, or labeled
- Manual trigger via `workflow_dispatch`

**Status:** Ensures issues are properly formatted before the healer begins work.

---

## 4. Verify PR (Manual Validation)

**Workflow:** `.github/workflows/03-verify-pr.yml`

**Purpose:** Provides comprehensive manual PR verification with phased validation gates.

**Key Features:**
- Full test suite execution
- Reliability canary benchmark pack with policy enforcement
- Phased validation summary (validation lane, fast pass, full pass, promotion state)
- Generates detailed validation artifacts
- Can be manually triggered to gate promotions and merges

**When it triggers:**
- Manual trigger via `workflow_dispatch`

**Status:** Acts as a secondary quality gate before sensitive merges.

---

## 5. Release (Publishing & Distribution)

**Workflow:** `.github/workflows/09-release.yml`

**Purpose:** Builds and publishes official releases when version tags are pushed.

**Key Features:**
- Builds Python distribution packages (sdist + wheel)
- Extracts version from `pyproject.toml`
- Verifies wheel installation in clean virtualenv
- Tests CLI entrypoint
- Creates GitHub releases with auto-generated release notes
- Uploads distribution artifacts to release

**When it triggers:**
- On git tags matching `v*` (e.g., `v1.0.0`)
- Manual trigger via `workflow_dispatch`

**Status:** Publishes official releases for users to install.

---

## Additional Workflows

While not in the top 5, these workflows provide important functionality:

- **CodeQL (07-codeql.yml):** Security scanning for code vulnerabilities
- **Workflow Lint (05-workflow-lint.yml):** Validates workflow YAML syntax
- **Dependency Review (06-dependency-review.yml):** Checks for vulnerable dependencies
- **Merge/Close (04-merge-close.yml):** Automated PR merge and issue close logic
- **Docs Guard (10-docs-guard.yml):** Ensures documentation stays current
- **Nightly E2E (08-nightly-e2e.yml):** Extended end-to-end testing on schedule

## Running Workflows Locally

To test workflow behavior locally before pushing:

```bash
# Install act (GitHub Actions runner simulator)
brew install act

# Run a specific workflow
act -j test

# Run with specific event
act pull_request -j test
```

## Debugging Workflow Issues

1. Check the **Actions** tab in GitHub for detailed logs
2. Look at **Artifacts** section for uploaded reports (e.g., `reliability-canary-report.json`)
3. For local debugging, use `act` to simulate the workflow runner
4. Review workflow syntax with `yamllint .github/workflows/`
