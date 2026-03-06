# Universal Proposal Preflight Research Plan

## Goal

Introduce stronger preflight checks before any proposal run so autonomous code healing fails fast on unsafe repository state, risky branch context, or missing runtime dependencies. The design should be universal across repositories and operators, with repo-local policy layered on top instead of hardcoded into the core engine.

## Current Baseline In This Repo

Flow Healer already has the right seams for a dedicated preflight layer:

- [`src/flow_healer/healer_runner.py`](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_runner.py) runs the proposer, stages edits, applies fallback patches, and decides whether to run tests, but it does not yet gate the run on repository or environment safety before spending a proposer turn.
- [`src/flow_healer/healer_workspace.py`](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_workspace.py) creates isolated issue worktrees and can verify whether a path is under the healer-managed worktree root.
- [`src/flow_healer/healer_loop.py`](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_loop.py) already distinguishes task kind and validation profile, which makes it a natural place to pass preflight requirements into the runner.
- [`src/flow_healer/service.py`](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/service.py) already exposes lightweight `doctor` checks, but those checks are separate from the runtime enforcement path.

The best next step is not a broad redesign. It is a shared preflight engine that both runtime and diagnostics call, with strict universal defaults and small repo-level overrides.

## Research Findings

### 1. Use script-stable Git interfaces, not human-facing output

Git documents `status --porcelain` as a stable, machine-readable format for scripts, `worktree list --porcelain` as the scripted worktree inventory interface, and `diff-index --quiet` as an exit-code cleanliness probe. `rev-parse` and `symbolic-ref --quiet HEAD` are also safer than parsing formatted shell output when resolving repository identity and branch state.

Why it matters:

- preflight failures need stable failure classes
- the same checks should behave consistently across macOS, Linux, CI, and operator shells
- worktree-aware runs should not depend on brittle text parsing

### 2. Branch safety should default to conservative behavior

GitHub's protected-branch and ruleset guidance shows that important branches commonly require pull requests, reviews, status checks, or merge queues. A universal proposer should therefore assume that detached HEAD, the repository default branch, and common protected branch families are unsafe by default unless policy explicitly allows them.

Why it matters:

- the proposer edits code directly in the workspace
- a single unsafe run on `main` or a release branch can create outsized operator risk
- universal defaults should prevent silent policy violations even in repos that have not configured custom rules yet

### 3. Environment readiness should be profile-aware

Python's standard library documents `shutil.which()` as the executable lookup API, `venv` as the standard isolated-environment mechanism, and pytest's usage docs still center the `pytest` CLI as the normal validation entrypoint. That supports a layered readiness model: require only the tools and credentials the current run will actually use, but verify them before the proposer consumes a turn.

Why it matters:

- `artifact_only` research or docs runs should not fail on missing test tools they will never invoke
- test-gated runs should fail early if `python`, `pytest`, or container tooling is missing
- operator diagnostics and live enforcement should share the same readiness rules

## Universal Design Principles

- Fail before proposal generation when the workspace is unsafe.
- Prefer stable Git plumbing, porcelain output, and explicit exit codes.
- Separate universal checks from repo-local policy knobs.
- Return `pass`, `warn`, `fail`, or `skip` for every check.
- Include remediation text for every non-passing check.
- Keep preflight side-effect free.
- Reuse the same preflight engine from runtime and `doctor`.
- Gate checks by task kind and validation profile.

## Recommended Check Families

### 1. Repository Cleanliness

Run cleanliness checks against the exact workspace path that will be handed to the proposer, not only the source clone.

Universal checks:

- confirm the target path is inside a Git work tree
- resolve the repository top level and canonical working path
- detect tracked changes in the index or work tree
- detect untracked files that may leak into proposal output
- detect unresolved merge, rebase, cherry-pick, revert, or bisect state
- detect stale or conflicting linked worktrees when healer-managed worktrees are expected

Recommended command set:
