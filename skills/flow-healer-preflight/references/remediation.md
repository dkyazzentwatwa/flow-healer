# Preflight Remediation

## Blocking Checks

- `gh_auth_ok = false`
  - Run `gh auth status`
  - Re-auth with `gh auth login` or refresh the token source before any live run
- `venv_ok = false`
  - Create `.venv` and install `-e '.[dev]'`
- `docker_ok = false`
  - Do not run live repair attempts that rely on Docker-backed pytest gates
- `repo_clean_git = false`
  - Review local changes before using the repo itself as a live target

## Active State Rules

- If the healer DB shows `running`, inspect whether an actual process is still active before retrying.
- If there is already an open PR for the target issue, prefer the follow-up skill instead of a new smoke run.
- If a smoke issue already exists, reuse it rather than creating a second one unless the first issue is permanently failed for fixture reasons.
