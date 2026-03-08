# GitHub Actions Sandbox Best Practices (Research Stress 7)

This note condenses current GitHub primary-source guidance into a practical sandbox baseline for workflows that build code, process pull requests, or perform privileged follow-up automation. The stable themes across GitHub Docs are to keep `GITHUB_TOKEN` permissions minimal, avoid mixing untrusted code with privileged triggers, prefer short-lived federated credentials, pin third-party actions immutably, and treat runners, caches, artifacts, logs, and chained workflows as part of the trust boundary.

## Current Best-Practice Summary

- Declare explicit `permissions` and keep them narrow. GitHub documents that if you specify any permission, every unspecified permission is set to `none`.[1]
- Run contributor-controlled code on `pull_request`, not `pull_request_target`. GitHub warns that `pull_request_target` can expose secrets, write permissions, and cache state if you combine it with untrusted code from a fork or branch.[2][3]
- Treat `workflow_run` as privileged follow-up automation. GitHub documents that a workflow started by `workflow_run` can access secrets and write tokens even if the previous workflow could not, so artifacts, outputs, and caches from low-trust runs must not be consumed blindly.[2][3]
- Prefer GitHub-hosted runners for public repositories and any workflow reachable by external contributors. GitHub-hosted runners start from a fresh environment per job, while self-hosted runners do not need to have a clean instance for every execution.[3][4][5]
- If self-hosted runners are necessary, keep them scoped to private repositories where possible and restrict access with runner groups or selected workflows.[5][6]
- Prefer OIDC federation over long-lived cloud secrets. Grant `id-token: write` only to the job that needs it, and scope cloud trust conditions to the repository, ref, environment, or reusable workflow context that should be allowed to assume that identity.[7]
- Pin third-party actions to full commit SHAs. GitHub documents a full-length SHA as the only immutable action reference and exposes repository, organization, and enterprise settings that can enforce SHA pinning or limit allowed actions.[1][3][8][9]
- Treat workflow inputs and GitHub context values as untrusted data. GitHub explicitly documents script-injection risk from attacker-controlled fields such as branch names, pull request titles, issue bodies, and commit messages.[3][10]
- Keep secrets, logs, caches, and artifacts tight. GitHub recommends masking sensitive runtime values, limiting secret exposure, and setting explicit artifact retention while avoiding uploads that contain credentials or raw environment data.[11][12]
- Use artifact attestations for release outputs and other high-value deliverables, then verify them where provenance matters. GitHub documents attestations as provenance evidence rather than a blanket guarantee that an artifact is safe.[13][14]

## Checklist

- Declare `permissions` explicitly for each workflow or job, starting from `contents: read` or `{}` and adding only the scopes a job truly needs.[1]
- Move write scopes to the narrowest possible job instead of granting workflow-wide write access.[1]
- Use `pull_request` for build, test, lint, and any workflow that checks out or executes pull request code.[2]
- Reserve `pull_request_target` for metadata-only tasks such as labeling, triage, or comments, and do not combine it with checkout of fork code, untrusted artifact download, or cache writes derived from attacker-controlled input.[2][3]
- Review `workflow_run` designs so an untrusted upstream workflow cannot pass poisoned artifacts, outputs, or cache state into a privileged downstream workflow.[2][3]
- Treat PR titles, PR bodies, issue text, branch names, commit messages, workflow inputs, checked-out files, and downloaded artifacts as untrusted when constructing shell commands or generated scripts.[3][10]
- Prefer GitHub-hosted runners for public repositories and any workflow influenced by forks or outside contributors.[3][4][5]
- If self-hosted runners are required, isolate them from sensitive networks, avoid long-lived credentials on the host, and use runner groups or selected-workflow restrictions so only the intended repositories and workflows can reach them.[5][6]
- Use OIDC trust conditions that restrict repository, ref, environment, or reusable workflow context instead of issuing broad cloud credentials.[7]
- Pin external actions to full SHAs and verify that the pinned commit belongs to the intended upstream repository.[1][3][8][9]
- Restrict which actions and reusable workflows can run through repository, organization, or enterprise policy when you need stronger supply-chain controls.[8][9]
- Require review for fork PR workflow runs according to your threat model, and inspect workflow-file changes before approving runs from outside contributors.[8][15]
- Mask generated secrets and other sensitive runtime values with `::add-mask::` when they are not stored in GitHub Secrets.[11]
- Set explicit artifact `retention-days` and avoid uploading credentials, environment dumps, or oversized debug bundles.[12]
- Generate and verify artifact attestations for binaries, packages, container images, or other release artifacts that downstream users should be able to validate.[13][14]

## Do / Don't

### Do

- Do keep `GITHUB_TOKEN` permissions explicit, narrow, and close to the job that needs them.[1]
- Do separate metadata-only automation from workflows that build or execute repository code.[2][3]
- Do use GitHub-hosted runners for fork and contributor traffic unless you have a deliberate isolation model for self-hosted infrastructure.[3][4][5]
- Do restrict self-hosted runner access with runner groups or selected-workflow policies when those runners can reach sensitive systems.[5][6]
- Do replace long-lived cloud keys with OIDC federation and tightly scoped trust conditions when your provider supports it.[7]
- Do pin third-party actions to verified full SHAs and periodically review their source and update path.[1][3][8][9]
- Do mask runtime secrets and keep artifact retention to the minimum practical window.[11][12]
- Do generate attestations for release artifacts that consumers or admission policies are expected to verify.[13][14]

### Don't

- Don't run tests, builds, or arbitrary pull request code under `pull_request_target` just to gain write permissions or secret access.[2][3]
- Don't treat `workflow_run` as harmless glue if it consumes artifacts, outputs, or caches from untrusted upstream workflows.[2][3]
- Don't assume self-hosted runners are clean between jobs or safe for untrusted public PRs by default.[3][5][6]
- Don't grant broad workflow-level write scopes to every job when only one job mutates repository state.[1]
- Don't trust branch names, issue text, PR descriptions, or workflow inputs inside shell scripts without defensive handling.[3][10]
- Don't rely on floating tags alone when immutability matters; GitHub documents full SHAs as the only immutable action reference.[1][3]
- Don't store long-lived cloud credentials in repository secrets when OIDC federation is available.[7][11]
- Don't upload secrets, credential files, raw environment snapshots, or unnecessary debug archives as artifacts.[11][12]
- Don't approve fork PR workflows casually, especially when the change set touches `.github/workflows/` or other execution paths.[8][15]

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

Use `pull_request_target` only when the workflow needs base-repository context for safe metadata tasks such as labeling, comments, or triage. Do not check out the pull request head, execute pull request code, restore attacker-influenced cache entries, or consume untrusted artifacts in that context.[2][3]

### Treat `workflow_run` As A Trust Boundary

Use `workflow_run` for carefully reviewed follow-up automation, not as an automatic bridge from untrusted CI into privileged release or deployment logic. If the upstream workflow handled attacker-controlled code or inputs, review any artifacts, outputs, caches, or conclusions before a downstream privileged workflow consumes them.[2][3]

## Practical Review Questions

1. Does this workflow execute contributor-controlled code or interpolate contributor-controlled text into shell commands?
2. If yes, is it running on `pull_request` with only the minimum read-level access it needs?
3. Does any downstream `workflow_run` job consume artifacts, caches, or outputs from an untrusted workflow while holding secrets or write scopes?
4. Are all third-party actions pinned to full commit SHAs from the expected upstream repository?
5. Can OIDC replace any stored cloud key or long-lived deployment credential?
6. Could a runner, cache, log, artifact, or downstream workflow leak sensitive data or amplify untrusted state?
7. Are self-hosted runners limited to the repositories and workflows that actually need them?
8. Are fork PR workflow approval rules strong enough for the repository's exposure level?
9. Are artifact attestations generated and verified for the release artifacts that matter?
10. Are repository, organization, or enterprise policies enforcing the same action restrictions maintainers expect authors to follow manually?

## Primary Sources

1. GitHub Docs, "Workflow syntax for GitHub Actions"  
   https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions
2. GitHub Docs, "Events that trigger workflows"  
   https://docs.github.com/en/actions/reference/events-that-trigger-workflows
3. GitHub Docs, "Secure use reference"  
   https://docs.github.com/en/actions/reference/security/secure-use
4. GitHub Docs, "GitHub-hosted runners"  
   https://docs.github.com/en/actions/concepts/runners/github-hosted-runners
5. GitHub Docs, "Self-hosted runners"  
   https://docs.github.com/en/actions/concepts/runners/self-hosted-runners
6. GitHub Docs, "Managing access to self-hosted runners using groups"  
   https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access
7. GitHub Docs, "OpenID Connect reference"  
   https://docs.github.com/en/actions/reference/security/oidc
8. GitHub Docs, "Managing GitHub Actions settings for a repository"  
   https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
9. GitHub Docs, "Enforcing policies for GitHub Actions in your enterprise"  
   https://docs.github.com/en/enterprise-cloud@latest/admin/enforcing-policies/enforcing-policies-for-your-enterprise/enforcing-policies-for-github-actions-in-your-enterprise
10. GitHub Docs, "Script injections"  
    https://docs.github.com/en/actions/concepts/security/script-injections
11. GitHub Docs, "Using secrets in GitHub Actions"  
    https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
12. GitHub Docs, "Store and share data with workflow artifacts"  
    https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow
13. GitHub Docs, "Artifact attestations"  
    https://docs.github.com/en/actions/concepts/security/artifact-attestations
14. GitHub Docs, "Using artifact attestations to establish provenance for builds"  
    https://docs.github.com/en/actions/security-guides/using-artifact-attestations-to-establish-provenance-for-builds
15. GitHub Docs, "Approving workflow runs from forks"  
    https://docs.github.com/en/actions/how-tos/manage-workflow-runs/approve-runs-from-forks
