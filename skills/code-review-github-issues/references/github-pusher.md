# GitHub Pusher

Use this after the final issue order is stable.

## Mission

Read the ordered issue list and create GitHub issues in that order so the issue numbers reflect the recommended fix path.

## Preflight

1. Check `gh auth status`.
2. Confirm repo access.
3. Check existing labels.
4. Check existing open issues to avoid obvious duplicates.

## Rules

- Respect the repo's issue templates if present.
- Use only labels the user requested plus ordinary repo labels like `bug` or `enhancement`.
- Do not add healer or agent labels unless explicitly asked.
- Create the tracking issue last.

## Issue Body Requirements

Each issue should include:

- what is wrong
- where it lives
- why it matters
- suggested fix
- layer or ordering context when useful

## Tracking Issue

If useful, create one final tracking issue with a checklist of the ordered issues.
