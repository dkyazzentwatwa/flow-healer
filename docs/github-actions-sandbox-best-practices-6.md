# GitHub Actions Sandbox Best Practices (Research Stress 6)

This note summarizes current GitHub primary-source guidance for keeping GitHub Actions workflows inside a safer trust boundary. The consistent themes across GitHub Docs are to minimize `GITHUB_TOKEN` permissions, keep untrusted pull request code out of privileged triggers, prefer ephemeral or GitHub-hosted execution environments, replace long-lived cloud secrets with OIDC, pin external actions immutably, and treat artifacts, caches, logs, and downstream workflows as part of the sandbox surface.

## Current Best-Practice Summary

- Declare explicit `permissions` and keep them narrow. GitHub documents that when you specify any individual permission, every unspecified permission is set to `none`.[1][2]
- Run contributor-controlled code on `pull_request`, not `pull_request_target`. GitHub warns that `pull_request_target` runs in the base branch context and can expose secrets, write privileges, or trusted cache state if mixed with untrusted code.[3][4][5]
- Treat `workflow_run` as a trust boundary. GitHub documents that downstream workflows triggered this way can access artifacts from the earlier workflow and may run with broader privileges, so untrusted upstream output must not be consumed blindly.[3][4]
- Prefer GitHub-hosted runners for workflows reachable by forks or outside contributors. GitHub-hosted runners start each job in a fresh environment, while self-hosted runners require you to engineer your own isolation and cleanup model.[4][6][7]
- Prefer OIDC federation over stored cloud keys. Grant `id-token: write` only to the workflow or job that needs it, and scope cloud trust conditions to the exact repository, ref, environment, or reusable-workflow context that should be able to assume that identity.[8]
- Pin third-party actions to a full commit SHA. GitHub documents full-length SHA pinning as the only immutable action reference and provides repository and organization policy controls to require it.[4][5][9][10]
- Treat workflow inputs and GitHub context fields as untrusted. GitHub explicitly calls out script injection risk from attacker-controlled values such as branch names, PR titles, issue bodies, and commit messages.[4][11]
- Keep logs, masks, artifacts, and retention tight. GitHub recommends masking sensitive runtime values that are not stored as secrets and using explicit artifact retention instead of leaving data around longer than necessary.[12][13]
- Use artifact attestations for release outputs or other high-value artifacts whose provenance should be verified by downstream consumers.[14][15]
- Use repository or organization Actions policy to restrict which actions and reusable workflows may run, require SHA pinning where possible, and tighten approval rules for fork-triggered workflows.[5][9][10][16]

## Checklist

- Start each workflow or job from `permissions: {}` or a minimal read baseline such as `contents: read`, then add only the scopes that are required.[1][2]
- Move write permissions to the narrowest possible job instead of giving the entire workflow write access.[1][2]
- Use `pull_request` for build, test, lint, and any job that checks out or executes pull request code.[3]
- Reserve `pull_request_target` for metadata-only tasks such as labeling, triage, or comments, and do not combine it with checkout of fork code, untrusted artifact downloads, or cache writes derived from attacker-controlled input.[3][4][5]
- Review every `workflow_run` design to make sure a low-trust workflow cannot feed poisoned artifacts, outputs, or cache state into a higher-trust follow-up workflow.[3][4]
- Treat PR text, issue text, branch names, workflow inputs, commit messages, checked-out files, and downloaded artifacts as untrusted when assembling shell commands or generated scripts.[4][11]
- Prefer GitHub-hosted runners for public repositories and for workflows that can be reached by forks or unknown contributors.[4][6]
- If self-hosted runners are required, isolate them from sensitive networks, avoid persistent secrets on the host, and prefer ephemeral or just-in-time runner patterns so each job starts from a clean instance.[4][7]
- Use OIDC trust conditions that restrict repository, ref, environment, or reusable-workflow context instead of issuing broad cloud credentials.[8]
- Pin external actions to full SHAs and verify that the pinned commit belongs to the intended upstream repository.[4][5][9][10]
- Restrict allowed actions and reusable workflows with repository or organization policy when supply-chain control matters.[5][9][10]
- Require maintainer review for fork-triggered workflows when your threat model calls for it, and inspect `.github/workflows/` changes before approving runs.[5][16]
- Mask generated secrets and other sensitive runtime values with `::add-mask::` when they are not stored in GitHub Secrets.[12]
- Set explicit artifact `retention-days` and avoid uploading credentials, environment dumps, or oversized debug bundles.[13]
- Generate and verify artifact attestations for binaries, packages, or container images whose provenance should be checked later.[14][15]

## Do / Don't

### Do

- Do keep `GITHUB_TOKEN` permissions explicit, narrow, and close to the job that needs them.[1][2]
- Do separate metadata-only automation from workflows that build or execute repository code.[3][4]
- Do prefer GitHub-hosted runners for contributor-driven workloads unless you have a deliberate isolation model for self-hosted infrastructure.[4][6][7]
- Do replace long-lived cloud credentials with OIDC federation and tightly scoped trust rules when your provider supports it.[8]
- Do pin third-party actions to verified full SHAs and periodically review the upstream source you are trusting.[4][5][9][10]
- Do mask runtime secrets, keep artifact retention short, and upload only the files another workflow or maintainer actually needs.[12][13]
- Do use artifact attestations for released artifacts that downstream users, admission policy, or deployment systems are expected to verify.[14][15]
- Do use repository or organization policy settings to narrow the allowed action surface and require stronger defaults where governance matters.[5][9][10][16]

### Don't

- Don't run tests, builds, or arbitrary PR code under `pull_request_target` to gain secrets or write permissions.[3][4][5]
- Don't treat `workflow_run` as harmless glue if it consumes artifacts, outputs, or cache state from an untrusted upstream run.[3][4]
- Don't assume self-hosted runners are clean between jobs or safe for untrusted public forks by default.[4][7]
- Don't give workflow-wide write scopes to every job when only one job mutates repository state.[1][2]
- Don't trust branch names, PR titles, issue text, commit messages, or workflow inputs inside inline shell without defensive handling.[4][11]
- Don't rely on floating tags alone when immutability matters; GitHub documents full SHAs as the only immutable action reference.[4][5][9]
- Don't store long-lived cloud credentials in repository secrets when OIDC federation is available.[8][12]
- Don't upload secrets, credential files, raw environment snapshots, or unnecessary debug archives as artifacts.[12][13]
- Don't approve fork workflow runs casually, especially when the proposed changes modify `.github/workflows/` or other execution paths.[16]

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

Use `pull_request_target` only when the workflow needs trusted base-repository context for safe metadata tasks such as labeling, triage, or comments. Do not check out the pull request head, execute pull request code, restore attacker-influenced cache entries, or download untrusted artifacts in that context.[3][4][5]

### Treat `workflow_run` As Privileged Follow-Up Automation

Use `workflow_run` only when the downstream workflow has a clearly reviewed contract for any artifact, output, or cache data it consumes. If the upstream workflow handled attacker-controlled code or inputs, the downstream workflow should validate or ignore that data rather than implicitly trusting it.[3][4]

## Practical Review Questions

1. Does this workflow execute contributor-controlled code or interpolate contributor-controlled text into shell commands?
2. If yes, is it running on `pull_request` with only the minimum read-level access it needs?
3. Does any downstream `workflow_run` job consume artifacts, caches, or outputs from a lower-trust workflow while holding secrets or write scopes?
4. Are all third-party actions pinned to full commit SHAs from the expected upstream repository?
5. Can OIDC replace any stored cloud key or long-lived deployment credential?
6. Could a runner, cache, artifact, log, or downstream workflow leak or amplify untrusted state?
7. Are artifact retention and masking settings tight enough to avoid leaving sensitive material behind?
8. Are repository or organization policies enforcing the same restrictions maintainers expect authors to follow manually?

## Primary Sources

1. GitHub Docs, "Workflow syntax for GitHub Actions"  
   https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions
2. GitHub Docs, "Use `GITHUB_TOKEN` for authentication in workflows"  
   https://docs.github.com/en/actions/tutorials/authenticate-with-github_token
3. GitHub Docs, "Events that trigger workflows"  
   https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
4. GitHub Docs, "Secure use reference"  
   https://docs.github.com/en/actions/reference/security/secure-use
5. GitHub Docs, "Managing GitHub Actions settings for a repository"  
   https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
6. GitHub Docs, "Using GitHub-hosted runners"  
   https://docs.github.com/en/actions/how-tos/using-github-hosted-runners/using-github-hosted-runners
7. GitHub Docs, "Self-hosted runners"  
   https://docs.github.com/en/actions/concepts/runners/self-hosted-runners
8. GitHub Docs, "OpenID Connect reference"  
   https://docs.github.com/en/actions/reference/security/oidc
9. GitHub Docs, "Disabling or limiting GitHub Actions for your organization"  
   https://docs.github.com/en/organizations/managing-organization-settings/disabling-or-limiting-github-actions-for-your-organization
10. GitHub Docs, "Enforcing policies for GitHub Actions in your enterprise"  
    https://docs.github.com/enterprise-cloud@latest/admin/enforcing-policies/enforcing-policies-for-your-enterprise/enforcing-policies-for-github-actions-in-your-enterprise
11. GitHub Docs, "Script injections"  
    https://docs.github.com/en/actions/concepts/security/script-injections
12. GitHub Docs, "Using secrets in GitHub Actions"  
    https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
13. GitHub Docs, "Store and share data with workflow artifacts"  
    https://docs.github.com/en/actions/tutorials/store-and-share-data
14. GitHub Docs, "Artifact attestations"  
    https://docs.github.com/en/actions/concepts/security/artifact-attestations
15. GitHub Docs, "Using artifact attestations to establish provenance for builds"  
    https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations
16. GitHub Docs, "Approving workflow runs from forks"  
    https://docs.github.com/en/actions/how-tos/manage-workflow-runs/approve-runs-from-forks
