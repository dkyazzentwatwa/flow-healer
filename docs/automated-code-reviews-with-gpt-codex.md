# Automated Code Reviews with GPT Codex

This guide is for running Codex as a code-review pass when you already have a bounded diff and want the highest signal for the lowest prompt cost. The cheapest useful review is usually the shortest one that still gives Codex the exact scope, the validation result, and a strict output contract.

The target is findings, not a rewrite. Ask Codex to identify concrete issues a human can act on quickly, then stop after one pass unless the review reveals a real ambiguity.

## When To Use Codex

Use Codex for narrow, evidence-based review questions:

- Did this patch introduce a correctness or compatibility bug?
- Are validation, error handling, or edge cases missing?
- Did the change add behavior without tests?
- Does the diff violate the intended issue scope?

Codex works best on one PR, one diff, or one small patch set. It is a poor fit for open-ended architecture debates, broad refactors without boundaries, or prompts that ask for implementation and review in the same pass.

## Cheapest Useful Review

For a low-cost review, include only what Codex cannot infer from the diff:

- the repo, issue, or PR being reviewed
- the exact changed files or diff
- the validation command and result
- the review goal, such as `find actionable findings only`
- the output shape you want back

If you already know the risky area, include the file and line range. If not, keep the scope at the PR or diff level and let Codex inspect from there. Avoid pasting old issue threads, long background notes, or implementation instructions that do not change the review decision.

## Prompt Pattern

The default shape should be short and strict:

```text
Review this PR for actionable findings only.
Scope: <files or diff>.
Validation: <command and result>.
Return at most 5 findings sorted by impact.
For each finding, include file, line, evidence, why it matters, and the smallest next step.
If there are no actionable findings, say that explicitly.
Do not summarize the patch.
Do not propose fixes unless they are directly tied to a finding.
```

That is usually enough when the diff is already small and the reviewer has the relevant context in hand.

## What To Include

- one diff or PR at a time
- a one-sentence review objective
- validation output or test summary
- a clear output contract
- file names or line references when the risky area is known
- an explicit ceiling on findings, such as `at most 5`

## What To Omit

- `review this code` with no scope
- a summary request when you want findings
- mixed requests to review and implement in the same pass
- long policy text or unrelated context dumps
- vague language like `be exhaustive` without a limit
- style-only critique unless style is the actual concern

## Cheap But Useful Prompts

Use these when you want the smallest prompt that still produces actionable output.

### PR Review

```text
Review this PR for actionable findings only.
Use the diff and the validation result below.
Return up to 5 findings, ordered by impact.
If there are no findings, say so explicitly.
```

### Regression Check

```text
Review this diff for regressions that could affect runtime behavior, validation, or test coverage.
Prioritize correctness, safety, and scope violations over style.
Return at most 5 findings.
```

### Line-Targeted Review

```text
Review the changes in <file> around <line range>.
Focus on correctness and missing coverage.
Return only actionable findings.
```

## Deeper Reviews

Spend more tokens only when the problem genuinely needs it:

- cross-file behavior changes
- security-sensitive edits
- performance-sensitive paths
- broad refactors with multiple dependencies

For those cases, add only the extra context the reviewer needs to judge the risk. Keep the output contract strict so the larger prompt still ends in a short, actionable answer.

## Practical Checklist

Before you trust the output, confirm the review:

- stayed inside the requested scope
- called out only actionable findings
- mentioned missing tests when behavior changed
- distinguished real risks from style preferences
- gave a clear next step for each finding
- matched the requested output format

## Related Docs

- [issue-contracts.md](issue-contracts.md): how Flow Healer scopes work from issue text
- [operator-workflow.md](operator-workflow.md): how review and draft PR states move through the queue
- [OpenAI Codex Prompting Guide](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide): official prompt guidance for Codex-style tasks
- [Introducing upgrades to Codex](https://openai.com/index/introducing-upgrades-to-codex/): product notes on Codex review use and prompt length
