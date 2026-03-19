# Automated Code Reviews with GPT Codex

This guide covers how to use GPT Codex for automated code reviews when you want a focused second pass over a diff, not a rewrite of the implementation. The goal is to get concrete findings that a human reviewer can act on quickly.

## When to Use Codex for Review

Use Codex when the change is already scoped and you want help answering questions like:

- Did this patch introduce a correctness bug?
- Does the change miss validation, error handling, or compatibility checks?
- Are there missing tests for the behavior that changed?
- Is the diff too broad, risky, or hard to reason about?

Codex works best when the prompt is tied to one PR or one diff. It is a poor fit for open-ended architecture debates, broad refactors without boundaries, or prompts that ask for both implementation and review at the same time.

## What A Good Prompt Includes

A strong review prompt gives Codex the minimum context it needs to judge the patch:

- the repo or issue being reviewed
- the exact diff or changed files
- the validation results or verifier summary
- the review goal, such as "find actionable issues only"
- the required output format

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

- a single diff or PR
- the review objective in one sentence
- the validation command or test summary
- a clear output contract
- file names or line references if you already know the suspicious area

### Avoid

- "review this code" with no scope
- asking for a summary when you need findings
- mixing implementation instructions into a review prompt
- pasting unrelated policy text or old issue threads into the prompt
- asking Codex to be exhaustive, brief, and speculative at the same time

### Ask For Structured Output

If the result feeds another automation step, ask for a format that is easy to parse:

- JSON for machine-readable findings
- a short Markdown report for human review
- a table with `severity`, `location`, `description`, and `next_step`

Example structured prompt:

```text
Return a Markdown review with:
- one-line verdict
- up to 5 findings
- for each finding: file, line, evidence, why it matters, and suggested fix
- if there are no actionable findings, say so explicitly
Keep the review under 300 words.
```

## Review Quality Checklist

Before you trust the output, check that the review:

- stays inside the requested scope
- calls out only actionable findings
- mentions missing tests when behavior changed
- distinguishes real risks from style preferences
- gives a clear next step for each finding
- avoids generic praise or restating the diff

## Practical Pattern

The most reliable pattern is:

1. validate the change
2. summarize the diff and changed files
3. ask Codex for concrete findings only
4. require structured output
5. keep the result narrow enough that a human can verify it fast

That pattern matches Flow Healer's review flow: the review pass should add signal, not noise.

## Related Docs

- [issue-contracts.md](issue-contracts.md): how Flow Healer scopes work from issue text
- [operator-workflow.md](operator-workflow.md): how review and draft PR states move through the queue
