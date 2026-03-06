# Usage

## Core Commands

~~~bash
flow-healer doctor
flow-healer status
flow-healer start --once
flow-healer scan --dry-run
~~~

## Typical Loop

1. Create or label a GitHub issue that Flow Healer should process.
2. Run a single pass with `flow-healer start --once` or let the service poll continuously.
3. Review the generated PR and leave comments if follow-up work is needed.

## Example

~~~bash
export GITHUB_TOKEN=your_token_here
flow-healer doctor --repo demo
flow-healer start --repo demo --once
flow-healer status --repo demo
~~~

## Scanner Behavior

The scanner can create deduplicated GitHub issues for deterministic findings when enabled in repo config.

- [TODO: Verify] Whether issue labels should be standardized across all managed repos
