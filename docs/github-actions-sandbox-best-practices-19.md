# GitHub Actions Sandbox Best Practices (Research Stress 19)

This note converts current GitHub primary-source guidance into a practical sandboxing and hardening checklist for repository automation. The safest baseline is consistent across the official docs: minimize `GITHUB_TOKEN` scope, keep untrusted code away from privileged triggers, prefer short-lived credentials, pin external actions immutably, and treat runners, artifacts, caches, and logs as part of the trust boundary.

## Current Best-Practice Summary

- Set explicit `permissions` on workflows or jobs and keep them minimal. GitHub documents that once a workflow declares any explicit permission, unspecified scopes become `none`.
- Run untrusted pull request code on `pull_request`, not `pull_request_target`. GitHub warns that `pull_request_target` runs in the base repository context and can be dangerous if it checks out or executes attacker-controlled code.
- Prefer GitHub-hosted runners for contributor-influenced workloads. GitHub-hosted runners start in a clean ephemeral VM for each job, while self-hosted runners can retain compromise across jobs if untrusted code runs there.
- Use OpenID Connect (OIDC) for cloud authentication instead of storing long-lived cloud keys in secrets. Grant `id-token: write` only to the job that truly needs federation.
- Pin third-party actions to a full-length commit SHA. GitHub identifies SHA pinning as the only immutable reference for an action version.
- Restrict which actions and reusable workflows are allowed at the repository or organization level when you need stronger supply-chain controls.
- Treat logs, caches, and artifacts as sensitive outputs. Mask generated secrets with `::add-mask::`, avoid uploading sensitive bundles, and set explicit artifact retention periods.
- Be careful with chained workflows. GitHub warns that running untrusted code before a `workflow_run` follow-up can create an escalation path if the follow-up has access to secrets or write tokens.

## Checklist

- Declare workflow or job `permissions` explicitly and start from `contents: read` or `{}`.
- Move write scopes down to job level when only one job needs elevated access.
- Use `pull_request` for build, test, lint, and any workflow that checks out or executes contributor-controlled code.
- Use `pull_request_target` only for trusted metadata tasks such as labeling, triage, or commenting, and never combine it with checkout of fork code, artifact reuse from untrusted runs, or cache writes derived from untrusted input.
- Treat issue titles, PR titles, PR bodies, branch names, commit messages, workflow inputs, and checked-out files as untrusted input when assembling shell commands or scripts.
- Prefer GitHub-hosted runners for public repositories and any workflow reachable by outside contributors.
- If self-hosted runners are unavoidable, isolate them from sensitive networks, avoid long-lived credentials on the host, and favor ephemeral or just-in-time runner patterns so each job starts clean.
- Use OIDC trust conditions that restrict repository, ref, environment, or event context instead of minting broad cloud credentials.
- Pin all external actions to full commit SHAs and review their source before adoption.
- Restrict which actions and reusable workflows may run through repository or organization Actions policy where governance allows it.
- Protect sensitive environments with required reviewers before deployment jobs can access high-value secrets.
- Set explicit artifact `retention-days`, and avoid uploading credential files, environment dumps, or raw debug archives.
- Review `workflow_run` designs carefully so an untrusted upstream workflow cannot smuggle state into a privileged downstream one.

## Do / Don't

### Do

- Do keep `GITHUB_TOKEN` permissions explicit and narrowly scoped.
- Do separate metadata-only automation from workflows that execute repository code.
- Do use GitHub-hosted runners for fork and contributor traffic unless you have a deliberate isolation design for self-hosted infrastructure.
- Do replace stored cloud keys with OIDC federation when the provider supports it.
- Do pin third-party actions to verified full SHAs and audit them periodically.
- Do mask generated tokens and one-time credentials even when they are not stored as GitHub secrets.
- Do set short artifact retention and upload only the files another person or workflow genuinely needs.
- Do limit which actions and reusable workflows are allowed when you need stronger supply-chain guarantees.

### Don't

- Don't run build, test, or arbitrary repository code under `pull_request_target` to gain write permissions or secret access.
- Don't assume self-hosted runners are clean between jobs unless you have engineered that property.
- Don't give broad workflow-level write scopes to every job when only one job mutates state.
- Don't rely on action tags alone when you need immutability; tags can move, full SHAs do not.
- Don't store long-lived cloud credentials in GitHub secrets if OIDC federation is available.
- Don't upload secrets, credential files, environment snapshots, or sensitive debug bundles as artifacts.
- Don't let an untrusted workflow feed caches, artifacts, or other state into a privileged `workflow_run` follow-up without an explicit trust review.

## Minimal Safe Patterns

### Least-Privilege Token Baseline

```yaml
permissions:
  contents: read
```

### Job-Scoped OIDC Instead Of Static Cloud Keys

```yaml
jobs:
  deploy:
    permissions:
      contents: read
      id-token: write
```

### Metadata-Only `pull_request_target`

Use `pull_request_target` only when the workflow acts on pull request metadata in the base repository context, such as applying a label or posting a comment. Do not check out the pull request head, execute pull request code, or consume untrusted artifacts in that context.

## Practical Review Questions

1. Does this workflow execute any contributor-controlled code or shell input?
2. If yes, is it running on `pull_request` with only the minimum read-level access it needs?
3. Does any job truly need write scopes, or can the default stay at `contents: read`?
4. Are all third-party actions pinned to full SHAs?
5. If cloud access is needed, can OIDC replace a stored credential?
6. Could a runner, cache, artifact, or log expose data that should stay private?
7. Could an untrusted workflow influence a privileged `workflow_run` follow-up?
8. Are repository or organization policies enforcing the same supply-chain rules maintainers expect authors to follow manually?

## Primary Sources

1. GitHub Docs, "Workflow syntax for GitHub Actions"  
   https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
2. GitHub Docs, "Events that trigger workflows"  
   https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
3. GitHub Docs, "Secure use reference"  
   https://docs.github.com/en/actions/reference/security/secure-use
4. GitHub Docs, "Using GitHub-hosted runners"  
   https://docs.github.com/en/actions/how-tos/using-github-hosted-runners/using-github-hosted-runners
5. GitHub Docs, "Self-hosted runners"  
   https://docs.github.com/en/actions/concepts/runners/self-hosted-runners
6. GitHub Docs, "OpenID Connect reference"  
   https://docs.github.com/en/actions/reference/security/oidc
7. GitHub Docs, "Managing GitHub Actions settings for a repository"  
   https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
8. GitHub Docs, "Using secrets in GitHub Actions"  
   https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
9. GitHub Docs, "Store and share data with workflow artifacts"  
   https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow
10. GitHub Docs, "Disabling or limiting GitHub Actions for your organization"  
    https://docs.github.com/en/organizations/managing-organization-settings/disabling-or-limiting-github-actions-for-your-organization
11. GitHub Docs, "Use `GITHUB_TOKEN` for authentication in workflows"  
    https://docs.github.com/en/actions/tutorials/authenticate-with-github_token
