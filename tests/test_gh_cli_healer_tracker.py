from __future__ import annotations

import json
import subprocess
from pathlib import Path

from flow_healer.gh_cli_healer_tracker import GhCliHealerTracker


def test_gh_cli_tracker_get_issue_uses_gh_api(monkeypatch) -> None:
    tracker = GhCliHealerTracker(repo_path=Path("."), gh_command="gh")
    tracker.repo_slug = "owner/repo"

    def fake_run(cmd, *, check, capture_output, text, timeout, input=None):
        assert cmd == ["gh", "api", "repos/owner/repo/issues/123"]
        assert check is False
        assert capture_output is True
        assert text is True
        assert timeout == 15
        assert input is None
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=json.dumps(
                {
                    "number": 123,
                    "state": "open",
                    "title": "Issue title",
                    "body": "Issue body",
                    "labels": [{"name": "healer:ready"}],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("flow_healer.gh_cli_healer_tracker.subprocess.run", fake_run)

    issue = tracker.get_issue(issue_id="123")

    assert issue == {
        "issue_id": "123",
        "state": "open",
        "title": "Issue title",
        "body": "Issue body",
        "labels": ["healer:ready"],
    }


def test_gh_cli_tracker_find_pr_for_issue_uses_graphql(monkeypatch) -> None:
    tracker = GhCliHealerTracker(repo_path=Path("."), gh_command="gh")
    tracker.repo_slug = "owner/repo"

    def fake_run(cmd, *, check, capture_output, text, timeout, input=None):
        assert cmd[:3] == ["gh", "api", "graphql"]
        assert "--method" not in cmd
        assert "-F" in cmd
        query_index = cmd.index("-f")
        assert cmd[query_index + 1].startswith("query=")
        assert "first=10" in cmd
        assert 'q=repo:owner/repo is:pr "issue #123"' in cmd
        assert check is False
        assert capture_output is True
        assert text is True
        assert timeout == 15
        assert input is None
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=json.dumps(
                {
                    "data": {
                        "search": {
                            "nodes": [
                                {
                                    "number": 17,
                                    "state": "OPEN",
                                    "url": "https://github.com/owner/repo/pull/17",
                                    "updatedAt": "2026-03-14T03:00:00Z",
                                    "mergedAt": None,
                                    "closedAt": None,
                                }
                            ]
                        }
                    }
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("flow_healer.gh_cli_healer_tracker.subprocess.run", fake_run)

    pr = tracker.find_pr_for_issue(issue_id="123")

    assert pr is not None
    assert pr.number == 17
    assert pr.state == "open"
    assert pr.html_url == "https://github.com/owner/repo/pull/17"
