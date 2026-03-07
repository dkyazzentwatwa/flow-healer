---
name: flow-healer-connector-debug
description: Run this skill when Flow Healer triage points to connector or patch generation failures and the user wants a deterministic connector-focused debug pass. Use for requests like "debug the connector", "why did the proposer emit no patch", "validate the verifier payload", or "compare proposer and verifier output contracts".
---

# Flow Healer Connector Debug

Use this skill when `flow-healer-triage` reports `connector_or_patch_generation`.

## Inputs

- Connector command and arguments from the active repo config
- A fixed prompt fixture or the failing issue prompt
- The failing patch, verifier payload, or attempt logs when available

## Outputs

- Connector invocation summary
- Patch-contract findings
- Verifier-contract findings
- Recommended next action

## Key Output Fields

- Connector command resolution
- Diff fence validity
- Empty diff detection
- Verifier JSON validity
- Patch-apply outcome

## Success Criteria

- The operator can say whether the connector command resolves correctly.
- The operator can identify whether the failure is caused by empty output, malformed diff fences, invalid verifier JSON, or patch-apply failure.
- The operator can compare proposer and verifier outputs without guessing which contract broke first.

## Failure Handling

- Stop and repair command resolution before deeper debugging if the connector binary or wrapper path is invalid.
- Stop and capture the raw output before retrying if the connector emits an empty or malformed patch.
- Escalate after evidence capture when the connector appears healthy but the proposer or verifier contract still breaks.

## Workflow

1. Validate connector command resolution from the repo config and local environment.
2. Rerun the connector against a fixed prompt fixture or the failing issue prompt.
3. Detect empty diff output and malformed diff fences before attempting to apply a patch.
4. Validate any verifier payload as JSON and confirm the expected verdict fields are present.
5. Reproduce patch application and record the exact failure if `git apply` or downstream patch parsing fails.
6. Compare proposer and verifier contracts to determine which stage first diverged from the expected format.

## Next Step

- Return to `flow-healer-triage` with the connector evidence if the root cause is still ambiguous.
- Hand off to the proposer/verifier implementation owner when the broken contract is isolated.
- Rerun `flow-healer-local-validation` or `flow-healer-preflight` after the connector fix lands, depending on whether the failure is local-only or blocks live work.
