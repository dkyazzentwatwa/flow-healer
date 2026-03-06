# Installation

## Requirements

- Python 3.11 or newer
- Docker available on the host
- A GitHub token with `repo` scope

## Local Setup

~~~bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
~~~

## Configuration

Start from `config.example.yaml` and copy it into `~/.flow-healer/config.yaml`.

~~~yaml
service:
  github_token_env: GITHUB_TOKEN
  github_api_base_url: https://api.github.com
  poll_interval_seconds: 60
  state_root: ~/.flow-healer
  connector_command: codex
  connector_model: ""
  connector_timeout_seconds: 300
~~~

## Validation

~~~bash
flow-healer doctor
pytest -q
~~~

- [TODO: Verify] Whether non-Docker fallback test gates should be documented for constrained environments
