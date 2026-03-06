# Failure Catalog

## Confirmed Product Bugs

- Retry backoff timestamp stored in a format SQLite would not compare correctly against `CURRENT_TIMESTAMP`
  - Symptom: issue remains `queued` even after backoff should have expired
- Issue worktree branch not refreshed from updated base branch
  - Symptom: retries continue from a stale branch after `main` changed

## Connector / Patch Generation Issues

- Nested fenced code blocks inside a diff response cause the diff extractor to truncate the patch
  - Symptom: `patch_apply_failed`, often with `corrupt patch`
- Follow-up diff generated from repo root instead of the issue worktree
  - Symptom: `no_patch` on follow-up even though the file exists on the PR branch

## Repo Fixture / Setup Issues

- Target repo tests are not importable in Docker because the repo root is missing from the module path
  - Symptom: `tests_failed` with import errors during collection

## Operator / Environment Issues

- Invalid `gh` auth or missing `GITHUB_TOKEN`
- Running with the wrong Python interpreter and missing `PyYAML`
- Missing Docker when the repo relies on Docker-backed test gates
