# Usage

This guide covers everyday CLI workflows. For issue-body semantics, lane-safe editing, or runtime-state meaning, use the canonical docs it links to rather than treating this file as the source of truth for those behaviors.

## Core Commands

| Command | Purpose |
| --- | --- |
| `flow-healer doctor [--repo NAME]` | Validate environment, git, Docker, and API setup. |
| `flow-healer status [--repo NAME]` | Show issue counts, state, and recent attempts. |
| `flow-healer export [--repo NAME] [--formats csv,jsonl] [--output-dir PATH]` | Write telemetry exports for spreadsheet and structured analysis workflows. |
| `flow-healer tui [--repo NAME] [--once] [--refresh-seconds N]` | Open the interactive terminal operator view, or print a one-shot text snapshot with `--once`. |
| `flow-healer start [--repo NAME] [--once]` | Run the healing loop continuously or for a single pass. |
| `flow-healer pause [--repo NAME]` | Pause autonomous processing for a repo. |
| `flow-healer resume [--repo NAME]` | Resume autonomous processing. |
| `flow-healer scan [--repo NAME] [--dry-run]` | Scan repo for deterministic breakage patterns. |
| `flow-healer recycle-helpers [--repo NAME] [--idle-only]` | Recycle long-lived helper subprocesses without taking the daemon down. |

## Typical Operator Flow

~~~bash
export GITHUB_TOKEN=your_token_here
flow-healer doctor --repo my-project
flow-healer start --repo my-project --once
flow-healer status --repo my-project
flow-healer export --repo my-project
~~~

## Telemetry And TUI

For self-serve analysis, export telemetry instead of relying on a separate browser dashboard:

~~~bash
flow-healer export --repo my-project
flow-healer export --repo my-project --formats csv,jsonl --output-dir /tmp/my-project-telemetry
~~~

Use the built-in terminal UI for lightweight live inspection:

~~~bash
flow-healer tui --repo my-project
flow-healer tui --repo my-project --once
~~~

Live TUI controls:

- `↑` / `↓`: move selection
- `Tab`: switch pane
- `←` / `→`: switch inspector tabs
- `r`: refresh
- `q`: quit

Use [telemetry-exports.md](telemetry-exports.md) for the export contract and [dashboard.md](dashboard.md) for the remaining control-plane/UI boundaries.

## Healing Lifecycle

1. An issue with the required label, `healer:ready` by default, becomes eligible.
2. Flow Healer claims the issue and creates an isolated worktree.
3. The issue body is parsed into a task contract.
4. The connector proposes a fix inside the worktree.
5. Flow Healer runs lane-aware validation and, when needed, evidence checks.
6. If verification passes, Flow Healer opens or updates the PR.
7. If human feedback arrives, Flow Healer re-queues the issue with that context.

For the full decision path, read [healing-state-machine.md](healing-state-machine.md). For the state and retry semantics behind the CLI output, read [runtime-state.md](runtime-state.md).

## Writing Good Issues

Use [issue-contracts.md](issue-contracts.md) as the canonical spec for:

- `Required code outputs`
- `Validation`
- `input-only context`
- `app_target`
- `runtime_profile`
- `artifact_requirements`
- `browser_repro_mode`
- strict mutation scope

Before creating or editing a lane-specific issue, also read the relevant guide under [lane-guides/](lane-guides/README.md).

## Bulk Sandbox Issue Creation

When you want to generate stress issues, use the sandbox-only helper:

~~~bash
scripts/create_sandbox_issues.sh 20 "Sandbox stress task"
~~~

This helper only creates issues whose `Required code outputs` and `Validation` stay inside:

- `e2e-smoke/*`
- `e2e-apps/*`

Optional labels:

~~~bash
EXTRA_LABELS="kind:scan,priority:medium" scripts/create_sandbox_issues.sh 20 "Sandbox stress task"
~~~

Use the issue-family options only when the output and validation lanes match the intended fixture family. The lane guides remain authoritative for what each family can safely mutate.

## Language Strategy Overrides

Per repo, you can pin language behavior or keep auto-detection:

~~~yaml
repos:
  - name: my-project
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

Lane-specific expectations live in [lane-guides/README.md](lane-guides/README.md), not here.

## Failure Recovery

If a healing attempt finishes with `no_patch`, `verifier_failed`, or another blocking failure:

1. Inspect the latest issue and attempt state with `flow-healer status`.
2. Check whether the problem is an issue-contract problem, a baseline validation blocker, or a runtime incident.
3. Re-run one controlled pass only after the blocker is understood.

~~~bash
flow-healer start --repo my-project --once
~~~

Use [operations.md](operations.md) for incident runbooks, [agent-remediation-playbook.md](agent-remediation-playbook.md) for repeated-failure doctrine, and [evidence-contract.md](evidence-contract.md) for browser-artifact blocking rules.

## Runtime Diagnostics

Use the repo-owned runtime helpers before changing launchd config or retrying a noisy queue:

~~~bash
scripts/diagnose_runtime.sh ~/.flow-healer/config.yaml my-project
scripts/verify_runtime.sh ~/.flow-healer/config.yaml my-project
FLOW_HEALER_RESTART=1 scripts/remediate_runtime.sh ~/.flow-healer/config.yaml my-project
~~~
