# Skills Upgrade Implementation

This repo now has the intended operator skill path under `skills/`:

- `flow-healer-local-validation`
- `flow-healer-preflight`
- `flow-healer-live-smoke`
- `flow-healer-triage`
- `flow-healer-pr-followup`
- `flow-healer-connector-debug`

The contract upgrade is implemented by making each existing `SKILL.md` executable from the skill file alone. Each core skill now names what to pass in, what JSON comes back, which fields matter first, when to stop, and what the default next action is. The connector failure path is also documented through a dedicated connector-debug skill.

## Baseline Preserved

- One repo-local skill still maps to each operator stage.
- Script-driven flows remain deterministic.
- Live GitHub mutation is still gated behind preflight and explicit stop conditions.
- The default path is readable without requiring `references/` on first pass.
- Documented fields stay aligned with current script output.

## Implemented Skill Contracts

### `flow-healer-local-validation`

`skills/flow-healer-local-validation/SKILL.md` now includes:

- `Inputs`
- `Outputs`
- `Key Output Fields`
- `Success Criteria`
- `Failure Handling`
- `Next Step`

The documented outputs remain aligned with `skills/flow-healer-local-validation/scripts/local_validation.py`:

- `repo_root`
- `checks`
- `checks[*].exit_code`
- `checks[*].output_tail`

The skill also keeps the warning explicit: do not rely on future-only fields such as `name`, `category`, or `duration_seconds`.

### `flow-healer-preflight`

`skills/flow-healer-preflight/SKILL.md` now includes the required shared sections and describes the real script contract from `skills/flow-healer-preflight/scripts/preflight_check.py`.

The documented outputs remain:

- `repo_path`
- `repo_slug`
- `required_checks`
- `context`
- `samples`
- `notes`

The key required checks are called out directly in the main skill body:

- `required_checks.gh_auth_ok`
- `required_checks.repo_exists`
- `required_checks.git_repo`
- `required_checks.repo_clean_git`
- `required_checks.venv_ok`
- `required_checks.docker_ok`

The skill now also states the real current constraint: `docker_ok` is required today.

### `flow-healer-live-smoke`

`skills/flow-healer-live-smoke/SKILL.md` now includes the required shared sections and keeps the template list aligned with `skills/flow-healer-live-smoke/scripts/make_live_smoke_bundle.py`.

The documented outputs remain:

- `template`
- `connector_path`
- `config_path`
- `state_root`

The skill keeps the real template choices explicit:

- `docs_scaffold`
- `docs_followup_note`

The artifact checklist now lives in the main skill body instead of only in the runbook:

- `issue_id`
- `pr_id`
- `branch_name`
- `attempt_state`
- `verifier_summary`
- `test_summary`

The skill also states the real boundary: bundle generation does not itself run `flow-healer start --once`.

### `flow-healer-triage`

`skills/flow-healer-triage/SKILL.md` now includes the required shared sections and maps each diagnosis bucket to a default operator action.

The documented outputs remain:

- `issue`
- `latest_attempt`
- `diagnosis`

The key fields called out in the skill body remain:

- `diagnosis`
- `latest_attempt.failure_class`
- `latest_attempt.failure_reason`
- `issue.state`

The default action mapping is now explicit for:

- `operator_or_environment`
- `repo_fixture_or_setup`
- `connector_or_patch_generation`
- `product_bug`
- `external_service_or_github`

### `flow-healer-pr-followup`

`skills/flow-healer-pr-followup/SKILL.md` now includes the required shared sections and keeps the reuse decision visible without requiring `references/`.

The documented outputs remain:

- `issue`
- `attempts`

The main skill body now calls out:

- `issue.pr_number`
- `issue.last_issue_comment_id`
- `issue.feedback_context`
- `issue.state`
- `attempts[*].state`

The safe-to-resume checklist is also present in the main skill body:

- issue still active
- PR still relevant
- new external feedback exists
- no active running attempt
- stored branch or worktree metadata still matches reality

### `flow-healer-connector-debug`

The previously missing connector-debug path now exists as `skills/flow-healer-connector-debug/SKILL.md`.

Its scope covers the highest-value gap identified in the original proposal:

- validating connector command resolution
- rerunning the connector against a fixed prompt fixture
- detecting empty diff output
- detecting malformed diff fences
- detecting invalid verifier JSON payloads
- detecting patch-apply failures
- comparing proposer and verifier output contracts

## Operator Graph

The current skill graph is now explicit:

1. `flow-healer-local-validation`
2. `flow-healer-preflight`
3. `flow-healer-live-smoke`
4. `flow-healer-triage`
5. `flow-healer-pr-followup`
6. `flow-healer-connector-debug` for connector and patch-generation failures

## Acceptance Status

Treat the contract upgrade as implemented because:

- each existing operator skill can be executed from its `SKILL.md` without opening a second doc for the default path
- every core skill names inputs, outputs, success criteria, failure handling, and next step
- the live-smoke artifact checklist is in the main skill body
- documented output fields align with current script JSON
- the connector failure path is explicitly routed through a dedicated skill
