# GitHub Actions Sandbox Best Practices

This repo already starts from a relatively safe baseline: CI and PR verification run on GitHub-hosted runners, and most workflows declare top-level `permissions`. The main hardening work left is to keep permissions narrowly scoped, avoid untrusted-code triggers, prefer short-lived credentials, and pin third-party actions immutably.

## Concise Checklist

- Set `GITHUB_TOKEN` permissions to the minimum required for each workflow or job. When a workflow declares any explicit permission, every unspecified scope becomes `none`. Source: GitHub workflow syntax docs.
- Default read-only workflows to `contents: read`, then add write scopes only to the specific jobs that need them. Source: GitHub workflow syntax docs and secure-use guidance.
- Keep running untrusted pull request code on `pull_request`, not `pull_request_target`. Use `pull_request_target` only for metadata-only tasks such as labeling or commenting, and never for building or executing PR code. Source: GitHub events docs.
- Prefer GitHub-hosted runners for repository automation that can be influenced by contributors. GitHub documents these as clean, isolated VMs, while self-hosted runners do not guarantee a clean instance per job and can be persistently compromised by untrusted code. Source: GitHub secure-use guidance and runner docs.
- If cloud access is ever needed, use OIDC with `id-token: write` on the specific job instead of storing long-lived cloud credentials in GitHub secrets. OIDC exchanges job identity for short-lived cloud tokens. Source: GitHub OIDC docs.
- Pin third-party actions to a full-length commit SHA where practical. GitHub documents full-length SHA pinning as the only immutable way to reference an action release. Source: GitHub secure-use guidance.
- Treat logs and artifacts as potentially sensitive outputs. Mask non-secret sensitive values with `::add-mask::`, review logs after changes, rotate secrets if anything leaks, and keep artifact retention short. Source: GitHub secrets and artifacts docs.
- Scope secret access tightly. Use environment protection and required reviewers for sensitive deployment secrets if this repo later adds release or deploy workflows. Source: GitHub secure-use and secrets docs.

## Recommended Baseline Policy For This Repo

The current workflow set is small and operationally simple:

- `.github/workflows/ci.yml` and `.github/workflows/03-verify-pr.yml` are test workflows on GitHub-hosted runners and already use `contents: read`.
- `.github/workflows/01-triage.yml`, `.github/workflows/02-run-agent.yml`, and `.github/workflows/04-merge-close.yml` perform issue and PR automation and legitimately need some write access.
- The repo currently uses `pull_request`, `push`, `issues`, `issue_comment`, `schedule`, and `workflow_dispatch`. It does not currently rely on `pull_request_target`, which is a good default for a repo that executes automation in response to contributor activity.

Recommended policy:

1. Keep `pull_request` as the trigger for validation workflows.
2. Do not introduce `pull_request_target` for any workflow that checks out, builds, tests, or otherwise executes code from a pull request.
3. Keep GitHub-hosted runners as the default runner class for all contributor-influenced workflows.
4. Keep workflow-level permissions minimal, then increase permissions at the job level only where a job must comment, label, merge, or push changes.
5. Add `id-token: write` only to jobs that actively perform OIDC federation, and do not mix that permission into unrelated jobs.
6. Pin `actions/checkout`, `actions/setup-python`, and any future third-party actions to full commit SHAs after verifying the upstream commit provenance.
7. If artifacts are added later, upload only non-secret outputs, set explicit `retention-days`, and avoid cross-workflow artifact downloads unless a token and trust boundary are clearly justified.

## Repo-Specific Starting Point

If maintainers want a practical baseline without redesigning the workflows, this is the safest default:

```yaml
permissions:
  contents: read
```

Then expand only where needed:

- `01-triage.yml`: keep `issues: write` and `contents: read`.
- `02-run-agent.yml`: keep write access only for the issue and PR operations the worker actually performs. Review whether `contents: write` can be reduced to a narrower job split if future edits separate repo mutation from issue commenting.
- `04-merge-close.yml`: keep `contents: write`, `pull-requests: write`, and `issues: write`, because this workflow merges PRs and closes issues.
- Any future cloud-deploy job: add `id-token: write` only on that deploy job and move cloud authentication to OIDC rather than repository secrets.

## Do / Don't

### Do

- Do set explicit `permissions` on every workflow.
- Do assume contributor-controlled inputs include issue titles, issue comments, PR titles, PR bodies, branch names, artifacts, and any checked-out PR code.
- Do keep automation that only labels, comments, or triages separate from automation that executes repository code.
- Do review logs after changing secret-handling or authentication steps.
- Do mask generated sensitive values that are not stored as GitHub secrets.
- Do use short artifact retention windows when artifacts are necessary.
- Do keep self-hosted runners out of contributor-triggered workflows unless there is a very deliberate isolation story.

### Don't

- Don't switch CI or PR verification from `pull_request` to `pull_request_target` just to gain secret or write-token access.
- Don't grant `write-all` or broad workflow-level write scopes when only one job needs elevated access.
- Don't store long-lived cloud keys in repository or organization secrets if the provider supports OIDC federation.
- Don't assume secret redaction is perfect for transformed or structured values such as JSON blobs, base64 variants, or generated tokens.
- Don't upload secrets, credential files, or raw debug bundles as workflow artifacts.
- Don't rely on major-tag action references alone if you need strong supply-chain immutability.
- Don't run untrusted PR code on self-hosted runners that can reach sensitive networks, metadata services, or long-lived credentials.

## Suggested Follow-Up Changes

These are the highest-value hardening steps for the current repo layout:

1. Pin `actions/checkout@v4` and `actions/setup-python@v5` to verified full commit SHAs in every workflow.
2. Review whether `02-run-agent.yml` can move from workflow-level write scopes to job-level permissions or a split between read-only preparation and write-capable mutation steps.
3. Keep `pull_request_target` out of the repo unless a future metadata-only workflow has a clearly documented reason to use it.
4. If artifacts are introduced for debugging or packaging, set explicit `retention-days` and document what data is safe to upload.

## References

- GitHub Docs, Workflow syntax for GitHub Actions (`permissions` behavior and scope calculation): https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- GitHub Docs, Secure use reference (least privilege, secret handling, third-party action pinning, self-hosted runner risks): https://docs.github.com/en/actions/reference/security/secure-use
- GitHub Docs, OpenID Connect (short-lived cloud credentials for a single job): https://docs.github.com/en/actions/concepts/security/openid-connect
- GitHub Docs, Events that trigger workflows (`pull_request` and `pull_request_target` behavior and warnings): https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- GitHub Docs, GitHub-hosted runners: https://docs.github.com/en/actions/concepts/runners/github-hosted-runners
- GitHub Docs, Self-hosted runners: https://docs.github.com/en/actions/concepts/runners/self-hosted-runners
- GitHub Docs, Using secrets in GitHub Actions (`::add-mask::`, fork secret behavior, secret review): https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- GitHub Docs, Store and share data with workflow artifacts (`retention-days`, download behavior): https://docs.github.com/en/actions/tutorials/store-and-share-data
