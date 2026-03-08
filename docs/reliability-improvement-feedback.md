# Reliability Improvement Feedback (Flow Healer)

## Current strengths to keep

- The pipeline already has a strong staged model (task parsing -> prompt assembly -> workspace staging -> validation -> PR), which is the right architecture for autonomous repair loops.
- `HealerTaskSpec` already supports output targets, input-only context files, execution-root inference, language hints, and issue-provided validation commands.
- `HealerRunner` already includes useful fallbacks (workspace edits, diff parsing, path-fenced file materialization, and artifact synthesis for docs/research tasks).

These are good foundations. The next gains are mostly about tightening contracts, reducing ambiguity, and guaranteeing deterministic outputs.

## Main gaps causing avoidable failures

### 1) "No-op" issues are still risky

If an issue is informational or non-code (for example, "investigate and report"), success can still depend on task classification and output target inference. If the issue is misclassified as a code-change task with no explicit targets, the run can fail with no patch/no workspace change.

### 2) Success is too dependent on issue wording quality

The system has excellent support for `Required code outputs` and `Validation:` hints, but in real repos many issue bodies are inconsistent. This creates brittle parsing, wrong execution roots, and misrouted validation.

### 3) Retry policy does not yet look fully failure-class aware

Retries are budgeted by profile (code vs artifact), but there is still room to add sharper per-failure handling (e.g., malformed output vs environment/toolchain failures vs task ambiguity).

### 4) Validation confidence varies by task type

Artifact-only validation is currently mostly markdown-link checks; quality checks for other artifact types (JSON/YAML/TOML, changelog/log files) can be more explicit to prevent low-signal outputs.

## Recommended roadmap (high ROI first)

## A) Add a guaranteed "completion artifact" mode (highest priority)

### Goal

Ensure every successfully processed issue produces at least one deterministic file change, even for non-code tasks.

### Proposal

Introduce a repo-level config like:

```yaml
healer:
  completion_artifact:
    enabled: true
    path_template: docs/healer-runs/{issue_number}-{slug}.md
    mode: always   # always | fallback_only
```

### Behavior

- `always`: any run must include a completion artifact file (code + summary allowed).
- `fallback_only`: only generate when no code/test/docs target was modified.

### Why this helps

- Eliminates no-op ambiguity.
- Gives operators a reliable audit trail for every issue attempt.
- Satisfies "task with no real code influence" requirements with deterministic output.

### Suggested artifact schema

Include structured metadata so downstream automation can parse it:

- issue id/title
- task kind and inferred language/root
- files changed
- validation commands executed
- validation result (pass/fail/skipped + reason)
- retry count and failure class (if applicable)
- generated timestamp and agent model

## B) Strengthen issue contract parsing with strict + lenient modes

### Goal

Reduce misclassification and wrong-root execution from loosely written issues.

### Proposal

Add parser modes:

- `strict`: requires explicit outputs + validation command; otherwise mark issue as "needs-clarification".
- `lenient` (default): infer as today, but write parser-confidence score and inference reasons into run metadata.

### Additional parsing hardening

- Explicitly parse "Output mode" and "Expected deliverable" fields when present.
- Add confidence scoring (`0.0-1.0`) for language/root/targets.
- If confidence below threshold, switch to clarification artifact generation instead of risky code edits.

## C) Add failure-class-specific retry playbooks

### Goal

Reduce repeated ineffective retries.

### Proposal

Map each failure class to an action plan:

- `malformed_diff` / format failures -> prompt-format repair path.
- `no_patch` / `no_workspace_change` -> enforce completion artifact fallback path.
- `patch_apply_failed` -> auto-refresh against latest base + smaller diff strategy.
- connector/tool unavailable -> circuit break quickly and annotate issue.
- validation failure -> one guided retry with focused failing test output.

Track per-class success rate and auto-tune retry budgets over time.

## D) Expand artifact validation beyond markdown links

### Goal

Stop low-quality non-code outputs from merging.

### Proposal

- `.json`: strict JSON parse.
- `.yaml/.yml`: parse + schema check when known.
- `.toml`: parse check.
- `.md`: keep link validation, add heading/lint checks for required sections.
- completion log/report files: enforce minimal required metadata keys.

## E) Add explicit task outcome states in issue/PR feedback

### Goal

Make operations smoother and triage faster.

### Proposal

Standardize outcome labels/comments:

- `healer:done-code`
- `healer:done-artifact`
- `healer:needs-clarification`
- `healer:blocked-environment`
- `healer:retry-exhausted`

This improves dashboarding and helps humans quickly choose next action.

## F) Improve preflight and self-healing for runtime/toolchain failures

### Goal

Reduce flaky failures unrelated to the actual issue.

### Proposal

- Preflight each run with a cheap capability probe for the inferred execution root.
- Cache probe results briefly (to avoid repeated overhead).
- If probe fails, skip proposer call and write a structured blocker artifact + issue comment with remediation steps.

## G) Add canary benchmarks for reliability regressions

### Goal

Measure if the agent is getting better release-over-release.

### Proposal

Create a fixed canary set of issues across docs/code/mixed tasks and track:

- first-pass success rate
- retries per successful issue
- wrong-root execution rate
- no-op rate
- mean time to valid PR

Gate releases on no regression in these canary metrics.

## Concrete implementation sequence

1. Implement completion artifact mode + metadata schema.
2. Wire no-change fallback to auto-generate completion artifact.
3. Add parser confidence scoring and low-confidence safe mode.
4. Add failure-class retry playbooks.
5. Add artifact validators by file type.
6. Add outcome labels/comments and dashboard aggregation.
7. Add reliability canary suite and CI gates.

## Quick wins you can ship immediately

- Add `fallback_only` completion artifact generation.
- Add `needs-clarification` outcome when issue parse confidence is low.
- Add JSON/YAML/TOML parse checks for artifact-only runs.
- Add a one-line run summary block to every PR body for observability.
