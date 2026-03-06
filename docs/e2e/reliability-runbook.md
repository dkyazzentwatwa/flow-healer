# E2E Reliability Runbook

## Purpose
Use this runbook to validate the E2E reliability artifact pack before handoff or retest sign-off.

## Operator Sequence
1. Open [reliability-retest-plan.md](reliability-retest-plan.md) and confirm the scope still matches the current issue.
2. Open [reliability-risk-review.md](reliability-risk-review.md) and verify the review contains exactly 8 numbered findings.
3. Check that each finding includes severity, impact, and recommendation text.
4. Open [../README.md](../README.md) and confirm the `E2E Reliability` section links to all three E2E docs.
5. Re-open each linked file once to confirm there are no broken relative paths.
6. Finish by confirming the completion check in the retest plan reports 4 files changed and 8 findings.

## Quick Failure Checks
- Missing file: recreate the required doc before review continues.
- Broken link: correct the relative path and re-open the target.
- Wrong findings count: add or remove entries until the review returns to exactly 8 items.
- Incomplete finding fields: add severity, impact, or recommendation before sign-off.

## Cross-Links
- Retest plan: [reliability-retest-plan.md](reliability-retest-plan.md)
- Risk review: [reliability-risk-review.md](reliability-risk-review.md)
