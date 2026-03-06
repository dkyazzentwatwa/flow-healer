# Usage

## Core Commands

| Command | Purpose |
| --- | --- |
| `flow-healer doctor [--repo NAME]` | Validate environment, git, Docker, and API setup. |
| `flow-healer status [--repo NAME]` | Show current issue counts, state, and recent attempts. |
| `flow-healer start [--repo NAME] [--once]` | Run the healing loop continuously or for a single pass. |
| `flow-healer pause [--repo NAME]` | Pause autonomous processing for a repo. |
| `flow-healer resume [--repo NAME]` | Resume autonomous processing. |
| `flow-healer scan [--repo NAME] [--dry-run]` | Scan repo for breakage patterns and optionally create issues. |

## The Healing Lifecycle

### 1. Triggering a Fix
Flow Healer monitors issues with the `healer:ready` label (configurable). It only processes issues from trusted actors or those explicitly labeled.

### 2. Autonomous Processing
Once claimed, Flow Healer:
- Creates an isolated git worktree.
- Analyzes the issue and predicts which files need locking.
- Generates a fix via the AI connector.
- Runs tests in a Docker container.
- Verifies the fix doesn't introduce regressions.

### 3. Review and Approval
If `pr_actions_require_approval` is enabled, Flow Healer waits for the `healer:pr-approved` label before opening or updating a Pull Request.

### 4. PR Feedback Loop
If a human reviewer leaves a comment on the generated PR, Flow Healer:
1. Detects the new comment.
2. Ingests the comment text as `feedback_context`.
3. Re-queues the issue for a new healing attempt.
4. Applies the feedback to improve the fix in the next iteration.

## Example Workflow

~~~bash
# 1. Setup environment
export GITHUB_TOKEN=your_token_here

# 2. Check health
flow-healer doctor --repo my-project

# 3. Start processing a single issue labeled 'healer:ready'
flow-healer start --repo my-project --once

# 4. Monitor progress
flow-healer status --repo my-project
~~~

## Scanner Behavior

The scanner identifies deterministic breakage patterns (e.g., failed CI, linting errors). If `scan_enable_issue_creation` is set to `true`, it will create deduplicated GitHub issues for these findings, labeled with `kind:scan` and `healer:ready` to trigger the healing loop automatically.

> **Note**: Labels can be customized per-repo in the configuration to match your project's workflow. Standardizing labels across repos is recommended for consistent multi-repo orchestration.
