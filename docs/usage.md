# Usage

## Core Commands

| Command | Purpose |
| --- | --- |
| `flow-healer doctor [--repo NAME]` | Validate environment, git, Docker, and API setup. |
| `flow-healer status [--repo NAME]` | Show current issue counts, state, and recent attempts. |
| `flow-healer start [--repo NAME] [--once]` | Run the healing loop continuously or for a single pass. |
| `flow-healer pause [--repo NAME]` | Pause autonomous processing for a repo. |
| `flow-healer resume [--repo NAME]` | Resume autonomous processing. |
| `flow-healer scan [--repo NAME] [--dry-run]` | Scan repo for breakage patterns and optionally create issues. |
| `flow-healer recycle-helpers [--repo NAME] [--idle-only]` | Ask the live daemon to recycle connector/helper subprocesses on the next tick. |

## The Healing Lifecycle

### 1. Triggering a Fix
Flow Healer monitors issues with the `healer:ready` label (configurable). It only processes issues from trusted actors or those explicitly labeled.

### 2. Autonomous Processing
Once claimed, Flow Healer:
- Creates an isolated git worktree.
- Analyzes the issue and predicts which files need locking.
- Generates a fix via the AI connector.
- Resolves a language strategy (auto-detected or pinned in config).
- Runs tests via local and/or Docker gates per `test_gate_mode`.
- Verifies the fix doesn't introduce regressions.

### 3. Review and Approval
By default, Flow Healer opens or updates the Pull Request as soon as verification passes. If `pr_actions_require_approval` is enabled, it waits for the `healer:pr-approved` label before continuing. When `pr_auto_approve_clean` and `pr_auto_merge_clean` are enabled, Flow Healer also makes a best-effort approval and merge pass for clean PRs with no merge conflicts. GitHub still blocks self-approval from the same actor that opened the PR, and branch protection can still block auto-merge.

### 4. PR Feedback Loop
If a human reviewer leaves a comment on the generated PR, Flow Healer:
1. Detects the new comment.
2. Ingests the comment text as `feedback_context`.
3. Re-queues the issue for a new healing attempt.
4. Applies the feedback to improve the fix in the next iteration.

## Example Workflow

~~~bash
# 1. Setup environment
export GITHUB_TOKEN=your_token_here

# 2. Check health
flow-healer doctor --repo my-project

# 3. Start processing a single issue labeled 'healer:ready'
flow-healer start --repo my-project --once

# 4. Monitor progress
flow-healer status --repo my-project
~~~

## Bulk Sandbox Issue Creation

When you want to generate stress issues (for example: "make 20 GitHub issues"), use the sandbox-only helper:

~~~bash
scripts/create_sandbox_issues.sh 20 "Sandbox stress task"
~~~

This script only creates issues whose `Required code outputs` and `Validation` stay inside:

- `e2e-smoke/*`
- `e2e-apps/*`

Optional labels:

~~~bash
EXTRA_LABELS="kind:scan,priority:medium" scripts/create_sandbox_issues.sh 20 "Sandbox stress task"
~~~

You can also select a dedicated issue family. For SQL-only `prosper-chat` migration or RLS work, use the DB family so generated issues stay under `supabase/**` and prefer the `db` validation lane:

~~~bash
ISSUE_FAMILY=prosper-chat-db scripts/create_sandbox_issues.sh 12 "Prosper chat DB task"
~~~

Those generated issues use:

- `Required code outputs:` under `e2e-apps/prosper-chat/supabase/migrations/` and `e2e-apps/prosper-chat/supabase/assertions/`
- `Validation: cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh db`
- DB-focused labels such as `area:db`, `kind:migration`, and `kind:rls`

For pure `prosper-chat` edge-function work under `supabase/functions/**`, prefer:

~~~bash
Validation:
- cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh backend
~~~

Reserve `full` for issues that intentionally span frontend/app files plus backend files.

For `prosper-chat` Supabase-related validation, the harness now starts local Supabase on demand and auto-stops it on exit only if the harness started it. If the stack was already running before validation began, it is left alone. Set `FLOW_HEALER_AUTO_STOP_SUPABASE=0` to keep the stack running even when the harness started it.

## Scanner Behavior

The scanner identifies deterministic breakage patterns (e.g., failed CI, linting errors). If `scan_enable_issue_creation` is set to `true`, it will create deduplicated GitHub issues for these findings, labeled with `kind:scan` and `healer:ready` to trigger the healing loop automatically.

> **Note**: Labels can be customized per-repo in the configuration to match your project's workflow. Standardizing labels across repos is recommended for consistent multi-repo orchestration.

## Language Strategy Overrides

Per repo, you can pin language behavior or keep auto-detection:

~~~yaml
repos:
  - name: my-project
    # ...
    test_gate_mode: local_then_docker
    local_gate_policy: auto
    language: ""
    docker_image: ""
    test_command: ""
    install_command: ""
~~~

- `language`: pin strategy (`python`, `node`, `swift`, `go`, `rust`, `ruby`, `java_gradle`) or leave empty for auto-detect.
- `local_gate_policy`: `auto`, `force`, or `skip`.
- `docker_image`, `test_command`, `install_command`: optional strategy overrides.

The issue parser and local validation lane now support additional reference ecosystems such as Ruby, Rust, Go, Swift, and Gradle-based Java. Docker-backed execution still only applies to Python and Node.js in this tranche.

### test_gate_mode Options

| Mode | Behavior |
| --- | --- |
| `local_only` | Run tests using local toolchain only |
| `local_then_docker` | Try local first, fall back to Docker (default) |
| `docker_only` | Skip local, use Docker exclusively |

### docker_only Example

When local Python or Node toolchains are unavailable, use `docker_only`:

~~~yaml
repos:
  - name: node-project
    test_gate_mode: docker_only
    local_gate_policy: skip
    language: node
    # Docker image and test command are auto-selected based on language
~~~

Swift, Go, Rust, Ruby, and Gradle-based Java do not support `docker_only`; use `local_only` or `local_then_docker` for those repos.

### Custom Docker Image

Override the default Docker image for any language:

~~~yaml
repos:
  - name: custom-project
    test_gate_mode: docker_only
    language: python
    docker_image: python:3.12-slim
    test_command: pytest -v
    install_command: python -m pip install -q pytest
~~~

## Failure Recovery

If a healing attempt finishes with `no_patch` or `verifier_failed`, stop and recover in this sequence:

1. Verify the issue is still visible and has context for retry.
2. Confirm temporary blockers are fixed (for example: dependency version drift, transient test flakiness, or missing credentials).
3. Trigger one controlled pass so the operator can review retry behavior before allowing normal cadence.

~~~bash
flow-healer start --repo my-project --once
~~~

## Runtime Diagnostics

Use the repo-owned runtime helpers before changing launchd config or retrying a noisy queue:

~~~bash
scripts/diagnose_runtime.sh ~/.flow-healer/config.yaml my-project
scripts/verify_runtime.sh ~/.flow-healer/config.yaml my-project
FLOW_HEALER_RESTART=1 scripts/remediate_runtime.sh ~/.flow-healer/config.yaml my-project
~~~

## Helper Recycling

Use helper recycling when the daemon should stay up but long-lived connector/helper subprocesses need a clean restart.

~~~bash
flow-healer recycle-helpers --repo my-project --idle-only
~~~

`--idle-only` tells the live daemon to defer the recycle while an issue is actively in `claimed`, `running`, or `verify_pending`. The parent service stays up; only helper backends are shut down and restarted lazily on the next use.
