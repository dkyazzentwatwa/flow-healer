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

```bash
git rev-parse --is-inside-work-tree
git rev-parse --show-toplevel
git status --porcelain=v1 --untracked-files=all
git diff-index --quiet HEAD --
git worktree list --porcelain -z
```

Universal default policy:

- hard-fail if the workspace is not a Git work tree
- hard-fail if tracked files are dirty before the proposer runs
- hard-fail on unresolved Git operation state
- warn or fail on unknown untracked files based on strictness mode
- warn on stale worktrees, and fail only when the active workspace is ambiguous or collides with another active run

Universal nuance:

Many operator source clones may already be dirty for unrelated reasons. The safer universal default is to require the proposer workspace itself to be clean while allowing the source clone to remain dirty if automation never writes there.

Repo-local override points:

- ignored untracked paths such as runtime state directories
- whether unknown untracked files are warnings or failures
- whether generated artifact outputs are allowed for `artifact_only` runs
- whether source-clone dirtiness matters when the proposer runs in an isolated worktree

### 2. Branch Safety

The proposer should never edit code from a risky branch context by accident.

Universal checks:

- resolve the current branch name, or detect detached HEAD
- resolve the repository default branch
- compare the active branch against protected names and patterns
- confirm the workspace branch matches the automation naming convention when worktree mode is expected
- confirm the run is not happening in the primary checkout when isolated issue worktrees are required

Recommended command set:

```bash
git branch --show-current
git symbolic-ref --quiet --short HEAD
git rev-parse --abbrev-ref origin/HEAD
git remote show origin
```

Universal default policy:

- hard-fail on detached HEAD
- hard-fail when the active branch equals the repository default branch
- hard-fail on protected patterns such as `main`, `master`, `trunk`, `develop`, `dev`, `release/*`, and `hotfix/*`
- hard-fail when an issue-scoped automation branch is required but missing
- warn when no upstream is configured if the run only needs to propose changes locally

Repo-local override points:

- protected branch patterns
- required branch naming conventions
- whether direct execution in the primary checkout is ever allowed
- whether missing upstream configuration matters before proposal or only before push

### 3. Environment Readiness

Readiness should be keyed to task kind and validation profile so research-only or `artifact_only` runs do not fail on tools they will never invoke.

Baseline checks for every proposal run:

- confirm the proposer connector command resolves in the effective `PATH`
- confirm required environment variables exist and are non-empty
- confirm the workspace is writable
- confirm Git is available
- confirm temporary scratch space is available for patches, logs, or connector artifacts

Conditional checks:

- for `artifact_only`: connector availability, Git availability, workspace writability, and required environment variables
- for test-gated runs: add Python interpreter, active dependency context, and `pytest`
- for containerized validation paths: add Docker only when configured for that run
- for PR or push flows: add Git identity, token presence, remote reachability, and provider-specific auth

Universal default policy:

- hard-fail on missing connector command
- hard-fail on missing required environment variables
- hard-fail on non-writable workspace
- warn, rather than fail, for optional tools that the current run will not invoke

Repo-local override points:

- required environment variables
- validation-tool requirements by profile
- whether Git identity is checked before proposal or only before commit or push
- whether network reachability is required at proposal time

## Recommended Result Contract

Every proposal attempt should generate a small structured preflight report before the connector runs.

Suggested shape:

```python
{
    "ok": False,
    "status": "fail",
    "failure_class": "preflight_branch_unsafe",
    "checks": [
        {
            "name": "branch_safe",
            "status": "fail",
            "summary": "Active branch matches the repository default branch.",
            "details": ["current_branch=main", "default_branch=main"],
            "remediation": "Create or switch to an isolated issue branch before retrying."
        }
    ]
}
```

Recommended semantics:

- `pass`: safe to continue
- `warn`: continue, but persist the warning in logs and operator output
- `fail`: stop before proposal generation and record a stable failure class
- `skip`: check intentionally omitted because the active profile does not require it

Stable failure classes worth standardizing:

- `preflight_repo_missing`
- `preflight_repo_dirty`
- `preflight_git_operation_in_progress`
- `preflight_branch_unsafe`
- `preflight_workspace_unsafe`
- `preflight_env_missing`
- `preflight_tool_missing`

## Best Fit For Flow Healer

### Recommended module split

Create a dedicated preflight module:

- `src/flow_healer/healer_preflight.py`

Suggested responsibilities:

- repository probes
- branch policy evaluation
- environment readiness checks
- profile-aware gating
- report assembly
- remediation messaging

### Recommended integration points

- [`src/flow_healer/healer_runner.py`](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_runner.py): run proposal preflight before the first proposer turn and short-circuit on hard failures
- [`src/flow_healer/healer_loop.py`](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_loop.py): pass task kind and validation profile into preflight and avoid burning proposer retries on deterministic setup failures
- [`src/flow_healer/healer_workspace.py`](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_workspace.py): reuse worktree-root and branch-shape knowledge for workspace safety checks
- [`src/flow_healer/service.py`](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/service.py): reuse the same engine for `doctor` so operator diagnostics match live runtime behavior

## Implementation Plan

### Phase 1: Build the universal preflight engine

**Files**

- Create `src/flow_healer/healer_preflight.py`
- Add tests in `tests/test_healer_runner.py` or a new `tests/test_healer_preflight.py`

**Steps**

1. Define `PreflightCheckResult` and `PreflightReport` dataclasses with stable `status`, `failure_class`, `summary`, `details`, and `remediation` fields.
2. Add narrow probe helpers for Git presence, repo identity, worktree cleanliness, untracked files, Git-operation-in-progress markers, branch state, command resolution, env vars, temp space, and writability.
3. Add a single `run_preflight(...)` entry point that accepts workspace path, task kind, validation profile, connector command, required env vars, and optional policy overrides.
4. Keep the engine side-effect free and make every probe return a structured check result instead of raising until report assembly time.
5. Standardize failure classes so loop, store, and issue comments can reason about preflight failures without parsing prose.

**Definition of done**

- one report object fully describes whether a proposal may run
- every failed or warned check includes remediation text
- `artifact_only` and test-gated profiles produce different required-check sets without branching all over the caller

### Phase 2: Enforce preflight before proposal turns

**Files**

- Modify `src/flow_healer/healer_runner.py`
- Modify `src/flow_healer/healer_loop.py`
- Add tests in `tests/test_healer_runner.py`
- Add tests in `tests/test_healer_loop.py`

**Steps**

1. Run preflight at the start of `HealerRunner.run_attempt(...)` before calling `connector.run_turn(...)`.
2. Return a normal `HealerRunResult` with a preflight failure class when preflight hard-fails, instead of spending a proposer attempt.
3. Thread the preflight report into retry decisions so deterministic setup failures do not trigger connector resets or retry loops.
4. Make the loop record preflight failures distinctly from connector or patch-application failures.
5. Ensure `artifact_only` runs can still succeed when test tooling is absent but connector and workspace readiness are intact.

**Definition of done**

- unsafe repo or branch state blocks proposal generation immediately
- preflight failures do not consume proposer retries
- run results clearly distinguish setup failures from proposer failures

### Phase 3: Align `doctor` and operator diagnostics

**Files**

- Modify `src/flow_healer/service.py`
- Add tests in `tests/test_service.py`

**Steps**

1. Replace the current ad hoc `doctor` probes with the shared preflight engine where practical.
2. Expose both repo-level runtime checks and operator-environment checks in a stable shape that mirrors the runtime report.
3. Keep lightweight summary fields for CLI display, but preserve detailed check output for debugging.
4. Make sure `doctor` can run in report-only mode even when runtime would enforce failures.

**Definition of done**

- `doctor` and runtime disagree only when policy intentionally differs
- operators can see the same remediation text runtime would use

### Phase 4: Add repo-local policy without breaking universality

**Files**

- Modify config-handling modules if needed, most likely `src/flow_healer/config.py`
- Add tests in `tests/test_config.py`

**Steps**

1. Introduce a small preflight policy surface for protected branch patterns, ignored untracked paths, required env vars, and validation-tool requirements.
2. Keep defaults strict enough to be safe without configuration.
3. Make every override optional and additive so repos can tighten or relax behavior without forking the engine.
4. Document which settings are universal defaults versus repo-specific policy choices.

**Definition of done**

- the engine remains portable across repos
- repo-specific exceptions do not leak into universal default logic

## Testing Plan

Add focused tests for the failure modes most likely to waste proposer turns:

- workspace path is not a Git repo
- tracked files are dirty
- unknown untracked files exist
- merge or rebase state is in progress
- detached HEAD
- active branch equals the default branch
- branch name fails required automation pattern
- connector command is missing from `PATH`
- required environment variable is missing
- workspace is not writable
- `artifact_only` skips test-tool requirements
- test-gated runs fail when `pytest` is missing

Recommended commands:

```bash
pytest tests/test_healer_runner.py -v
pytest tests/test_healer_loop.py -v
pytest tests/test_service.py -v
pytest
```

## Rollout Strategy

Roll this out in two modes:

1. report-only mode so operators can see how often runs would fail and which checks are noisy
2. enforced mode once the failure patterns and repo-local overrides are understood

This keeps the universal defaults conservative without surprising live automation on day one.

## Sources

- Git status porcelain: <https://git-scm.com/docs/git-status>
- Git worktree porcelain: <https://git-scm.com/docs/git-worktree>
- Git diff-index: <https://git-scm.com/docs/git-diff-index>
- Git rev-parse: <https://git-scm.com/docs/git-rev-parse>
- Git symbolic-ref: <https://git-scm.com/docs/git-symbolic-ref>
- GitHub branch protection and rulesets: <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches>
- Python `shutil.which()`: <https://docs.python.org/3/library/shutil.html#shutil.which>
- Python `venv`: <https://docs.python.org/3/library/venv.html>
- pytest usage: <https://docs.pytest.org/en/stable/how-to/usage.html>
