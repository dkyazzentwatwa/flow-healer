# GitHub Actions Sandbox Best Practices (Research Stress 8)

This note condenses current GitHub primary-source guidance into a practical sandbox baseline for workflows that build code, process pull requests, or perform privileged follow-up automation. The repeated guidance across GitHub Docs is to minimize `GITHUB_TOKEN` permissions, keep untrusted code away from privileged triggers, prefer short-lived federated credentials, pin external actions immutably, and treat runners, caches, artifacts, logs, and chained workflows as part of the trust boundary.

## Current Best-Practice Summary

- Declare explicit `permissions` and keep them narrow. GitHub documents that if you specify any permission, every unspecified permission is set to `none`.[1][2]
- Run contributor-controlled code on `pull_request`, not `pull_request_target`. GitHub warns that `pull_request_target` can expose secrets, write permissions, and cache state if you mix it with untrusted code from a fork or branch.[3][4]
- Treat `workflow_run` as privileged follow-up automation. GitHub notes that downstream workflows triggered this way can access secrets and write tokens even if the upstream workflow could not, so artifacts, outputs, and caches from low-trust runs must not be consumed blindly.[3][4]
- Prefer GitHub-hosted runners for public repositories and any workflow reachable by external contributors. GitHub-hosted runners start from a fresh virtual machine for each job, while self-hosted runners do not inherently provide a clean instance per run.[4][5][6]
- Prefer OIDC federation over long-lived cloud secrets. Grant `id-token: write` only to the job that needs it, and scope cloud trust conditions to the repository, ref, environment, or reusable workflow context that should be allowed to assume that identity.[7]
- Pin third-party actions to full commit SHAs. GitHub documents a full-length SHA as the only immutable action reference and exposes repository and organization settings that can require SHA pinning.[4][8][9]
- Treat workflow inputs and GitHub context values as untrusted data. GitHub explicitly documents script injection risk from attacker-controlled fields such as branch names, pull request titles, issue bodies, and commit messages.[4][10]
- Keep logs, caches, and artifacts tight. GitHub recommends masking sensitive runtime values, setting explicit retention, and avoiding uploads that contain credentials, raw environment snapshots, or unnecessary debug data.[11][12]
- Use artifact attestations for high-value release outputs, then verify them where provenance matters. GitHub positions attestations as build provenance evidence, not as a substitute for verification policy.[13][14]
- Use repository, organization, or enterprise Actions policies to restrict the allowed action surface, require approval for fork PR workflows where appropriate, and enforce immutable pinning when governance matters.[8][9][15]

## Checklist

- Declare `permissions` explicitly for each workflow or job, starting from `contents: read` or `{}` and adding only the scopes a job truly needs.[1][2]
- Move write scopes to the narrowest possible job instead of granting workflow-wide write access.[1][2]
- Use `pull_request` for build, test, lint, and any workflow that checks out or executes pull request code.[3]
- Reserve `pull_request_target` for metadata-only tasks such as labeling, triage, or comments, and do not combine it with checkout of fork code, artifact download, or cache writes derived from attacker-controlled input.[3][4]
- Review `workflow_run` designs so an untrusted upstream workflow cannot pass poisoned artifacts, outputs, or cache state into a privileged downstream workflow.[3][4]
- Treat PR titles, PR bodies, issue text, branch names, commit messages, workflow inputs, checked-out files, and downloaded artifacts as untrusted when constructing shell commands or generated scripts.[4][10]
- Prefer GitHub-hosted runners for public repositories and any workflow influenced by forks or outside contributors.[4][5][6]
- If self-hosted runners are required, isolate them from sensitive networks, avoid long-lived credentials on the host, and prefer ephemeral or just-in-time runners so each job starts clean.[4][6]
- Use OIDC trust conditions that restrict repository, ref, environment, or reusable workflow context instead of issuing broad cloud credentials.[7]
- Pin external actions to full SHAs and verify that the pinned commit belongs to the intended upstream repository.[4][8][9]
- Restrict which actions and reusable workflows can run through repository, organization, or enterprise policy when you need stronger supply-chain controls.[8][9][15]
- Require review or approval for fork PR workflows according to your threat model, and inspect workflow-file changes before approving runs from outside contributors.[3][8][15][16]
- Mask generated secrets and other sensitive runtime values with `::add-mask::` when they are not stored in GitHub Secrets.[11]
- Set explicit artifact `retention-days` and avoid uploading credentials, environment dumps, or oversized debug bundles.[12]
- Generate and verify artifact attestations for binaries, packages, container images, or other release artifacts that downstream users should be able to validate.[13][14]

## Do / Don't

### Do

- Do keep `GITHUB_TOKEN` permissions explicit, narrow, and close to the job that needs them.[1][2]
- Do separate metadata-only automation from workflows that build or execute repository code.[3][4]
- Do use GitHub-hosted runners for fork and contributor traffic unless you have a deliberate isolation model for self-hosted infrastructure.[4][5][6]
- Do replace long-lived cloud keys with OIDC federation and tightly scoped trust conditions when your provider supports it.[7]
- Do pin third-party actions to verified full SHAs and periodically review their source and update path.[4][8][9]
- Do mask runtime secrets and keep artifact retention to the minimum practical window.[11][12]
- Do generate attestations for release artifacts that consumers or admission policies are expected to verify.[13][14]
- Do use repository, organization, or enterprise policy to narrow the allowed action surface and tighten fork-workflow approval rules where appropriate.[8][9][15][16]

### Don't

- Don't run tests, builds, or arbitrary pull request code under `pull_request_target` just to gain write permissions or secret access.[3][4]
- Don't treat `workflow_run` as harmless glue if it consumes artifacts, outputs, or caches from untrusted upstream workflows.[3][4]
- Don't assume self-hosted runners are clean between jobs or safe for untrusted public PRs by default.[6]
- Don't grant broad workflow-level write scopes to every job when only one job mutates repository state.[1][2]
- Don't trust branch names, issue text, PR descriptions, or workflow inputs inside shell scripts without defensive handling.[4][10]
- Don't rely on floating tags alone when immutability matters; GitHub documents full SHAs as the only immutable action reference.[4][8]
- Don't store long-lived cloud credentials in repository secrets when OIDC federation is available.[7][11]
- Don't upload secrets, credential files, raw environment snapshots, or unnecessary debug archives as artifacts.[11][12]
- Don't approve fork PR workflows casually, especially when the change set touches `.github/workflows/` or other execution paths.[15][16]

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

Use `pull_request_target` only when the workflow needs base-repository context for safe metadata tasks such as labeling, comments, or triage. Do not check out the pull request head, execute pull request code, restore attacker-influenced cache entries, or consume untrusted artifacts in that context.[3][4]

### Treat `workflow_run` As A Trust Boundary

Use `workflow_run` for carefully reviewed follow-up automation, not as an automatic bridge from untrusted CI into privileged release or deployment logic. If the upstream workflow handled attacker-controlled code or inputs, review any artifacts, outputs, caches, or conclusions before a downstream privileged workflow consumes them.[3][4]

## Practical Review Questions

1. Does this workflow execute contributor-controlled code or interpolate contributor-controlled text into shell commands?
2. If yes, is it running on `pull_request` with only the minimum read-level access it needs?
3. Does any downstream `workflow_run` job consume artifacts, caches, or outputs from an untrusted workflow while holding secrets or write scopes?
4. Are all third-party actions pinned to full commit SHAs from the expected upstream repository?
5. Can OIDC replace any stored cloud key or long-lived deployment credential?
6. Could a runner, cache, log, artifact, or downstream workflow leak sensitive data or amplify untrusted state?
7. Are fork PR workflow approval rules strong enough for the repository's exposure level?
8. Are artifact attestations generated and verified for the release artifacts that matter?
9. Are repository, organization, or enterprise policies enforcing the same action restrictions maintainers expect authors to follow manually?

## Primary Sources

1. GitHub Docs, "Workflow syntax for GitHub Actions"  
   https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
2. GitHub Docs, "Use `GITHUB_TOKEN` for authentication in workflows"  
   https://docs.github.com/en/actions/security-guides/automatic-token-authentication
3. GitHub Docs, "Events that trigger workflows"  
   https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
4. GitHub Docs, "Secure use reference"  
   https://docs.github.com/en/actions/reference/security
5. GitHub Docs, "GitHub-hosted runners"  
   https://docs.github.com/en/actions/concepts/runners/github-hosted-runners
6. GitHub Docs, "Self-hosted runners"  
   https://docs.github.com/en/actions/concepts/runners/self-hosted-runners
7. GitHub Docs, "OpenID Connect reference"  
   https://docs.github.com/en/actions/reference/security/oidc
8. GitHub Docs, "Managing GitHub Actions settings for a repository"  
   https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
9. GitHub Docs, "Disabling or limiting GitHub Actions for your organization"  
   https://docs.github.com/en/organizations/managing-organization-settings/disabling-or-limiting-github-actions-for-your-organization
10. GitHub Docs, "Script injections"  
    https://docs.github.com/en/actions/concepts/security/script-injections
11. GitHub Docs, "Using secrets in GitHub Actions"  
    https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
12. GitHub Docs, "Store and share data with workflow artifacts"  
    https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow
13. GitHub Docs, "Artifact attestations"  
    https://docs.github.com/en/actions/concepts/security/artifact-attestations
14. GitHub Docs, "Using artifact attestations to establish provenance for builds"  
    https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations
15. GitHub Docs, "Approving workflow runs from forks"  
    https://docs.github.com/en/actions/how-tos/manage-workflow-runs/approve-runs-from-forks
16. GitHub Docs, "Controlling changes from forks to workflows in public repositories"  
    https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
