#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


DOCS = {
    "docs/README.md": """# Flow Healer Docs

Flow Healer is a Python CLI tool for autonomous GitHub maintenance. It watches issues, creates isolated worktrees, runs guarded fixes through an AI connector, verifies the result with pytest in Docker, and stores durable state in SQLite.

## Quick Start

~~~bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export GITHUB_TOKEN=your_token_here
flow-healer doctor
flow-healer start --once
~~~

## Doc Map

- [installation.md](installation.md): local environment setup and config
- [usage.md](usage.md): CLI flows and examples
- [architecture.md](architecture.md): control loop and module map
- [contributing.md](contributing.md): development and review expectations

## Notes

- Project type: CLI automation service
- Tech stack: Python 3.11+, SQLite, GitHub, Docker, pytest
- Target audience: repository maintainers and contributors
- [TODO: Verify] Whether future docs should include a dedicated operations runbook
""",
    "docs/installation.md": """# Installation

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
""",
    "docs/usage.md": """# Usage

## Core Commands

~~~bash
flow-healer doctor
flow-healer status
flow-healer start --once
flow-healer scan --dry-run
~~~
""",
    "docs/architecture.md": """# Architecture

~~~text
GitHub Issues / Repo Signals
            |
            v
   Flow Healer CLI + Service
            |
   Connector -> Docker Test Gate -> Verifier -> PR
~~~
""",
    "docs/contributing.md": """# Contributing

## Development

~~~bash
pytest
pytest tests/test_healer_loop.py -v
flow-healer scan --dry-run
~~~
""",
}


CONNECTOR_TEMPLATE = """#!/usr/bin/env python3
from __future__ import annotations

import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

DOCS = {docs_json}


def _new_file_diff(path: str, content: str) -> str:
    body = "".join(
        difflib.unified_diff(
            [],
            content.splitlines(keepends=True),
            fromfile=f"a/{{path}}",
            tofile=f"b/{{path}}",
            n=3,
        )
    )
    body = body.replace(f"--- a/{{path}}", "--- /dev/null", 1)
    digest = hashlib.sha1(content.encode("utf-8")).hexdigest()[:7]
    return f"diff --git a/{{path}} b/{{path}}\\nnew file mode 100644\\nindex 0000000..{{digest}}\\n{{body}}"


def _full_patch() -> str:
    chunks = [_new_file_diff(path, content) for path, content in DOCS.items()]
    return "```diff\\n" + "\\n".join(chunk.rstrip() for chunk in chunks if chunk.strip()) + "\\n```\\n"


def _find_followup_readme(repo_root: Path, prompt: str) -> Path:
    worktrees_root = repo_root / ".apple-flow-healer" / "worktrees"
    match = re.search(r"Issue #(\\d+):", prompt)
    issue_id = match.group(1) if match else ""
    candidates = []
    if issue_id and worktrees_root.exists():
        candidates.extend(sorted(worktrees_root.glob(f"issue-{{issue_id}}-*/docs/README.md")))
    if worktrees_root.exists():
        candidates.extend(sorted(worktrees_root.glob("*/docs/README.md")))
    if candidates:
        return candidates[0]
    return repo_root / "docs" / "README.md"


def _followup_patch(repo_root: Path, prompt: str) -> str:
    path = _find_followup_readme(repo_root, prompt)
    before = path.read_text(encoding="utf-8")
    marker = "- [TODO: Verify] Whether future docs should include a dedicated operations runbook\\n"
    replacement = (
        marker
        + "- Review feedback addressed: this initial docs scaffold is intended as a starting point for iterative refinement.\\n"
    )
    after = before.replace(marker, replacement)
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="a/docs/README.md",
            tofile="b/docs/README.md",
            n=3,
        )
    )
    diff = "diff --git a/docs/README.md b/docs/README.md\\n" + diff
    return "```diff\\n" + diff.strip() + "\\n```\\n"


def main() -> int:
    prompt = sys.argv[-1] if len(sys.argv) > 1 else ""
    repo_root = Path.cwd()

    if "You are the verifier agent for autonomous code healing." in prompt:
        print(json.dumps({{"verdict": "pass", "summary": "Smoke verifier passed."}}))
        return 0

    if "You are 'Jules', a highly skilled software engineer performing a code review." in prompt:
        print("Added or refined low-risk documentation for the smoke run and kept the change narrowly scoped.")
        return 0

    if "### User Feedback for PR:" in prompt:
        print(_followup_patch(repo_root, prompt))
        return 0

    print(_full_patch())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


CONFIG_TEMPLATE = """service:
  github_token_env: GITHUB_TOKEN
  github_api_base_url: https://api.github.com
  poll_interval_seconds: 60
  state_root: {state_root}
  connector_command: {connector_command}
  connector_model: ""
  connector_timeout_seconds: 120

repos:
  - name: {repo_name}
    path: {repo_path}
    repo_slug: {repo_slug}
    default_branch: main
    enable_autonomous_healer: true
    healer_mode: guarded_pr
    issue_required_labels: []
    pr_actions_require_approval: false
    trusted_actors: []
    retry_budget: 2
    backoff_initial_seconds: 5
    backoff_max_seconds: 60
    enable_review: true
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a deterministic live smoke connector + config bundle")
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--repo-slug", required=True)
    parser.add_argument("--repo-name", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--template", choices=["docs_scaffold", "docs_followup_note"], default="docs_scaffold")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = hashlib.sha1(f"{args.repo_slug}:{args.repo_name}:{args.template}".encode("utf-8")).hexdigest()[:10]
    connector_path = output_dir / f"flow-healer-smoke-codex-{suffix}"
    config_path = output_dir / f"flow-healer-smoke-config-{suffix}.yaml"
    state_root = output_dir / f"state-{suffix}"

    connector_path.write_text(
        CONNECTOR_TEMPLATE.format(docs_json=json.dumps(DOCS, indent=2, ensure_ascii=True)),
        encoding="utf-8",
    )
    os.chmod(connector_path, 0o755)
    config_path.write_text(
        CONFIG_TEMPLATE.format(
            state_root=str(state_root),
            connector_command=str(connector_path),
            repo_name=args.repo_name,
            repo_path=str(Path(args.repo_path).expanduser().resolve()),
            repo_slug=args.repo_slug,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "template": args.template,
                "connector_path": str(connector_path),
                "config_path": str(config_path),
                "state_root": str(state_root),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
