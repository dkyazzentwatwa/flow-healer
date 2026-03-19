# Automated Code Reviews with GPT Codex

Use GPT Codex as a second-pass reviewer when you already have a bounded diff and want concrete findings a human can act on quickly. This guide stays focused on review prompts, output quality, and practical review habits for automated code review runs. The goal is to ask for findings, evidence, and next steps, not a rewrite of the patch.

## When To Use Codex

Use Codex when the question is narrow and evidence-based:

- Did this patch introduce a correctness or compatibility bug?
- Are validation, error handling, or edge cases missing?
- Did the change add behavior without tests?
- Is the diff too broad or risky for the intended issue scope?

Codex works best on one PR, one diff, or one small patch set. It is a poor fit for open-ended architecture debates, broad refactors without boundaries, or prompts that ask for both implementation and review in the same pass.

## Good Review Prompts

A good prompt gives Codex only the context it needs to judge the patch:

- the repo, issue, or PR being reviewed
- the exact changed files or diff
- the validation command and result
- the review goal, such as `find actionable issues only`
- the output format you want back

Example:

```text
You are a strict code review findings engine.
Review this diff for only concrete, non-obvious, actionable issues.
Do not praise the code. Do not rewrite the patch. Do not give general advice.
Focus on correctness bugs, compatibility risks, missing validation, missing error handling,
meaningful maintainability risks, and missing tests for changed behavior.

Return JSON only:
{"verdict":"NO_ACTIONABLE_FINDINGS"|"ACTIONABLE_FINDINGS","findings":[...]}

Context:
- Issue: #1282
- Changed files: src/example.py, tests/test_example.py
- Validation: pytest tests/test_example.py -v
- Verifier summary: all checks passed
```

## Prompt Tips

### Include

- one diff or PR at a time
- a one-sentence review objective
- validation output or test summary
- a clear output contract
- file names or line references when you already know the risky area

### Avoid

- `review this code` with no scope
- asking for a summary when you need findings
- mixing implementation instructions into a review prompt
- pasting unrelated policy text or old issue threads into the prompt
- asking Codex to be exhaustive, brief, and speculative at the same time

### Ask For Structured Output

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

## Review Checklist

Before you trust the output, confirm the review:

- stayed inside the requested scope
- called out only actionable findings
- mentioned missing tests when behavior changed
- distinguished real risks from style preferences
- gave a clear next step for each finding
- avoided generic praise or restating the diff

## Practical Pattern

The most reliable workflow is:

1. validate the change first
2. summarize the diff and changed files
3. ask Codex for concrete findings only
4. require structured output
5. keep the result narrow enough that a human can verify it quickly

That pattern matches Flow Healer's review flow: the review pass should add signal, not noise.

## Related Docs

- [issue-contracts.md](issue-contracts.md): how Flow Healer scopes work from issue text
- [operator-workflow.md](operator-workflow.md): how review and draft PR states move through the queue
