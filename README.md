<div align="center">

# Flow Healer

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](#getting-started)
[![Interface](https://img.shields.io/badge/interface-CLI%20%2B%20Dashboard-111111?style=for-the-badge&logo=gnubash&logoColor=white)](#core-workflow)
[![State](https://img.shields.io/badge/state-SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](#architecture)
[![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)](#development)
[![GitHub](https://img.shields.io/badge/automation-GitHub-181717?style=for-the-badge&logo=github&logoColor=white)](#how-it-fits-into-github)

**Trusted issue-to-PR automation with guarded fixes, isolated worktrees, validation gates, and an operator-first control plane.**

[Documentation](docs/README.md) · [Installation](docs/installation.md) · [Usage](docs/usage.md) · [Architecture](docs/architecture.md) · [Operations](docs/operations.md)

</div>

## Screenshot

<!-- Add a screenshot of the dashboard or control UI here -->
<!-- ![Screenshot](screenshot.png) -->

## Why Flow Healer

Flow Healer is for repositories that want AI automation without surrendering control. It watches GitHub issues, routes work into isolated worktrees, asks the configured connector (Codex by default) to produce a fix, runs validation gates, opens or updates the pull request, and preserves enough local state to recover safely when something goes wrong.

It is designed as a practical repo-operations loop, not just an issue generator. The service combines deterministic scanning, issue-driven healing, PR feedback ingestion, readiness checks, and runtime guardrails so maintainers can automate routine repair work while still understanding why the system did or did not run.

## What It Does

- Monitors one or many repositories from a single config file.
- Processes only issues that match the repo's required labels, `healer:ready` by default.
- Creates isolated git worktrees for each attempt so fixes stay contained.
- Infers execution root and language from issue bodies, validation commands, and sandbox paths.
- Runs guarded test gates with local and Docker-backed strategies.
- Tracks readiness, retry behavior, and failure domains in durable local state.
- Opens or updates PRs only after verification passes.
- Re-queues work when human reviewers leave PR feedback comments.
- Exposes a web dashboard and CLI controls for operators.
- Supports Apple Mail and Calendar command polling with a strict command DSL.

## Why Maintainers Trust It

- **Guarded execution:** isolated worktrees, verification gates, and branch-safe PR flow keep fix attempts contained.
- **Operator visibility:** `doctor`, `status`, and the dashboard surface readiness, connector health, retry behavior, and failure trends.
- **Deterministic recovery:** durable SQLite state, retry playbooks, and circuit-breaker behavior make failure handling inspectable instead of opaque.
- **Low-noise automation:** labels, approval options, and repo-level controls keep the loop policy-governed instead of free-running.

## Core Workflow

```text
GitHub Issue labeled healer:ready
                |
                v
       Flow Healer claims work
                |
                v
     Isolated git worktree is created
                |
                v
   Issue body is parsed into task targets,
   execution root, language, and validation
                |
                v
      The configured connector generates a candidate fix
                |
                v
   Local and/or Docker validation gates run
                |
        +-------+-------+
        |               |
        v               v
   verification ok   verification fails
        |               |
        v               v
   open/update PR    record outcome,
   and track review  learn, retry safely
```

## How It Fits Into GitHub

Flow Healer's default happy path looks like this:

1. A maintainer opens or labels a GitHub issue with `healer:ready`.
2. Flow Healer claims the issue and creates an isolated worktree.
3. The issue body is parsed into required outputs, reference-only context, validation commands, and language hints.
4. The configured connector (Codex by default) produces a patch inside the worktree.
5. Flow Healer runs verification using the right execution root and language strategy.
6. If the candidate survives verification, Flow Healer opens or updates the PR.
7. If a human leaves PR feedback, Flow Healer ingests that comment and re-queues a refined attempt.

With `pr_auto_approve_clean` and `pr_auto_merge_clean` enabled, the service can also make a best-effort approval and merge pass for clean PRs, subject to GitHub's normal actor and branch-protection rules.

## Supported Languages

Flow Healer currently provides first-class local execution for Python, Node.js, Swift, Go, Rust, Ruby, and Gradle-based Java reference targets.

| Language | Default strategy | Typical validation |
| --- | --- | --- |
| Python | local or Docker | `pytest -q` |
| Node.js | local or Docker | `npm test -- --passWithNoTests` |
| Swift | local only | `swift test` |
| Go | local only | `go test ./...` |
| Rust | local only | `cargo test` |
| Ruby | local only | `bundle exec rspec` |
| Java (Gradle) | local only | `./gradlew test --no-daemon` |

`java_maven` remains intentionally unsupported in this tranche; use Gradle for Java reference lanes.

## Framework Expansion

The issue parser and preflight layer now support framework-aware routing and smoke coverage for common JS and Python stacks.

- JS smoke sandboxes: `next`, `vue-vite`, `nuxt`, `angular`, `sveltekit`, `express`, `nest`
- Python smoke sandboxes: `fastapi`, `django`, `flask`, `pandas`, `sklearn`
- Additional language-reference sandboxes: `swift`, `go`, `rust`, `ruby`, `java-gradle`
- Browser-backed reference apps beyond `node-next`: `ruby-rails-web`, `java-spring-web`
- Node preflight toolchain checks: `pnpm`, `yarn`, `bun`
- Monorepo markers detected during preflight: `pnpm-workspace.yaml`, `nx.json`, `turbo.json`, `package.json#workspaces`
- New issue families for generation: `js-frameworks`, `python-frameworks`, `python-data-ml`

## Architecture

```text
                           +----------------------+
                           |  GitHub Issues / PRs |
                           +----------+-----------+
                                      |
                                      v
                    +-----------------+-----------------+
                    |        Flow Healer Service        |
                    |      CLI, runtime, dashboard      |
                    +-----------------+-----------------+
                                      |
         +----------------------------+----------------------------+
         |                            |                            |
         v                            v                            v
  Deterministic Scanner        Healing Loop                 Operator Controls
  issue generation             dispatcher, locks            CLI + web dashboard
  repo health signals          retries, verifier           Apple command DSL
         |                            |                            |
         +----------------------------+----------------------------+
                                      |
                                      v
                         +------------+-------------+
                         |   SQLite state store     |
                         | attempts, locks, memory  |
                         +------------+-------------+
                                      |
                                      v
                  Codex connector -> test gate -> PR / retry
```

## Project Layout

```text
src/flow_healer/
├── cli.py                   # CLI entrypoint
├── service.py               # multi-repo orchestration and status
├── healer_loop.py           # issue processing control loop
├── healer_runner.py         # prompt assembly, execution root, validation flow
├── healer_task_spec.py      # issue-body parsing and task extraction
├── healer_scan.py           # deterministic scan and issue generation
├── healer_tracker.py        # GitHub issues, PRs, and feedback integration
├── healer_workspace.py      # isolated git worktree management
├── healer_memory.py         # lessons from prior attempts
├── language_detector.py     # repo-level language detection
├── language_strategies.py   # per-language validation strategies
├── web_dashboard.py         # operator dashboard
└── store.py                 # SQLite persistence

tests/
├── test_healer_task_spec.py
├── test_healer_runner.py
└── e2e/
```

## Getting Started

### 1. Install locally

```bash
git clone <your-repo-url>
cd flow-healer
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### 2. Create the service config

```bash
mkdir -p ~/.flow-healer
cp config.example.yaml ~/.flow-healer/config.yaml
```

Example configuration:

```yaml
service:
  github_token_env: GITHUB_TOKEN
  poll_interval_seconds: 60
  state_root: ~/.flow-healer
  # exec | app_server | claude_cli | cline | kilo_cli
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

Optional swarm reliability knobs:

```yaml
repos:
  - name: demo
    swarm_analysis_timeout_seconds: 240
    swarm_recovery_timeout_seconds: 420
    swarm_orphan_subagent_ttl_seconds: 900
```

### 3. Export credentials

```bash
export GITHUB_TOKEN=your_token_here
```

If you already keep secrets in an env file, point the service at it:

```yaml
service:
  github_token_env: GITHUB_TOKEN
  env_file: /absolute/path/to/.env
```

### 4. Run a controlled pass

```bash
flow-healer doctor
flow-healer status
flow-healer start --once
```

### 5. Run the always-on service

```bash
flow-healer serve
```

`flow-healer start` without `--once` launches the same always-on runtime shape as `flow-healer serve`.

## Issue Format That Works Best

Flow Healer is most reliable when the issue body tells it exactly what code should change and how the result should be validated.

```md
Required code outputs:
- e2e-smoke/node/src/add.js
- e2e-smoke/node/test/add.test.js

Validation:
- cd e2e-smoke/node && npm test -- --passWithNoTests
```

This format helps Flow Healer infer:

- the expected output files
- the execution root
- the language strategy
- the right validation gate

If a file is reference material rather than an output target, mark it as input-only context in the issue body.

If you want stricter contract enforcement, enable strict parsing in repo config:

```yaml
repos:
  - name: demo
    issue_contract_mode: strict
    parse_confidence_threshold: 0.3
```

In strict mode, Flow Healer moves issues to `needs_clarification` unless both `Required code outputs` and `Validation` are explicit.

## Command Reference

| Command | Purpose |
| --- | --- |
| `flow-healer doctor [--repo NAME] [--preflight]` | Validate environment, repo config, Docker, Codex, and token setup |
| `flow-healer status [--repo NAME]` | Show queue state, pause status, recent attempts, swarm/failure-domain counters, retry playbook diagnostics, and reliability canary/trend rollups |
| `flow-healer start [--repo NAME] [--once]` | Run one controlled healing pass or start the continuous runtime |
| `flow-healer serve [--repo NAME] [--host HOST] [--port PORT]` | Start the runtime with dashboard and operator controls |
| `flow-healer scan [--repo NAME] [--dry-run]` | Run deterministic repo scanning with optional no-write mode |
| `flow-healer pause [--repo NAME]` | Pause autonomous processing for a repo |
| `flow-healer resume [--repo NAME]` | Resume autonomous processing for a repo |
| `flow-healer recycle-helpers [--repo NAME] [--idle-only]` | Ask the live daemon to recycle helper subprocesses safely |

## Runtime And Operations

Flow Healer includes operator-facing helpers for diagnosing runtime drift, connector failures, and unhealthy queues.

```bash
scripts/diagnose_runtime.sh ~/.flow-healer/config.yaml my-repo
scripts/verify_runtime.sh ~/.flow-healer/config.yaml my-repo
FLOW_HEALER_RESTART=1 scripts/remediate_runtime.sh ~/.flow-healer/config.yaml my-repo
```

Helpful runtime environment controls:

```bash
export FLOW_HEALER_DOCKER_RUNTIME=colima
export FLOW_HEALER_DOCKER_IDLE_SHUTDOWN=1
export FLOW_HEALER_DOCKER_IDLE_SECONDS=900
export FLOW_HEALER_SQL_AUTO_PAUSE_SUPABASE=1
```

These let Flow Healer choose a Docker runtime, shut it down after idle periods, and pause Supabase-related infrastructure after SQL validation work finishes.

## Apple Control DSL

When Mail or Calendar polling is enabled, subjects and titles use this command format:

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

## Documentation Map

- [docs/README.md](docs/README.md): top-level doc index
- [docs/installation.md](docs/installation.md): setup and configuration
- [docs/usage.md](docs/usage.md): command flows, lifecycle, and recovery
- [docs/architecture.md](docs/architecture.md): control loop and module map
- [docs/operations.md](docs/operations.md): runtime maintenance and incident response
- [docs/contributing.md](docs/contributing.md): development workflow and review expectations
- [docs/archive/README.md](docs/archive/README.md): historical planning and review artifacts

## Development

Run the full test suite:

```bash
pytest
```

High-value focused tests:

```bash
pytest tests/test_healer_task_spec.py -v
pytest tests/test_healer_runner.py -v
pytest tests/e2e/test_flow_healer_e2e.py -k mixed_repo_sandbox -v
```

Smoke-test the service locally:

```bash
flow-healer doctor
flow-healer start --once
flow-healer status
```

## Contributing

Flow Healer is easiest to work on when changes stay small, verified, and issue-driven.

- Follow the existing Python module boundaries instead of growing grab-bag files.
- Keep changes PEP 8 compliant and consistent with neighboring code.
- Add or update tests alongside behavior changes.
- Use issue bodies with explicit `Required code outputs` and `Validation:` sections when testing mixed-language or sandbox behavior.
- Keep healer-managed work on `healer/issue-*` branches and human work on normal branches.

## Notes

- Package name: `flow-healer`
- Python requirement: `>=3.11`
- CLI entrypoint: `flow_healer.cli:main`
- Primary runtime state root: `~/.flow-healer/`

## Acknowledgements

Built for maintainers who want AI-assisted repository upkeep with stronger operational guardrails than a simple issue bot.
