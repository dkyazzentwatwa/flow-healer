# GitHub Actions Sandbox Best Practices (Research Stress 18)

This note distills current GitHub primary-source guidance into a practical hardening baseline for workflows that build code, process pull requests, or automate repository changes. The recurring themes in GitHub's security documentation are straightforward: keep `GITHUB_TOKEN` permissions minimal, avoid running untrusted code in privileged contexts, prefer short-lived cloud credentials, pin external actions immutably, and treat runners, caches, artifacts, and logs as part of the sandbox boundary.

## Current Best-Practice Summary

- Declare explicit `permissions` and keep them narrow. GitHub documents that once any permission is set explicitly, every unspecified permission becomes `none`.[1]
- Run contributor-controlled code on `pull_request`, not `pull_request_target`. GitHub warns that using `pull_request_target` with untrusted code can expose secrets, write privileges, or cache state.[2][3]
- Prefer GitHub-hosted runners for workflows reachable by external contributors. GitHub-hosted runners start in a fresh environment per job, while self-hosted runners can retain compromise unless you engineer clean isolation yourself.[3][4][5]
- Prefer OIDC federation to long-lived cloud secrets. Grant `id-token: write` only to the job that actually needs a cloud identity token.[6]
- Pin third-party actions to a full commit SHA. GitHub calls full-SHA pinning the only immutable action reference.[3][7]
- Treat shell inputs as untrusted data. GitHub explicitly warns about script injection risks from issue titles, pull request bodies, branch names, and similar attacker-controlled values.[3]
- Keep logs, caches, and artifacts tight. Mask sensitive runtime values, avoid uploading confidential material, and set short retention for artifacts that must exist.[8][9]
- Use repository, organization, or enterprise policy to restrict which actions and reusable workflows can run, especially when you need stronger supply-chain guarantees.[7][10]

## Checklist

- Set workflow or job `permissions` explicitly, starting from `contents: read` or `{}` and adding only the scopes a job truly requires.[1][11]
- Move write permissions to the narrowest possible job instead of granting broad workflow-level write access.[1][11]
- Use `pull_request` for build, test, lint, and any job that checks out or executes pull request code.[2]
- Reserve `pull_request_target` for trusted metadata-only automation such as labeling or commenting, and do not combine it with checkout of fork code, untrusted artifact download, or cache writes derived from attacker-controlled input.[2][3]
- Treat issue bodies, PR text, branch names, workflow inputs, commit messages, and checked-out files as untrusted when assembling shell commands or generated scripts.[3]
- Prefer GitHub-hosted runners for public repositories and any workflow influenced by forks or outside contributors.[3][4]
- If self-hosted runners are required, isolate them from sensitive networks, avoid long-lived credentials on the host, and prefer ephemeral or just-in-time runners so each job starts clean.[3][5]
- Use OIDC trust conditions that restrict repository, ref, environment, reusable workflow, or event context instead of issuing broad cloud credentials.[6]
- Pin external actions to full SHAs and review their source before adoption or update.[3][7]
- Restrict allowed actions and reusable workflows at the repository or organization policy layer when governance or compliance requires tighter control.[7][10]
- Use environments and required reviewers for deployment jobs or any workflow that can reach high-value secrets.[3][8]
- Set explicit artifact `retention-days`, and do not upload raw environment dumps, credentials, or sensitive debug bundles.[9]
- Review cache and chained-workflow designs so untrusted jobs cannot poison inputs consumed by privileged follow-up workflows.[2][3]

## Do / Don't

### Do

- Do keep `GITHUB_TOKEN` permissions explicit, narrow, and close to the job that needs them.[1][11]
- Do separate metadata-only automation from workflows that build or execute repository code.[2][3]
- Do prefer GitHub-hosted runners for contributor-driven workloads unless you have a deliberate isolation model for self-hosted infrastructure.[3][4][5]
- Do use OIDC for cloud access and scope trust policies to the repository and execution context that actually needs access.[6]
- Do pin third-party actions to verified full SHAs and periodically review updates.[3][7]
- Do mask generated secrets, one-time credentials, and sensitive runtime values even when they were not stored in GitHub secrets.[8]
- Do keep artifact retention short and upload only files that another workflow or maintainer truly needs.[9]
- Do use Actions policy settings to narrow the allowed action surface when supply-chain control matters.[7][10]

### Don't

- Don't run tests, builds, or arbitrary PR code under `pull_request_target` to gain write access or secrets.[2][3]
- Don't assume self-hosted runners are automatically clean between jobs or safe for untrusted forks.[3][5]
- Don't grant workflow-wide write scopes when only one job mutates issues, pull requests, releases, or repository contents.[1][11]
- Don't trust branch names, issue text, PR descriptions, or workflow inputs inside shell scripts without defensive handling.[3]
- Don't store long-lived cloud credentials in repository secrets if your provider supports GitHub OIDC federation.[6][8]
- Don't rely on floating action tags alone when immutability matters; tags can move, but full SHAs are fixed.[3]
- Don't upload secrets, credential files, or oversized debug bundles into artifacts or logs.[8][9]
- Don't allow untrusted jobs to feed caches, artifacts, or workflow outputs into privileged follow-up automation without an explicit trust review.[2][3]

## Minimal Safe Patterns

### Least-Privilege Token Baseline

```yaml
permissions:
  contents: read
```

### Job-Scoped OIDC For Cloud Access

```yaml
jobs:
  deploy:
    permissions:
      contents: read
      id-token: write
```

### Metadata-Only `pull_request_target`

Use `pull_request_target` only when the workflow needs base-repository context for safe metadata tasks such as labeling, triage, or comments, and avoid checking out the PR head, running PR code, restoring attacker-influenced cache entries, or consuming untrusted artifacts there.[2][3]

## Practical Review Questions

1. Does this workflow execute contributor-controlled code or interpolate contributor-controlled text into shell commands?
2. If yes, is it running on `pull_request` with only the minimum read-level access it needs?
3. Does any job truly require write permissions, or can the default remain `contents: read`?
4. Are all third-party actions pinned to full commit SHAs?
5. Can OIDC replace any stored cloud key or long-lived deployment secret?
6. Could a runner, cache, artifact, log, or downstream workflow leak or amplify untrusted state?
7. Are repository or organization policies enforcing the same action restrictions maintainers expect authors to follow manually?

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
