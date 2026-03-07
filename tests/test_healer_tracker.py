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


def test_add_issue_reaction(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/issues/123/reactions"
        assert method == "POST"
        assert body == {"content": "eyes"}
        return {"id": 555}

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    ok = tracker.add_issue_reaction(issue_id="123")
    assert ok is True


def test_add_issue_comment(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/issues/123/comments"
        assert method == "POST"
        assert body == {"body": "ready for approval"}
        return {"id": 556}

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    ok = tracker.add_issue_comment(issue_id="123", body="ready for approval")
    assert ok is True


def test_get_issue_returns_state_and_labels(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/issues/123"
        assert method == "GET"
        return {
            "number": 123,
            "state": "open",
            "title": "Test issue",
            "body": "details",
            "labels": [{"name": "healer:ready"}, {"name": "kind:scan"}],
        }

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    issue = tracker.get_issue(issue_id="123")
    assert issue is not None
    assert issue["issue_id"] == "123"
    assert issue["state"] == "open"
    assert issue["labels"] == ["healer:ready", "kind:scan"]


def test_get_issue_returns_none_for_missing_issue(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/issues/404"
        assert method == "GET"
        return {}

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    assert tracker.get_issue(issue_id="404") is None


def test_close_issue(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/issues/123"
        assert method == "PATCH"
        assert body == {"state": "closed"}
        return {"number": 123, "state": "closed"}

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    ok = tracker.close_issue(issue_id="123")
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
                "created_at": "2023-01-01T00:00:00Z",
            }
        ]

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    comments = tracker.list_pr_comments(pr_number=123)
    assert comments == [
        {
            "id": 1,
            "body": "Comment 1",
            "author": "user1",
            "created_at": "2023-01-01T00:00:00Z",
        }
    ]


def test_list_pr_reviews(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/pulls/123/reviews"
        return [
            {
                "id": 22,
                "body": "Please add coverage",
                "state": "CHANGES_REQUESTED",
                "user": {"login": "reviewer"},
                "submitted_at": "2023-01-01T00:00:00Z",
            }
        ]

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    reviews = tracker.list_pr_reviews(pr_number=123)
    assert reviews == [
        {
            "id": 22,
            "body": "Please add coverage",
            "author": "reviewer",
            "state": "CHANGES_REQUESTED",
            "created_at": "2023-01-01T00:00:00Z",
        }
    ]


def test_list_pr_review_comments(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/pulls/123/comments"
        return [
            {
                "id": 33,
                "body": "Guard this branch",
                "path": "src/example.py",
                "user": {"login": "reviewer"},
                "created_at": "2023-01-01T00:00:00Z",
            }
        ]

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    comments = tracker.list_pr_review_comments(pr_number=123)
    assert comments == [
        {
            "id": 33,
            "body": "Guard this branch",
            "author": "reviewer",
            "path": "src/example.py",
            "created_at": "2023-01-01T00:00:00Z",
        }
    ]


def test_viewer_login_uses_authenticated_user(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/user"
        return {"login": "healer-service"}

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    assert tracker.viewer_login() == "healer-service"
    assert tracker.viewer_login() == "healer-service"
