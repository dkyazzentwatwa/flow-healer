---
name: code-review-github-issues
description: Review a local codebase, turn validated findings into small GitHub issues, and order them by fix path. Use when the user wants a code review that produces GitHub issues instead of code changes, especially for requests like "scan this repo and create issues", "do a multi-agent review", "open fix-path issues", or "review without editing code".
---

# Code Review GitHub Issues

Run a review-first workflow that scans the repo, verifies real defects, and opens small GitHub issues in dependency order.

Do not edit code unless the user explicitly changes the goal. Default output is GitHub issues, not patches.

This skill embeds the `full-code-issues` playbook directly. Use the bundled prompts in:

- [references/lead-agent.md](references/lead-agent.md)
- [references/code-reviewer.md](references/code-reviewer.md)
- [references/arch-reviewer.md](references/arch-reviewer.md)
- [references/github-pusher.md](references/github-pusher.md)
- [references/scratch-protocol.md](references/scratch-protocol.md)

## Workflow

1. Read `references/lead-agent.md` first and follow it as the orchestrator prompt.
2. Create `code-scratch.md` from `references/scratch-protocol.md` if it does not exist.
3. Check for issue templates, contribution rules, and existing open issues before creating anything.
4. Dispatch reviewer agents using `references/code-reviewer.md` and `references/arch-reviewer.md`.
5. Verify the strongest findings locally before opening issues.
6. Order the final issues by fix path using [references/fix-path-order.md](references/fix-path-order.md).
7. Create GitHub issues through the flow in `references/github-pusher.md`.
8. Optionally create one tracking issue that links the ordered set.

## Review Shape

- Prefer multi-agent review for medium or large repos.
- Split work into a few disjoint slices by subsystem or file priority.
- Ask review agents for real, actionable findings only.
- Cap each agent at a small number of findings so the repo does not get flooded.
- Keep ownership disjoint when delegating so findings do not overlap.
- Use `code-scratch.md` as the only shared memory between agents.

## Review Priorities

- P0: core execution, shared state, data access, scheduling, auth, validation
- P1: API routes, connectors, middleware, repo orchestration
- P2: UI, helpers, adapters, formatting, dashboards
- P3: config, scripts, tests, docs

Use tests mainly to verify or sharpen findings, not to create noise.

## Verification Rules

- Verify top findings against the source before opening issues.
- Prefer concrete repros, focused shell checks, or targeted tests.
- Do not open speculative issues.
- Merge duplicates and collapse minor cleanup into one issue when needed.
- Aim for roughly 5 to 12 issues unless the user asks for a broader sweep.

## Issue Rules

- Keep each issue small enough for one focused PR.
- Use action titles: `Fix ...`, `Prevent ...`, `Preserve ...`, `Constrain ...`.
- Include:
  - what is wrong
  - where it lives
  - why it matters
  - a suggested fix
  - layer or ordering context when useful
- Respect repo issue templates when present.
- Do not add healer or agent labels unless the user explicitly asks.
- If the user gives a custom label such as `core-fix`, apply it consistently.

## Embedded Prompts

- `lead-agent.md`: plan, dispatch, synthesize, and decide final ordering
- `code-reviewer.md`: per-file or small-batch reviewer prompt
- `arch-reviewer.md`: cross-file architecture pass
- `github-pusher.md`: GitHub issue creation flow
- `scratch-protocol.md`: exact `code-scratch.md` format

Treat these reference files as the source of truth for the subagent prompts.

## Fix Path Ordering

Use the ordering guide in [references/fix-path-order.md](references/fix-path-order.md).

Within a layer:

- Fix interface or contract changes before their callers.
- Fix shared utilities before isolated consumers.
- Put queue, locking, and state-consistency bugs before observability or cleanup.

## GitHub Flow

- Check `gh auth status` and repo access before issue creation.
- Check existing open issues to avoid obvious duplicates.
- If network access is blocked, rerun the `gh` commands with escalation.
- Prefer normal repo labels such as `bug`, `enhancement`, or a user-requested label.
- Create the tracking issue last so it can reference the final issue numbers.

## Suggested Delegation Prompt

If you are not loading the bundled reviewer prompt files directly, use wording like:

```md
Review these files for real, actionable issues only. Focus on correctness, design, performance, and test gaps. Return at most 5 findings, each with layer, title, file:line, explanation, and a suggested GitHub issue body. No code edits.
```

## Stop Conditions

- The repo or target GitHub remote is unclear and cannot be inferred safely.
- The user wants findings only and does not want issues created.
- The review produced too little verified signal to justify opening issues.

## Final Output

Report:

- which issues were created
- their ordering
- any label choices you applied
- whether a tracking issue was created

Keep the summary short.
