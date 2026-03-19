# Automated Code Reviews with GPT Codex

Use GPT Codex as a second-pass reviewer when you already have a bounded diff and want concrete findings a human can act on quickly. The goal is not to rewrite the patch. The goal is to surface evidence-backed issues, explain why they matter, and make the next step obvious.

OpenAI notes that Codex is effective for PR review work and that shorter prompts work well when the model already has code context available in the editor or repo. That fits Flow Healer's review pattern: keep the review narrow, give Codex the exact diff, and ask for actionable findings instead of a general critique.

## When To Use Codex

Use Codex when the review question is narrow and evidence-based:

- Did this patch introduce a correctness or compatibility bug?
- Are validation, error handling, or edge cases missing?
- Did the change add behavior without tests?
- Is the diff too broad or risky for the intended issue scope?

Codex works best on one PR, one diff, or one small patch set. It is a poor fit for open-ended architecture debates, broad refactors without boundaries, or prompts that ask for both implementation and review in the same pass.

## What To Give It

A useful review packet is small and explicit:

- the repo, issue, or PR being reviewed
- the exact changed files or diff
- the validation command and result
- the review goal, such as `find actionable issues only`
- the output format you want back

If you already know the risky area, include the file and line range. If not, keep the scope at the PR or diff level and let Codex inspect from there.

## Review Workflow

A reliable review pass usually follows this sequence:

1. validate the change first
2. summarize the diff and changed files
3. ask Codex for concrete findings only
4. require structured output
5. keep the review narrow enough that a human can verify it quickly

That pattern matches Flow Healer's review flow: the review pass should add signal, not noise.

## Prompt Tips

### Include

- one diff or PR at a time
- a one-sentence review objective
- validation output or test summary
- a clear output contract
- file names or line references when you already know the risky area
- an explicit ceiling on findings, such as `at most 5`

### Avoid

- `review this code` with no scope
- asking for a summary when you need findings
- mixing implementation instructions into a review prompt
- pasting unrelated policy text or old issue threads into the prompt
- asking Codex to be exhaustive, brief, and speculative at the same time
- asking for a fix and a review in the same pass

## Useful Prompt Patterns

Use these patterns when you want repeatable review output.

### Strict Findings Only

```text
Review this PR for actionable findings only.
Do not summarize the patch.
Do not suggest implementation changes unless they are directly tied to a finding.
For each finding, include file, line, evidence, why it matters, and the smallest next step.
If there are no actionable findings, say that explicitly.
```

### Regression-Focused Review

```text
Review this diff for regressions that could affect runtime behavior, validation, or test coverage.
Prioritize correctness, safety, and scope violations over style.
Return at most 5 findings sorted by impact.
```

### Automation-Friendly Output

If the result feeds another automation step, ask for a parseable format:

- JSON for machine-readable findings
- a short Markdown report for human review
- a table with `severity`, `location`, `description`, and `next_step`

Example:

```text
Return a Markdown review with:
- one-line verdict
- up to 5 findings
- for each finding: file, line, evidence, why it matters, and suggested fix
- if there are no actionable findings, say so explicitly
Keep the review under 300 words.
```

## Practical Checklist

Before you trust the output, confirm the review:

- stayed inside the requested scope
- called out only actionable findings
- mentioned missing tests when behavior changed
- distinguished real risks from style preferences
- gave a clear next step for each finding
- avoided generic praise or restating the diff
- matched the requested output format

## Do / Don't

### Do

- validate the patch before asking for review
- give Codex the exact scope and desired output
- ask for evidence, not vibes
- keep the prompt short and direct
- use the same prompt shape across similar review runs

### Don't

- ask Codex to both review and implement the fix in the same pass
- expect useful output from a diff with no context
- bury the review goal under long background text
- ask for a summary when you need actionable findings
- let the prompt become a catch-all for every concern you have

## Related Docs

- [issue-contracts.md](issue-contracts.md): how Flow Healer scopes work from issue text
- [operator-workflow.md](operator-workflow.md): how review and draft PR states move through the queue
- [OpenAI Codex Prompting Guide](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide): official prompt guidance for Codex-style tasks
- [Introducing upgrades to Codex](https://openai.com/index/introducing-upgrades-to-codex/): product notes on Codex review use and prompt length
