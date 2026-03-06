from __future__ import annotations

from pathlib import Path

from flow_healer.healer_tracker import GitHubHealerTracker


def test_find_open_issue_by_fingerprint_uses_search(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert method == "GET"
        assert "/search/issues?q=" in path
        return {
            "items": [
                {
                    "number": 12,
                    "html_url": "https://github.com/owner/repo/issues/12",
                    "title": "sample",
                }
            ]
        }

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    result = tracker.find_open_issue_by_fingerprint("abc123")
    assert result is not None
    assert result["number"] == 12


def test_create_issue_posts_payload(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/issues"
        assert method == "POST"
        assert body is not None
        assert body["labels"] == ["healer:ready", "kind:scan"]
        return {"number": 77, "html_url": "https://github.com/owner/repo/issues/77", "state": "open"}

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    issue = tracker.create_issue(
        title="Test failing: tests/test_a.py::test_x",
        body="details",
        labels=["healer:ready", "kind:scan"],
    )
    assert issue is not None
    assert issue["number"] == 77


def test_add_pr_comment(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/issues/123/comments"
        assert method == "POST"
        assert body == {"body": "LGTM!"}
        return {"id": 999}

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    ok = tracker.add_pr_comment(pr_number=123, body="LGTM!")
    assert ok is True


def test_list_pr_comments(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/issues/123/comments"
        return [
            {
                "id": 1,
                "body": "Comment 1",
                "user": {"login": "user1"},
                "created_at": "2023-01-01T00:00:00Z"
            }
        ]

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    comments = tracker.list_pr_comments(pr_number=123)
    assert len(comments) == 1
    assert comments[0]["author"] == "user1"
    assert comments[0]["body"] == "Comment 1"
