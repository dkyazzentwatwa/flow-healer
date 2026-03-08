# GitHub Actions Sandbox Best Practices (Research Stress 20)

This note turns current GitHub primary-source guidance into a practical hardening checklist for repositories that run CI, automation, or contributor-triggered workflows. The main themes are consistent across GitHub Docs: reduce token scope, keep untrusted code away from privileged triggers, prefer short-lived credentials, pin external actions immutably, and treat runners, logs, and artifacts as part of the trust boundary.

## Current Best-Practice Summary

- Set explicit `permissions` on each workflow or job and keep them minimal. GitHub documents that if you specify any individual permission, all unspecified permissions become `none`.[1]
- Keep untrusted pull request code on the `pull_request` trigger. Use `pull_request_target` only for metadata-only tasks such as labeling or commenting, and do not check out or execute untrusted PR code there.[2][3]
- Prefer GitHub-hosted runners for contributor-influenced jobs. GitHub-hosted runners are provisioned as new VMs for jobs, while self-hosted runners do not guarantee a clean instance per job and can be persistently compromised by untrusted code.[3][4][5]
- Prefer OpenID Connect (OIDC) for cloud authentication instead of storing long-lived cloud credentials in secrets. Grant `id-token: write` only to the specific job that needs it.[6]
- Pin third-party actions to a full-length commit SHA. GitHub documents this as the only immutable way to reference an action release.[3][7]
- Mask sensitive runtime values that are not stored as GitHub secrets by using `::add-mask::VALUE`, and assume logs and artifacts can expose data if steps are careless.[8][9]
- Keep artifact and log retention as short as practical. GitHub notes repository defaults start at 90 days unless you reduce them.[9]
- Use repository, organization, or enterprise Actions policies to restrict which actions and reusable workflows can run, and consider requiring full-length SHA pinning where governance allows it.[7][10]

## Checklist

- Declare top-level `permissions` for every workflow, starting from `contents: read` or `{}` and adding only the scopes a job truly needs.[1]
- Move elevated permissions from workflow level to job level whenever only one job needs write access.[1][11]
- Use `pull_request` for build, test, lint, and any job that checks out or executes contributor-controlled code.[2]
- Reserve `pull_request_target` for trusted-repo-context tasks such as labeling, commenting, or routing, and never combine it with checkout of fork code, artifact reuse from untrusted runs, or cache writes derived from attacker-controlled input.[2][3]
- Treat issue titles, PR bodies, branch names, commit messages, workflow inputs, artifacts, and checked-out code as untrusted input when building shell commands or scripts.[3]
- Prefer GitHub-hosted runners for public repos and any workflow reachable by outside contributors.[3][4]
- If self-hosted runners are required, isolate them from sensitive networks, avoid exposing long-lived credentials, and prefer ephemeral or just-in-time runner patterns so each job starts clean.[3][5]
- For cloud auth, configure OIDC trust conditions that restrict repository, ref, environment, or event context instead of minting broad credentials.[6]
- Pin all external actions to full commit SHAs and review action source before adoption.[3][7]
- Restrict which actions and reusable workflows can run at the repository or org policy layer when you need stronger supply-chain controls.[10]
- Use environments and required reviewers for sensitive deployments or secrets so privileged operations need explicit approval.[3][8]
- Set explicit artifact `retention-days` and avoid uploading raw debug bundles, secret-bearing config, or credentials.[9]
- Review whether workflows can create or approve pull requests. GitHub documents this automation path as a potential risk if merges are not independently reviewed.[3][10]

## Do / Don't

### Do

- Do keep `GITHUB_TOKEN` permissions narrowly scoped and explicit.[1][8]
- Do split trusted metadata automation from untrusted-code execution so the privileged workflow never needs to run attacker-controlled code.[2][3]
- Do use GitHub-hosted runners for fork and contributor traffic unless you have a very deliberate isolation story for self-hosted infrastructure.[3][4]
- Do use OIDC with narrowly scoped claims for cloud access instead of long-lived static cloud keys.[6]
- Do pin third-party actions to verified full SHAs and periodically audit them.[3][7]
- Do mask generated tokens, one-time credentials, and other sensitive values even when they are not stored in `secrets`.[8]
- Do set short artifact retention and upload only the files another human or workflow genuinely needs.[9]
- Do use repository or organization policies to narrow the set of allowed actions and require immutable pinning where possible.[7][10]

### Don't

- Don't run build, test, or arbitrary repo code under `pull_request_target` just to gain write permissions or secret access.[2][3]
- Don't assume self-hosted runners are clean between jobs unless you have engineered that property yourself.[3][5]
- Don't hand broad workflow-level write scopes to all jobs when one job is the only writer.[1][11]
- Don't rely on action tags alone when you need immutability; tags can move, but a full commit SHA is fixed.[3]
- Don't store long-lived cloud credentials in repository secrets if the provider supports GitHub OIDC federation.[6][8]
- Don't upload secrets, credential files, environment dumps, or sensitive debug archives as artifacts.[8][9]
- Don't allow automation to create or approve pull requests without clear review controls and organizational intent.[3][10]

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

### Metadata-Only `pull_request_target` Usage

Use `pull_request_target` only when the workflow acts on pull request metadata in the base repository context, such as adding labels or posting a comment, and avoid checking out the PR head or consuming untrusted artifacts there.[2][3]

## Practical Review Questions

Before merging or enabling a workflow, ask:

1. Does this workflow execute any contributor-controlled code or shell input?
2. If yes, is it running on `pull_request` with only read-level access?
3. Does any job really need write scopes, or can the workflow default to `contents: read`?
4. Are third-party actions pinned to full SHAs?
5. If cloud auth is needed, can OIDC replace a stored credential?
6. Could a runner, log, cache, or artifact expose data that should stay private?
7. Are repository or org policies enforcing the same supply-chain rules we expect authors to follow manually?

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
