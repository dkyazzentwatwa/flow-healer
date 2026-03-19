# Apple Reminders for Flow Healer Project Management

This guide describes how to use Apple Reminders as a personal project-management layer for Flow Healer work.

It is intentionally narrow:

- It is for planning, triage, and follow-up.
- It does not change Flow Healer queue state or issue contracts.
- It does not describe a Reminders integration inside Flow Healer.

Use [operator-workflow.md](operator-workflow.md) for Flow Healer's queue states and operator actions, and [usage.md](usage.md) for the CLI commands that act on the repo.

## Recommended Setup

Create one reminder list per repo or per active project. For this repository, a single list named `Flow Healer` is usually enough.

Keep each reminder short and action-oriented:

- Start with the next visible action.
- Put the issue number or PR number in the title when there is one.
- Put links, commands, and extra context in the note field.
- Use subtasks only when the reminder needs a short checklist.
- Use due dates for follow-up timing, not for formal status tracking.

Example reminders:

- `#1287 - add Apple Reminders doc`
- `Review draft PR for issue 1267`
- `Check failed validation on repo doctor run`
- `Follow up on PR comment from maintainer`

## Daily Workflow

Use Reminders as an inbox, not as the source of truth.

1. Capture anything that needs attention while you are away from the terminal.
2. Review the list once in the morning and again before you stop working.
3. Move only the next concrete action into your active set.
4. When a task becomes durable repo work, record the authoritative details in GitHub or Flow Healer instead of keeping them only in Reminders.
5. Clear finished reminders promptly so the list stays a short execution queue.

## What to Track

Apple Reminders works well for:

- Small operator follow-ups
- PR reviews
- Manual verification steps
- Revisit tasks after a pause or external dependency
- Personal reminders tied to a specific Flow Healer issue or repo action

## What Not to Track

Do not use Reminders as a second issue tracker.

Avoid putting these in the list as if they were repo state:

- `queued`
- `claimed`
- `verify_pending`
- `pr_open`
- `failed`
- `blocked`

Those are Flow Healer runtime states. They belong in the repo's documented queue and state surfaces, not in Apple Reminders.

## Practical Rules

- Keep one reminder per actionable item.
- Prefer nouns plus verbs over long prose.
- Use tags only if they help you sort the inbox locally.
- If a reminder needs repo context, add the issue URL or file path in the note.
- If you need to hand the work back to Flow Healer, update the GitHub issue or CLI state and then leave the reminder as a follow-up only.

## Related Docs

- [docs/README.md](README.md)
- [docs/operator-workflow.md](operator-workflow.md)
- [docs/usage.md](usage.md)
- [docs/issue-contracts.md](issue-contracts.md)
