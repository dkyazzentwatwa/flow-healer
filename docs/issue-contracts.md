# Issue Contracts

This doc is the canonical spec for Flow Healer issue bodies.

## Canonical Anchors

- [src/flow_healer/healer_task_spec.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_task_spec.py)
- [src/flow_healer/healer_runner.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_runner.py)
- [tests/test_healer_task_spec.py](/Users/cypher-server/Documents/code/flow-healer/tests/test_healer_task_spec.py)
- [tests/test_healer_runner.py](/Users/cypher-server/Documents/code/flow-healer/tests/test_healer_runner.py)
- [docs/harness-repro-contract-examples.json](/Users/cypher-server/Documents/code/flow-healer/docs/harness-repro-contract-examples.json)

## Required Fields

For code-changing issues, the contract should always declare:

- `Required code outputs:`: exact allowlist of files that may be edited
- `Validation:`: the commands that prove the requested change

In strict mode, Flow Healer moves issues to `needs_clarification` if these are missing or ambiguous.

## Optional Fields

Use these when the task needs them:

- `Execution root:` or `execution_root`: when the repo has multiple plausible roots
- input-only context markers for files that are references, not outputs
- `app_target`
- `runtime_profile`
- `fixture_profile`
- `browser_repro_mode`
- `repro_steps`
- `artifact_requirements`
- `judgment_required_conditions`

## Exact Semantics

### `Required code outputs`

This is an exact edit allowlist for sandboxed and issue-scoped work. Files not listed are out of scope unless Flow Healer explicitly widens scope under a documented policy, such as safe baseline-validation widening inside the same execution root.

If a file should inform the fix but must not be edited, mark it as input-only context instead of listing it as an output.

### `Validation`

These commands define the acceptance lane. They are run from the resolved execution root and override generic language defaults when explicitly provided.

Validation commands should be:

- deterministic
- scoped to the declared root when possible
- strong enough to prove the requested behavior

### `app_target`

Declares that the task is aimed at a browser-backed reference app under `e2e-apps/`.

### `runtime_profile`

Selects a configured app runtime profile. Use the profile name from [config.example.yaml](/Users/cypher-server/Documents/code/flow-healer/config.example.yaml) or repo config.

### `fixture_profile`

Selects deterministic seeded state for app-backed runs. See [docs/fixture-profile-guidance.md](/Users/cypher-server/Documents/code/flow-healer/docs/fixture-profile-guidance.md).

### `browser_repro_mode`

Supported values:

- `require_failure`: pre-fix browser failure must reproduce
- `allow_success`: constructive browser tasks may already pass before mutation

### `repro_steps`

Ordered browser actions and assertions for the browser harness.

Prefer outcome assertions over progress assertions. Stable outcomes such as the final route, winner text, visible board or reset state, and declared artifact presence are stronger than transient copy like `Current turn: X`.

When a browser task has a small set of known-valid UI states, use an explicit enumerated assertion such as `expect_any_text A || B`. Use this sparingly and only for clearly bounded valid states; do not use it as a generic fuzzy matcher.

For constructive `allow_success` tasks, prefer a fresh-entry or route-owned deterministic path over UI reset controls. A visible restart button may still be part of the product requirements, but the repro contract should not depend on clicking it unless reset behavior is the thing being verified.

### `artifact_requirements`

Explicit evidence requirements such as screenshots, console logs, network logs, or other named artifacts. See [docs/evidence-contract.md](/Users/cypher-server/Documents/code/flow-healer/docs/evidence-contract.md).

## Good Example

```md
Required code outputs:
- e2e-apps/ruby-rails-web/app/controllers/dashboard_controller.rb

Execution root:
- e2e-apps/ruby-rails-web

app_target: ruby-rails-web
runtime_profile: ruby-rails-web
fixture_profile: seeded-admin
browser_repro_mode: allow_success

repro_steps:
- goto /dashboard
- expect_text Ruby Browser Signal R1

artifact_requirements:
- screenshot: artifacts/ruby-dashboard.png
- console log
- network log

Validation:
- cd e2e-apps/ruby-rails-web && bundle exec rspec
```

## Outcome-Oriented Browser Example

```md
Required code outputs:
- e2e-apps/node-next/app/page.js

Execution root:
- e2e-apps/node-next

app_target: node-next
runtime_profile: web
browser_repro_mode: allow_success

repro_steps:
- goto /game
- expect_url /game
- expect_any_text Start game || Current turn: X
- click [aria-label="Cell 1"]
- click [aria-label="Cell 2"]
- click [aria-label="Cell 4"]
- click [aria-label="Cell 5"]
- click [aria-label="Cell 7"]
- expect_text Winner: X

artifact_requirements:
- screenshot: artifacts/game-board.png
- console log
- network log

Validation:
- cd e2e-apps/node-next && npm test -- --passWithNoTests
```

## Bad Example

```md
Please fix the dashboard and make it nicer.
```

Why it is bad:

- no explicit outputs
- no execution root
- no validation command
- no browser/runtime contract
- the requested scope is ambiguous

## Out-Of-Scope Mutation Rules

Do not mutate:

- sibling files not listed in `Required code outputs`
- lockfiles, manifests, or tests unless explicitly listed or widened by policy
- unrelated runtime or dashboard contracts while making a UI-only request

If the task cannot be completed within the declared scope, the correct behavior is to:

- stop for clarification, or
- create a documented follow-up issue

## Relationship To Other Docs

- use [docs/evidence-contract.md](/Users/cypher-server/Documents/code/flow-healer/docs/evidence-contract.md) for artifact semantics
- use [docs/lane-guides/README.md](/Users/cypher-server/Documents/code/flow-healer/docs/lane-guides/README.md) for lane-specific expectations
- use [docs/healing-state-machine.md](/Users/cypher-server/Documents/code/flow-healer/docs/healing-state-machine.md) for what happens after parsing
