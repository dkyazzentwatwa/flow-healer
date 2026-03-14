# Issue Contracts

This doc is the canonical specification for Flow Healer issue bodies and the task spec compiled from them.

## Canonical Anchors

- [src/flow_healer/healer_task_spec.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_task_spec.py)
- [src/flow_healer/healer_runner.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_runner.py)
- [src/flow_healer/healer_loop.py](/Users/cypher-server/Documents/code/flow-healer/src/flow_healer/healer_loop.py)
- [tests/test_healer_task_spec.py](/Users/cypher-server/Documents/code/flow-healer/tests/test_healer_task_spec.py)
- [tests/test_healer_runner.py](/Users/cypher-server/Documents/code/flow-healer/tests/test_healer_runner.py)
- [docs/harness-repro-contract-examples.json](/Users/cypher-server/Documents/code/flow-healer/docs/harness-repro-contract-examples.json)

## Core Rule

The issue body is the runtime contract. Flow Healer compiles it into a `HealerTaskSpec` that decides:

- task kind
- output targets
- input-only context
- execution root
- validation commands
- browser/runtime requirements
- artifact requirements
- judgment-required conditions

If the contract is weak, the right fix is to tighten the issue body or the parser contract, not to teach the connector a one-off heuristic.

## Supported Contract Fields

### Required for code-change issues

- `Required code outputs:`
- `Validation:`

In strict mode, missing required outputs or missing validation routes the issue to `needs_clarification`.

### Optional but first-class

- `Execution root:`
- `app_target:`
- `entry_url:`
- `runtime_profile:`
- `fixture_profile:`
- `browser_repro_mode:`
- `repro_steps:`
- `artifact_requirements:`
- `judgment_required_conditions:`
- input-only context sections or inline input-only phrasing

## Accepted Syntax

The parser accepts both section-style and directive-style forms.

Examples:

```md
Required code outputs:
- src/flow_healer/healer_task_spec.py
- tests/test_healer_task_spec.py

Execution root:
- e2e-smoke/node

Validation:
- cd e2e-smoke/node && npm test -- --passWithNoTests
```

```md
app_target: node-next
runtime_profile: web
fixture_profile: seeded-admin
browser_repro_mode: allow_success

repro_steps:
- goto /dashboard
- expect_text Artifact Proof Java E1

artifact_requirements:
- screenshot: artifacts/demo.png
- console log
- network log
```

The parser also recognizes a `Task kind:` hint inside the issue body when you need to force classification such as `docs`.

## Required Code Outputs

`Required code outputs:` defines the intended mutation scope.

Semantics:

- for sandboxed issue-scoped work, the named targets are the exact allowed edit set
- outside strict sandbox cases, named targets are still required anchors for the fix
- files marked as input-only context are not outputs and should not be edited

Do not use this field as a vague suggestion list. If a file is expected to change, name it.

## Input-Only Context

Use input-only context for files that inform the fix but are not output targets.

Supported patterns include:

- explicit sections like `Input context`
- phrases such as `input-only`, `spec only`, or `not output targets`

This lets the runner tell the connector which files are references without widening mutation scope.

## Validation

`Validation:` defines the acceptance lane for the issue.

Rules:

- commands are parsed from the issue body, not the title
- explicit validation commands override generic language defaults
- validation should run from the declared or inferred execution root
- mismatched roots are linted as `validation_root_mismatch`

Supported command families include common `npm`, `pnpm`, `yarn`, `bun`, `pytest`, `python -m pytest`, Django `manage.py test`, `bundle exec rspec`, `cargo test`, `go test`, `swift test`, `mvn test`, `./gradlew test`, and `./scripts/healer_validate.sh`.

## Execution Root

`Execution root:` is required whenever multiple plausible roots exist.

If the declared output targets span multiple sandboxes or the validation root points somewhere else, the contract is ambiguous and the issue should stop for clarification rather than guessing.

Examples of lint results:

- `ambiguous_execution_root`
- `validation_root_mismatch`

## Browser-App Contract Fields

### `app_target`

Declares that the issue targets a browser-backed app lane.

### `runtime_profile`

Selects the configured runtime profile to boot for the attempt. Missing configured profiles fail the run with `app_runtime_profile_missing`.

### `entry_url`

Optional browser entry URL. Relative paths are resolved against the booted runtime readiness URL.

### `fixture_profile`

Selects deterministic seeded state. If the runtime profile defines a fixture driver, the runner can call it for prepare/auth-state steps.

### `browser_repro_mode`

Supported values:

- `require_failure`
- `allow_success`

`require_failure` means the pre-fix journey must reproduce the failure.

`allow_success` is for constructive browser tasks where the requested behavior may already pass before mutation. In that mode, Flow Healer can succeed with no code diff if the journey passes and the required evidence is complete.

## `repro_steps`

`repro_steps:` is an ordered list of browser actions and assertions.

Prefer outcome-oriented assertions over fragile progress copy. Stable examples:

- `expect_url /game`
- `expect_text Winner: X`
- `expect_any_text Start game || Current turn: X`

Use `expect_any_text` only for a bounded set of known-valid states, not as a fuzzy matcher.

## `artifact_requirements`

This field declares promotion-blocking browser evidence requirements. Common examples:

- `screenshot: artifacts/demo.png`
- `console log`
- `network log`
- `failure_video`
- `resolution_video`

The exact blocking behavior is defined in [docs/evidence-contract.md](/Users/cypher-server/Documents/code/flow-healer/docs/evidence-contract.md).

## Docs And Artifact-Only Tasks

Not every issue is a code-change issue. Artifact-only or docs tasks can be valid without `Validation:` when the task classifies as docs/artifact-only. For example, a docs issue targeting `docs/*.md` can pass strict lint without a validation command.

That is the exception, not the default. If the task changes runtime behavior, include validation.

## Good Examples

### Code-change sandbox issue

```md
Required code outputs:
- e2e-smoke/node/src/add.js
- e2e-smoke/node/test/add.test.js

Validation:
- cd e2e-smoke/node && npm test -- --passWithNoTests
```

### Browser-backed issue

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

## Bad Contracts

```md
Please fix the dashboard and make it nicer.
```

Why this is bad:

- no output targets
- no validation
- no execution root
- no browser/runtime contract
- no clear mutation boundary

## Relationship To Clarification Stops

The loop can stop with `needs_clarification` when the contract is too weak to edit safely. The clarification comment points the operator back to these sections:

- `Required code outputs`
- `Execution root`
- `Validation`

Those stops are intentional. They are not a signal to broaden heuristics silently.

## Testing Expectations

When issue-contract behavior changes, run:

```bash
pytest tests/test_healer_task_spec.py -v
pytest tests/test_healer_runner.py -v
python scripts/validate_repro_contract_examples.py
```

If the new behavior affects queue routing or clarification stops, also run:

```bash
pytest tests/test_healer_loop.py -v
```

## Relationship To Other Docs

- [docs/evidence-contract.md](/Users/cypher-server/Documents/code/flow-healer/docs/evidence-contract.md) defines artifact completeness
- [docs/healing-state-machine.md](/Users/cypher-server/Documents/code/flow-healer/docs/healing-state-machine.md) defines what happens after parsing
- [docs/lane-guides/README.md](/Users/cypher-server/Documents/code/flow-healer/docs/lane-guides/README.md) defines lane-safe editing rules
