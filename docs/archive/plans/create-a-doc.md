# Verifier Guardrails Expansion (Docs-Only, Config-Only, High-Risk)

## Goal

Define and apply differentiated verifier guardrails for three classes of changes:

- docs-only
- config-only
- high-risk code changes

The objective is to keep low-risk edits permissive while preventing silent safety regressions in configuration and runtime-sensitive code paths.

## Why this is needed

Single-path verification is too coarse. Documentation-only changes can still ship broken operator guidance, configuration edits can silently alter behavior, and high-risk runtime edits often need stronger evidence than broad claims of success.

## Research basis

Key sources used to shape this policy:

- Git stable machine output: [`git status`](https://git-scm.com/docs/git-status) and [`git diff`](https://git-scm.com/docs/git-diff)
- Governance patterns for sensitive files/branches: [GitHub branch protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) and [CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/managing-repository-settings/about-code-owners)
- Config parsing safety: [Python `tomllib`](https://docs.python.org/3/library/tomllib.html) / [PyYAML safe load guidance](https://pyyaml.org/wiki/PyYAMLDocumentation)
- Targeted validation: [pytest usage and selecting tests with `-k`](https://docs.pytest.org/en/stable/how-to/usage.html)

## Current contract baseline in this repo

Flow Healer already has:

- change class naming in verifier/task handling,
- profile awareness in task specs,
- a short-circuit path for artifact-like updates.

The expansion below keeps that shape but makes policy class-specific.

## Change classes and guardrails

### A. docs-only

Definition:
- every changed path is documentation-like (`docs/**`, `*.md`, `*.rst`, `*.txt`, etc.),
- no source code, dependency declarations, migrations, workflows, or runtime configs are touched.

Pass criteria:
- change scope is strictly docs-only,
- all referenced commands/paths/flags/env names match the repository and current implementation,
- no claims of behavior that are unimplemented.

Fail criteria:
- stale commands, paths, or file references,
- factual claims about runtime behavior not present in code,
- code/config edits hidden inside a docs change.

Verifier stance:
- permissive on execution requirements,
- strict on factual integrity.

### B. config-only

Definition:
- all changed files are config examples/templates/settings,
- no source file changes in runtime paths.

Pass criteria:
- format-parse check for supported types (`yaml`, `json`, `toml`, etc.),
- no accidental secret/canonical local values in shared files,
- behavior-affecting defaults remain conservative and justified.

Reclassify to high-risk when config changes:
- modify auth/credential scope or token flow,
- alter deploy/branch/protection or connector execution targets,
- modify store/data-path, migration, lock, safety, deletion, or destructive toggles.

Fail criteria:
- parse errors,
- inclusion of real secrets/tokens/personal endpoints,
- broadened privilege or disabled safety gates without explicit justification.

Verifier stance:
- no generic code runtime requirement,
- mandatory syntax/semantic safety checks.

### C. high-risk code changes

Definition:
- edits touching runtime `src/**`, service start-up, dispatch, locking, persistence, validation core, dependency/lock files, or path families with elevated blast radius.

Pass criteria:
- validation evidence is path-specific,
- issue-level rationale explains blast radius,
- tests/smoke/checks are targeted to edited subsystems.

Fail criteria:
- sensitive-path edits without actionable validation,
- broad or unrelated refactors inside a high-risk fix,
- contradiction between claimed behavior and produced evidence.

Verifier stance:
- conservative default,
- prefer fail on ambiguity.

## Verification matrix

| Class | Primary objective | Minimum evidence |
|---|---|---|
| docs-only | factual accuracy | Path-scope check + repo fact consistency |
| config-only | safe behavior | parseability + safe-default + secret/local-value scan |
| high-risk | behavioral confidence | changed-path-linked validation and issue-scoped justification |

Default fail bias:

- docs-only: stale facts or scope violations;
- config-only: any unresolved risk in parsing/secret/safety;
- high-risk: weak or non-specific validation.

## Enforcement algorithm (verifier assembly)

1. Build the changed path set from diff output in machine-stable form.
2. Classify in priority order:
   - if any file is outside docs/config and is source/operational -> high-risk,
   - else if all files are docs-like -> docs-only,
   - else if all files are config-like -> config-only,
   - else high-risk.
3. Apply class-specific checks.
4. Escalate config-only to high-risk when trigger conditions fire.
5. Reject on mismatch between issue, scope, and claimed behavior.
6. Emit concise pass/fail summary with actionable failure reason.

## Operational checks by class

Docs-only
- File-scope check
- Reference integrity check for paths/commands/flags/env names
- Narrative-to-implementation consistency check

Config-only
- Parse check by format
- Secret/local value detection
- Boundary check for high-impact behavior knobs

High-risk
- Evidence-to-path mapping
- Targeted validation check (tests/smoke) against edited modules
- Scope-and-blast-radius review

## Suggested downstream docs updates

- Keep this as the canonical doc for verifier policy.
- Add a companion implementation plan document describing exact prompt fields and checker outputs.
- Link this policy into contributor/reviewer docs where verifier outcomes are interpreted.
