# Installation

## Requirements

- **Python 3.11** or newer.
- **Docker** available on the host (used for isolated test execution).
- **Git** installed and configured.
- A **GitHub Personal Access Token** with `repo` scope.

## Local Setup

~~~bash
git clone <your-repo-url>
cd flow-healer
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
~~~

## Configuration

Flow Healer looks for a configuration file at `~/.flow-healer/config.yaml` by default. Start by copying the provided example:

~~~bash
mkdir -p ~/.flow-healer
cp config.example.yaml ~/.flow-healer/config.yaml
~~~

### Service Settings

Global settings for the Flow Healer service.

| Key | Description | Default |
| --- | --- | --- |
| `github_token_env` | Environment variable name for the GitHub token. | `GITHUB_TOKEN` |
| `poll_interval_seconds` | How often to poll GitHub for changes. | `60` |
| `state_root` | Directory for SQLite state and worktrees. | `~/.flow-healer` |
| `connector_command` | The CLI command for the AI connector (e.g., `codex`). | `codex` |
| `connector_model` | Model name to pass to the connector. | `""` |
| `connector_timeout_seconds` | Max time allowed for AI generation. | `300` |

### Repo Settings

Configuration for each managed repository.

| Key | Description | Default |
| --- | --- | --- |
| `name` | Local identifier for the repo. | (Required) |
| `path` | Absolute path to the target repository. | (Required) |
| `repo_slug` | GitHub `owner/repo` slug. | `""` |
| `default_branch` | The branch to base fixes on and target for PRs. | `main` |
| `enable_autonomous_healer` | Enable the healing loop for this repo. | `true` |
| `healer_mode` | `guarded_pr` (verify before PR) or `autonomous_pr`. | `guarded_pr` |
| `issue_required_labels` | Labels required to trigger healing. | `["healer:ready"]` |
| `pr_actions_require_approval` | Require a label before opening/updating a PR. | `true` |
| `pr_required_label` | Label required if `pr_actions_require_approval` is true. | `["healer:pr-approved"]` |
| `max_concurrent_issues` | Max issues to process at once for this repo. | `1` |
| `retry_budget` | Max attempts per issue before giving up. | `2` |
| `learning_enabled` | Record and use lessons from past attempts. | `true` |
| `enable_review` | Generate an AI code review for the proposed PR. | `true` |

## Validation

Run the "doctor" command to verify your environment and configuration:

~~~bash
flow-healer doctor
~~~

You can also run the test suite:

~~~bash
pytest
~~~

> **Note**: Currently, Docker is the only supported test gate. Non-Docker fallbacks are not implemented to ensure a consistent and safe execution environment.
