# GitHub Actions Sandbox Best Practices (Research Stress 17)

This note distills current GitHub primary-source guidance into a practical sandboxing baseline for CI and automation. The steady guidance across the official docs is to keep `GITHUB_TOKEN` permissions minimal, avoid running untrusted code in privileged contexts, prefer short-lived cloud credentials, pin third-party actions immutably, and treat runners, caches, artifacts, and logs as part of the sandbox boundary.

## Current Best-Practice Summary

- Set explicit `permissions` and keep them minimal. GitHub documents that you should grant the `GITHUB_TOKEN` the least required access, and once permissions are declared explicitly, unspecified scopes become `none`.[1][2]
- Run contributor-controlled code on `pull_request`, not `pull_request_target`. GitHub warns that running untrusted code on `pull_request_target` can lead to cache poisoning and unintended access to write privileges or secrets.[3][4]
- Treat `workflow_run` as privileged follow-up automation. GitHub documents that a `workflow_run`-triggered workflow can access secrets and write tokens even if the earlier workflow could not, so untrusted upstream output must not flow into privileged downstream jobs without review.[3]
- Prefer GitHub-hosted runners for contributor-reachable workflows. GitHub-hosted runners start in a fresh environment for each job, while self-hosted runners do not need to have a clean instance for every job execution.[4][5]
- Prefer OpenID Connect (OIDC) over stored cloud credentials. GitHub documents that `id-token: write` only enables requesting the JWT and does not grant write access to other resources.[6]
- Pin third-party actions to full commit SHAs. GitHub states that a full-length commit SHA is the only immutable release reference for an action.[4][7][8]
- Treat workflow inputs and GitHub context fields as untrusted. GitHub's secure-use guidance recommends avoiding inline script interpolation for attacker-controlled values such as PR titles and using safer argument passing patterns instead.[4]
- Keep artifacts and logs tight. GitHub recommends masking non-secret sensitive values with `::add-mask::VALUE` and documents explicit artifact retention controls with `retention-days`.[9][10]
- Use repository, organization, or enterprise Actions policies to restrict which actions can run, require SHA pinning, and gate risky fork-triggered workflow behavior.[7][8][11]

## Checklist

- Declare `permissions` on every workflow or job, starting from `contents: read` or `{}` and adding only the scopes a job truly needs.[1][2]
- Move write scopes to the narrowest possible job instead of granting workflow-wide write access.[1][2]
- Use `pull_request` for builds, tests, linting, and any workflow that checks out or executes pull request code.[3]
- Reserve `pull_request_target` for metadata-only tasks such as labeling or commenting, and do not combine it with checkout of fork code, cache writes from attacker-controlled input, or artifact reuse from untrusted runs.[3][4]
- Review any `workflow_run` design so an untrusted upstream job cannot pass poisoned artifacts, cache state, or other attacker-controlled data into a privileged downstream workflow.[3][4]
- Treat PR titles, PR bodies, issue text, branch names, commit messages, workflow inputs, artifacts, and checked-out files as untrusted input when assembling shell commands or generated scripts.[4]
- Prefer GitHub-hosted runners for public repositories and external-contributor workflows.[4][5]
- If self-hosted runners are required, isolate them from sensitive networks, avoid long-lived credentials on the host, and prefer ephemeral or just-in-time runner patterns so each job starts clean.[5][11]
- Use OIDC trust conditions that restrict repository, ref, environment, or reusable workflow context instead of issuing broad cloud credentials.[6]
- Pin external actions to full SHAs and verify the SHA belongs to the action's upstream repository, not a fork.[4]
- Restrict allowed actions and reusable workflows through repository, organization, or enterprise policy when you need stronger supply-chain control.[7][8][11]
- Mask generated secrets and other sensitive runtime values that are not stored in GitHub Secrets.[9]
- Set explicit artifact `retention-days` and avoid uploading credentials, environment dumps, or oversized debug bundles.[10]
- Protect sensitive deployments with environments and approval controls when a workflow can reach high-value secrets or production systems.[9][11]

## Do / Don't

### Do

- Do keep `GITHUB_TOKEN` permissions explicit, narrow, and close to the job that needs them.[1][2]
- Do separate metadata-only automation from workflows that build or execute repository code.[3][4]
- Do use GitHub-hosted runners for fork and contributor traffic unless you have a deliberate isolation model for self-hosted infrastructure.[4][5]
- Do replace long-lived cloud keys with OIDC federation and narrowly scoped trust conditions when your provider supports it.[6][9]
- Do pin third-party actions to verified full SHAs and periodically review the action source you depend on.[4][7][8]
- Do mask runtime secrets and reduce artifact retention to the minimum practical window.[9][10]
- Do use repository, org, or enterprise policy to limit allowed actions and require immutable pinning where available.[7][8][11]

### Don't

- Don't run builds, tests, or arbitrary PR code under `pull_request_target` just to gain write permissions or secret access.[3][4]
- Don't treat `workflow_run` as harmless glue code if it consumes artifacts or state from untrusted upstream workflows.[3][4]
- Don't assume self-hosted runners are clean between jobs or safe for untrusted public PRs by default.[5][11]
- Don't give broad workflow-level write scopes to every job when only one job mutates repository state.[1][2]
- Don't rely on floating tags alone when immutability matters; GitHub documents full SHAs as the only immutable action reference.[4]
- Don't store long-lived cloud credentials in repository secrets when OIDC federation is available.[6][9]
- Don't upload secrets, credential files, raw environment snapshots, or unnecessary debug archives as artifacts.[9][10]

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

Use `pull_request_target` only when the workflow needs base-repository context for safe metadata tasks such as labeling, commenting, or triage. Do not check out the pull request head, execute pull request code, restore attacker-influenced cache entries, or consume untrusted artifacts in that context.[3][4]

## Practical Review Questions

1. Does this workflow execute contributor-controlled code or interpolate contributor-controlled text into shell commands?
2. If yes, is it running on `pull_request` with only the minimum read-level access it needs?
3. Does any downstream `workflow_run` job consume artifacts, caches, or outputs from an untrusted workflow while holding secrets or write scopes?
4. Are all third-party actions pinned to full commit SHAs from the expected upstream repository?
5. Can OIDC replace any stored cloud key or long-lived deployment credential?
6. Could a runner, cache, log, or artifact leak sensitive data or amplify untrusted state?
7. Are repository, organization, or enterprise policies enforcing the same action restrictions maintainers expect authors to follow manually?

## Primary Sources

1. GitHub Docs, "Workflow syntax for GitHub Actions"  
   https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
2. GitHub Docs, "Use `GITHUB_TOKEN` for authentication in workflows"  
   https://docs.github.com/en/actions/tutorials/authenticate-with-github_token
3. GitHub Docs, "Events that trigger workflows"  
   https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
4. GitHub Docs, "Secure use reference"  
   https://docs.github.com/en/actions/reference/security/secure-use
5. GitHub Docs, "Self-hosted runners"  
   https://docs.github.com/en/actions/concepts/runners/self-hosted-runners
6. GitHub Docs, "OpenID Connect reference"  
   https://docs.github.com/en/actions/reference/security/oidc
7. GitHub Docs, "Managing GitHub Actions settings for a repository"  
   https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
8. GitHub Docs, "Enforcing policies for GitHub Actions in your enterprise"  
   https://docs.github.com/en/enterprise-cloud@latest/admin/enforcing-policies/enforcing-policies-for-your-enterprise/enforcing-policies-for-github-actions-in-your-enterprise
9. GitHub Docs, "Using secrets in GitHub Actions"  
   https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-your-workflow-does/use-secrets
10. GitHub Docs, "Store and share data with workflow artifacts"  
    https://docs.github.com/en/actions/tutorials/store-and-share-data
11. GitHub Docs, "Disabling or limiting GitHub Actions for your organization"  
    https://docs.github.com/en/organizations/managing-organization-settings/disabling-or-limiting-github-actions-for-your-organization
