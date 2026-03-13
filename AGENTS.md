# Repository Guidelines

Flow Healer is an issue-to-PR automation service with durable runtime state, lane-aware validation, browser evidence requirements, and both CLI and dashboard operator surfaces. If you are picking this repo up quickly, do not start by inferring behavior from scattered plans or recent commits. Start from the canonical docs below.

## Canonical Sources Of Truth

Read these first when the work touches the matching area:

- [docs/README.md](docs/README.md): canonical documentation index
- [docs/issue-contracts.md](docs/issue-contracts.md): issue-body semantics, mutation scope, runtime-profile fields, evidence fields, `browser_repro_mode`
- [docs/healing-state-machine.md](docs/healing-state-machine.md): claim-to-resolution runtime flow
- [docs/runtime-state.md](docs/runtime-state.md): SQLite tables, attempts, queue states, locks, safe resets
- [docs/evidence-contract.md](docs/evidence-contract.md): artifact completeness and browser-evidence rules
- [docs/dashboard.md](docs/dashboard.md): Next dashboard vs legacy Python dashboard, routes, and safe control-plane boundaries
- [docs/lane-guides/README.md](docs/lane-guides/README.md): lane-safe editing rules for `e2e-smoke/` and `e2e-apps/`
- [docs/agent-remediation-playbook.md](docs/agent-remediation-playbook.md): repeated-failure doctrine
- [docs/test-strategy.md](docs/test-strategy.md): which test to add when behavior changes or escapes

Historical planning docs under [docs/plans/](docs/plans/) and [docs/archive/README.md](docs/archive/README.md) are reference material only. They are not the authority for current behavior.

## Fast Orientation

If you need to build context in code after reading the docs, start here:

- `src/flow_healer/healer_task_spec.py`: parses issue title and body into task kind, outputs, input-only context, execution root, runtime profile, evidence requirements, and validation commands
- `src/flow_healer/healer_runner.py`: assembles the proposer prompt, stages connector output, runs validation, and enforces scope and evidence rules
- `src/flow_healer/healer_loop.py`: queue claiming, retry handling, quarantine, clarification flow, and orchestration
- `src/flow_healer/store.py`: durable SQLite state and migration-backed persistence
- `tests/test_healer_task_spec.py`, `tests/test_healer_runner.py`, `tests/test_healer_loop.py`: executable source of truth for issue-contract and runtime behavior

## Documentation-First Rules

- If a runtime, contract, lane, evidence, or dashboard behavior changes, update the corresponding canonical doc in the same change.
- Do not leave new semantics documented only in a plan doc, issue comment, or commit message.
- If you discover a repeated failure pattern caused by missing documentation, add or tighten the doc before teaching the connector a one-off workaround.
- Keep `README.md` high-level. Put operating semantics in `docs/`.

## Contract-First Issue Handling

- Treat [docs/issue-contracts.md](docs/issue-contracts.md) as authoritative for issue-body parsing and semantics.
- Use `Required code outputs` to define the intended mutation scope.
- Use `input-only context` for reference files that should not become output targets.
- Keep `Validation` scoped to the execution root actually owned by the issue.
- For constructive browser tasks that may already pass before mutation, use `browser_repro_mode: allow_success`.
- If an issue body is ambiguous, fix the contract or open a clarification path instead of encoding a fragile heuristic.

## Dashboard And Control-Plane Rules

- Read [docs/dashboard.md](docs/dashboard.md) before touching `apps/dashboard/` or `src/flow_healer/web_dashboard.py`.
- Treat UI-only edits differently from control-plane edits. If a change affects route data loading, dashboard proxy behavior, runtime status surfaces, or artifact/control semantics, update the canonical docs in the same change.
- Do not treat browser-app fixture changes as dashboard changes; app-backed sandboxes belong to the lane guides.

## Lane-Safe Editing Rules

- Read the relevant guide in [docs/lane-guides/README.md](docs/lane-guides/README.md) before editing anything under `e2e-smoke/` or `e2e-apps/`.
- Keep work inside the declared execution root unless the runner explicitly widens scope for a safe baseline blocker.
- Do not widen scope manually just because validation is red. First determine whether the failure is baseline, harness, contract, or lane-specific.
- Browser-backed app targets follow [docs/lane-guides/browser-apps.md](docs/lane-guides/browser-apps.md); fixture lanes follow their family guide.

## Evidence And Runtime-State Rules

- Read [docs/evidence-contract.md](docs/evidence-contract.md) before changing browser harness behavior, artifact publishing, or evidence verification.
- Read [docs/runtime-state.md](docs/runtime-state.md) before changing queue states, lease handling, retries, locks, migrations, or SQLite resets.
- Missing named artifact outputs are real blockers for browser-evidence issues even when the UI looks correct.
- Do not ad hoc rename artifacts, reinterpret queue states, or clear state blindly.

## Remediation Doctrine

- When the system fails repeatedly, prefer docs, contracts, tests, fixtures, or guardrails before adding connector cleverness.
- If a lane fails because the issue contract is weak, strengthen the issue contract and parser examples.
- If a runtime edge keeps escaping, add the missing invariant and regression test.
- If a fixture or browser app has repeated baseline blockers, document the lane and add the smallest safe guardrail that prevents blind retries.
- Use [docs/agent-remediation-playbook.md](docs/agent-remediation-playbook.md) as the operating doctrine for repeated failure handling.

## Project Structure

- `src/flow_healer/`: core Python runtime
- `tests/`: pytest suites that mirror runtime modules
- `apps/dashboard/`: modern Next dashboard
- `e2e-smoke/`: fixture lanes for language and framework smoke coverage
- `e2e-apps/`: browser-backed app targets and richer app fixtures
- `docs/`: canonical and supporting documentation

## Build, Test, And Development Commands

Create a local environment and install in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

High-value focused tests:

```bash
pytest tests/test_healer_task_spec.py -v
pytest tests/test_healer_runner.py -v
pytest tests/test_healer_loop.py -v
pytest tests/e2e/test_flow_healer_e2e.py -k mixed_repo_sandbox -v
```

Doc and contract validation:

```bash
python scripts/validate_repro_contract_examples.py
python scripts/check_harness_doc_drift.py
```

CLI smoke:

```bash
flow-healer doctor
flow-healer start --once
flow-healer status
```

## Branch And Workspace Hygiene

- Let healer-managed issue work stay on `healer/issue-*` branches and worktrees.
- Keep human changes on a normal branch based on `origin/main`.
- Do not edit inside `.apple-flow-healer/` unless you are explicitly debugging healer internals or a broken worktree.
- Before rebasing or pulling from `origin/main`, make sure `git status` is clean or any remaining changes are intentionally staged or stashed.

## Commit And Review Expectations

- Use Conventional Commit-style messages such as `docs: add runtime-state canon` or `fix: widen safe baseline blockers`.
- Keep pull requests small enough to review.
- Include test evidence for runtime changes and doc-validation output for documentation overhauls.
- When behavior changes, mention which canonical docs were updated alongside the code.

## Security And Config

- Do not commit tokens, local repo paths, or generated state.
- Store GitHub credentials in environment variables such as `GITHUB_TOKEN`.
- Keep runtime data under `~/.flow-healer/` as intended by the sample config.
