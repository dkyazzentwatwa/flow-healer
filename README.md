<div align="center">

# Flow Healer

![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Control Plane](https://img.shields.io/badge/interface-CLI%20%2B%20Web-111111?style=for-the-badge&logo=gnubash&logoColor=white)
![SQLite](https://img.shields.io/badge/state-SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Pytest](https://img.shields.io/badge/tests-pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)
![GitHub](https://img.shields.io/badge/automation-GitHub-181717?style=for-the-badge&logo=github&logoColor=white)

**An autonomous GitHub repo healer that scans for breakage, picks safe work in isolated worktrees, runs guarded fixes through Codex, and only opens a PR when the result survives verification.**

</div>

## Why Flow Healer

Most automation stops at issue detection. Flow Healer keeps going.

It watches labeled GitHub issues, creates per-issue workspaces, feeds the task to an AI connector, runs Docker-backed test gates, learns from past attempts, and keeps enough local state to recover cleanly across retries. The result is a practical control loop for repository maintenance, not just a bot that files tickets.

## What It Does

- Monitors one or many repositories from a single config file.
- Stores durable per-repo state in SQLite under `~/.flow-healer/`.
- Provides a phone-friendly web dashboard (`flow-healer serve`) for status and control.
- Supports Apple Mail + Calendar command polling with strict subject DSL.
- Creates isolated git worktrees so each fix attempt stays contained.
- Claims and locks work to reduce conflicting edits across issues.
- Applies retry budgets, backoff, and circuit-breaker logic before reattempting work.
- Runs deterministic scan passes with optional GitHub issue creation.
- Verifies candidate changes before opening a pull request.
- Captures lessons from previous attempts to improve future prompts.

## Architecture

```text
GitHub Issues / Repo Signals
            |
            v
   Flow Healer CLI + Service
            |
   +--------+--------+------------------+
   |        |        |                  |
   v        v        v                  v
 Scanner  Tracker  Workspace Mgr   SQLite Store
   |        |        |                  |
   +--------+--------+------------------+
            |
            v
      Autonomous Loop
            |
   Codex Connector -> Docker Test Gate -> Verifier -> PR
```

## Core Modules

```text
src/flow_healer/
├── cli.py                # command entrypoint
├── service.py            # multi-repo orchestration
├── healer_loop.py        # issue processing control loop
├── healer_scan.py        # deterministic repo scanning
├── healer_tracker.py     # GitHub issue + PR adapter
├── healer_workspace.py   # isolated git worktrees
├── healer_memory.py      # lessons from prior attempts
├── healer_dispatcher.py  # claims and lock acquisition
├── healer_verifier.py    # post-fix verification
└── store.py              # SQLite persistence
```

## Supported Languages

Flow Healer supports 3 core languages:

| Language | Docker Image | Test Command |
| --- | --- | --- |
| Python | `python:3.11-slim` | `pytest -q` |
| Node.js | `node:20-slim` | `npm test -- --passWithNoTests` |
| Swift | local toolchain | `swift test` |

Issue parsing can still recognize validation commands and sandbox path hints for additional ecosystems such as Ruby, Rust, Go, and Java so unsupported-language issues fail explicitly instead of being silently misclassified. Execution support, test gates, and automatic healing are limited to Python, Node.js, and Swift.

### Docker-First Testing

By default, Flow Healer uses `test_gate_mode: local_then_docker`, which tries local toolchains first and falls back to Docker for Python and Node. Swift is local-first and intentionally does not use Docker.

```yaml
repos:
  - name: my-node-project
    test_gate_mode: docker_only
    local_gate_policy: skip
```

The `local_gate_policy` options are:
- `auto` - skip if unavailable (default)
- `force` - fail if unavailable
- `skip` - always skip local testing

## Quickstart

### 1. Install

```bash
git clone <your-repo-url>
cd flow-healer
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### 2. Create config

Copy `config.example.yaml` into `~/.flow-healer/config.yaml` and adjust repo details:

```yaml
service:
  github_token_env: GITHUB_TOKEN
  env_file: ""
  poll_interval_seconds: 30
  state_root: ~/.flow-healer
  connector_backend: exec
  connector_command: codex
  connector_model: gpt-5.4
  connector_timeout_seconds: 300

repos:
  - name: demo
    path: /absolute/path/to/target-repo
    repo_slug: owner/repo
    default_branch: main
    enable_autonomous_healer: true
    healer_mode: guarded_pr
    issue_required_labels:
      - healer:ready
    pr_actions_require_approval: false
    pr_required_label: healer:pr-approved
    pr_auto_approve_clean: true
    pr_auto_merge_clean: true
    pr_merge_method: squash
    max_concurrent_issues: 3
    test_gate_mode: local_then_docker
    local_gate_policy: auto
    language: ""
    docker_image: ""
    test_command: ""
    install_command: ""
```

Export your GitHub token before running:

```bash
export GITHUB_TOKEN=your_token_here
```

By default, Flow Healer no longer pauses for a `healer:pr-approved` issue label before opening or updating a PR. It also makes a best-effort approval and merge pass for clean PRs with no merge conflicts. Approval still cannot happen from the same GitHub actor that opened the PR, because GitHub blocks self-approval.

Or point Flow Healer at an existing env file:

```yaml
service:
  github_token_env: GITHUB_TOKEN
  env_file: /absolute/path/to/.env
```

To run through the local app-server instead of `codex exec`, switch the backend:

```yaml
service:
  connector_backend: app_server
  connector_command: codex
```

### 3. Run health checks and a single pass

```bash
flow-healer doctor
flow-healer status
flow-healer start --once
flow-healer serve
```

## Documentation

Use [docs/README.md](docs/README.md) as the active doc map for setup, usage, operations, and architecture notes. Historical planning and review artifacts are preserved under `docs/archive/`.

## Command Reference

| Command | Purpose |
| --- | --- |
| `flow-healer doctor [--repo NAME]` | Validate repo path, git, Docker, Codex, and token setup |
| `flow-healer status [--repo NAME]` | Show current issue counts, pause state, and recent attempts |
| `flow-healer start [--repo NAME] [--once]` | Start the always-on runtime (healer loop + web dashboard + pollers) or run a single iteration |
| `flow-healer pause [--repo NAME]` | Pause autonomous processing for a repo |
| `flow-healer resume [--repo NAME]` | Resume autonomous processing |
| `flow-healer scan [--repo NAME] [--dry-run]` | Run deterministic scan checks with optional no-write mode |
| `flow-healer serve [--repo NAME] [--host HOST] [--port PORT]` | Run healer loop + web dashboard + Apple Mail/Calendar pollers |

`flow-healer start` now launches the same always-on runtime as `flow-healer serve` so the dashboard stays up with the service. `flow-healer start --once` remains the one-pass maintenance path.

## Runtime Ops

For runtime debugging and recovery, the repo ships operator-focused scripts:

```bash
scripts/diagnose_runtime.sh ~/.flow-healer/config.yaml my-repo
scripts/verify_runtime.sh ~/.flow-healer/config.yaml my-repo
FLOW_HEALER_RESTART=1 scripts/remediate_runtime.sh ~/.flow-healer/config.yaml my-repo
```

- `diagnose_runtime.sh` captures command resolution, PATH, launchd context, `doctor`, and `status`.
- `verify_runtime.sh` fails fast if repo path, git state, token, connector health, or circuit-breaker readiness are not healthy.
- `remediate_runtime.sh` suggests a safer absolute `connector_command` value and can restart the launch agent when explicitly requested.

### Docker Runtime Controls

Flow Healer can now start Docker on demand for SQL validation and Docker test gates, then shut the runtime down again after an idle window.

```bash
export FLOW_HEALER_DOCKER_RUNTIME=colima
export FLOW_HEALER_DOCKER_IDLE_SHUTDOWN=1
export FLOW_HEALER_DOCKER_IDLE_SECONDS=900
export FLOW_HEALER_SQL_AUTO_PAUSE_SUPABASE=1
```

- `FLOW_HEALER_DOCKER_RUNTIME`: `auto`, `docker_desktop`, `colima`, `orbstack`, or `none`
- `FLOW_HEALER_DOCKER_IDLE_SHUTDOWN`: `1` to stop the selected runtime when Flow Healer has not used Docker recently
- `FLOW_HEALER_DOCKER_IDLE_SECONDS`: idle threshold before shutdown
- `FLOW_HEALER_SQL_AUTO_PAUSE_SUPABASE`: pause the Supabase DB container when SQL work finishes

For the rest of the operator workflow, failure recovery, and maintenance guidance, use [docs/usage.md](docs/usage.md) and [docs/operations.md](docs/operations.md).

## Apple Control DSL

Mail subjects and Calendar event titles use:

```text
FH: <command> repo=<repo-name> key=value ...
```

Examples:

```text
FH: status repo=demo
FH: pause repo=demo
FH: resume repo=demo
FH: once repo=demo
FH: scan repo=demo dry_run=true
FH: doctor repo=demo
```

## Development

Run the test suite:

```bash
pytest
```

Run a focused test while iterating:

```bash
pytest tests/test_healer_scan.py -v
```

## Operational Notes

- The default AI connector backend is `exec`, using the `codex` CLI.
- Set `connector_backend: app_server` to use local `codex app-server` over stdio instead.
- Test-gate execution is language-aware, with per-repo overrides for language/image/commands.
- State is stored per managed repo at `~/.flow-healer/repos/<repo-name>/state.db`.
- Scans can be dry-run only, or configured to create deduplicated GitHub issues above a severity threshold.

## Why This System Matters

Flow Healer is built for teams that want autonomous maintenance without surrendering control. It combines AI-assisted remediation with worktree isolation, explicit approval points, deterministic scan inputs, and durable local state, so the system can move fast without behaving like a black box.
