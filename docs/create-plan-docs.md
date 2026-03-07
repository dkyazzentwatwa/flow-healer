# Universal Proposal Preflight Plan

## Goal

Introduce a stronger preflight layer that runs before any proposal attempt so autonomous code healing fails fast on unsafe repository state, risky branch context, or missing runtime dependencies. The plan should be portable across repositories and operator setups, with repo-specific policy layered on top instead of baked into the core checks.

## Research Findings

The safest universal design is to build preflight checks around machine-readable Git commands and explicit exit codes instead of parsing human-oriented terminal output. Git documents `status --porcelain` as stable for scripts, `diff-index --quiet` as an exit-code-based cleanliness check, `rev-parse` as the source of repository identity and branch resolution, and `worktree list --porcelain` as the worktree inventory interface. That combination is a solid base for deterministic repository and branch safety gates.

Branch safety should default to conservative behavior. GitHub's branch protection model makes it normal for important branches to require pull requests, reviews, status checks, or merge queues. A proposal runner should therefore assume that operating directly on the default branch, a release branch, or a detached HEAD is unsafe unless policy explicitly allows it.

Environment readiness should be task-aware instead of one-size-fits-all. Python packaging guidance still treats isolated virtual environments as the standard default, and pytest's CLI remains the baseline validation interface for Python projects. That suggests a layered readiness model: only require the tools and credentials the current run actually needs, but verify them before the proposer consumes a turn.

## Universal Design Principles

- Fail before proposal generation when the workspace is unsafe.
- Prefer machine-readable Git interfaces and exit codes.
- Separate universal checks from repo-local policy knobs.
- Distinguish `fail`, `warn`, `pass`, and `skip` so operators can tune strictness without losing observability.
- Return actionable remediation text for every non-passing check.
- Keep the same preflight engine reusable from both live runs and operator-facing diagnostics.

## Recommended Check Families

### 1. Repository Cleanliness

Run cleanliness checks against the exact workspace path that will be handed to the proposer.

Universal checks:

- Confirm the path is inside a Git working tree.
- Resolve the repository root so downstream checks run against the intended repo.
- Detect tracked changes in the index or work tree.
- Detect untracked files that may leak into proposal output.
- Detect unfinished merge, rebase, cherry-pick, revert, or bisect state.
- Detect worktree collisions or stale healer-managed worktrees when worktree mode is expected.

Recommended command set:

```bash
git rev-parse --is-inside-work-tree
git rev-parse --show-toplevel
git status --porcelain=v1 --untracked-files=all
git diff-index --quiet HEAD --
git worktree list --porcelain
```

Universal default policy:

- Hard-fail if the workspace is not a Git work tree.
- Hard-fail if tracked files are dirty.
- Hard-fail on unresolved Git operation state.
- Warn or fail on untracked files based on strictness mode.
- Warn on stale worktrees; fail only when the active workspace is ambiguous or conflicting.

Repo-local override points:

- Ignored untracked paths such as runtime state directories.
- Whether unknown untracked files are warnings or failures.
- Whether certain generated files are tolerated for artifact-only runs.

### 2. Branch Safety

The proposer should never mutate code from a risky branch context by accident.

Universal checks:

- Resolve the current branch name, or detect detached HEAD.
- Resolve the repo's default branch.
- Compare the active branch against protected names and patterns.
- Confirm the workspace branch matches the automation naming convention when worktree mode is expected.
- Confirm the run is not happening in the source repository when an isolated issue worktree is required.

Recommended command set:

```bash
git branch --show-current
git symbolic-ref --quiet HEAD
git remote show origin
git rev-parse --abbrev-ref origin/HEAD
```

Universal default policy:

- Hard-fail on detached HEAD.
- Hard-fail when the active branch equals the default branch.
- Hard-fail on protected patterns such as `main`, `master`, `trunk`, `develop`, `dev`, `release/*`, and `hotfix/*`.
- Hard-fail when an issue-scoped automation branch is expected but missing.
- Treat missing upstream configuration as a warning before commit time, not before proposal time.

Repo-local override points:

- Protected branch patterns.
- Required branch naming scheme.
- Whether direct execution in the primary clone is ever allowed.

### 3. Environment Readiness

Readiness should be gated by task kind and validation profile so research-only runs do not fail on tools they will never invoke.

Baseline checks for every proposal run:

- Confirm the proposer connector command resolves in the effective `PATH`.
- Confirm required environment variables exist and are non-empty.
- Confirm the workspace is writable.
- Confirm temporary space is available for patches, transcripts, or connector scratch files.
- Confirm Git is available.

Conditional checks:

- For `artifact_only`: connector, writable workspace, Git, and required environment variables.
- For test-gated runs: add Python interpreter, virtual environment or equivalent dependency context, and `pytest`.
- For containerized validation paths: add Docker only when configured for the run.
- For PR or push flows: add Git identity, token presence, and remote reachability.

Universal default policy:

- Hard-fail on missing connector command.
- Hard-fail on missing required environment variables.
- Hard-fail on non-writable workspace.
- Warn, rather than fail, for optional tools that the current run will not use.

Repo-local override points:

- Required environment variables.
- Validation-tool requirements by profile.
- Whether Git identity is checked before proposal or only before commit/push.

## Proposed Preflight Contract

Add a small structured report that every proposal run produces before invoking the connector.

Suggested shape:

```python
{
    "ok": False,
    "status": "fail",
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

Expected behavior:

- `pass`: safe to continue.
- `warn`: continue, but persist the warning in operator-visible output.
- `fail`: stop before proposal generation and record a stable failure class.
- `skip`: check intentionally omitted because the task profile does not require it.

## Recommended Integration Shape

### New Module

Create a dedicated preflight module so the policy can be reused from runtime and diagnostics:

- `src/flow_healer/healer_preflight.py`

Responsibilities:

- repository probes
- branch policy evaluation
- environment readiness checks
- report assembly
- remediation messaging

### Runtime Integration

Recommended touchpoints:

- [`src/flow_healer/healer_runner.py`](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_runner.py): run proposal preflight before the first proposer turn and short-circuit on hard failures.
- [`src/flow_healer/healer_workspace.py`](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_workspace.py): reuse or extend repo/worktree safety helpers.
- [`src/flow_healer/healer_loop.py`](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_loop.py): surface preflight failures in attempt status and retry logic.
- [`src/flow_healer/service.py`](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/service.py): expose the same engine through `doctor` or a comparable operator command.

## Implementation Plan

### Phase 1: Universal Engine

Files:

- Create `src/flow_healer/healer_preflight.py`
- Modify `src/flow_healer/healer_runner.py`
- Add tests in `tests/test_healer_runner.py`

Steps:

1. Define `PreflightCheckResult` and `PreflightReport` dataclasses.
2. Implement Git probes for repo identity, cleanliness, branch detection, and worktree inventory.
3. Implement environment probes for command resolution, env-var presence, and writability.
4. Add a `run_preflight(...)` entry point keyed by task kind and validation profile.
5. Return stable failure classes such as `preflight_repo_dirty`, `preflight_branch_unsafe`, and `preflight_env_missing`.

### Phase 2: Enforce Before Proposal

Files:

- Modify `src/flow_healer/healer_runner.py`
- Modify `src/flow_healer/healer_loop.py`
- Add tests in `tests/test_healer_loop.py`

Steps:

1. Run preflight before the first proposer turn.
2. Refuse to consume proposer retries on hard-fail preflight results.
3. Persist warnings and failures in attempt metadata.
4. Emit short, operator-readable summaries for issue comments or logs.

### Phase 3: Align Operator Diagnostics

Files:

- Modify `src/flow_healer/service.py`
- Modify `src/flow_healer/cli.py`
- Add tests in `tests/test_service.py`

Steps:

1. Reuse the same preflight engine from `doctor` or an equivalent command.
2. Show the same failure classes and remediation text that runtime would use.
3. Make the output easy to scan by grouping results into cleanliness, branch safety, and environment readiness.

### Phase 4: Add Safe Configuration

Files:

- Modify `src/flow_healer/config.py`
- Modify `config.example.yaml`
- Add tests in `tests/test_config.py`

Steps:

1. Add config for protected branch patterns, ignored untracked paths, required env vars, and strictness level.
2. Keep conservative defaults so the feature is safe without customization.
3. Document clearly which overrides reduce safety.

## Testing Plan

Add or update coverage for:

- clean workspace passes
- dirty tracked file fails
- unresolved rebase or merge state fails
- unknown untracked file behavior changes by strictness mode
- detached HEAD fails
- default branch execution fails
- expected automation branch passes
- missing connector command fails
- missing required env var fails
- optional unused tool warns instead of failing
- `doctor` and runtime preflight report the same outcome for the same repo state

## Rollout Guidance

- Start with report-only mode if operators want visibility before enforcement.
- Promote repository cleanliness and branch safety to hard-fail first.
- Keep environment checks profile-aware so artifact-only runs do not become noisy or brittle.
- Capture recurring preflight failures as healer lessons so future operators see the remediation quickly.

## References

- Git `status --porcelain` and script-oriented status output: https://git-scm.com/docs/git-status
- Git `diff-index --quiet` for exit-code-based change detection: https://git-scm.com/docs/git-diff-index
- Git `rev-parse` for repo and ref resolution: https://git-scm.com/docs/git-rev-parse
- Git `worktree list --porcelain` for machine-readable worktree inventory: https://git-scm.com/docs/git-worktree
- GitHub branch protection guidance: https://docs.github.com/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- Python packaging guidance on virtual environments: https://packaging.python.org/en/latest/tutorials/installing-packages/#creating-virtual-environments
- pytest installation and invocation docs: https://docs.pytest.org/en/stable/getting-started.html
