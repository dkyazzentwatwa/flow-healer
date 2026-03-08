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


def test_merge_pr(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/pulls/123/merge"
        assert method == "PUT"
        assert body == {"merge_method": "squash"}
        return {"merged": True}

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    ok = tracker.merge_pr(pr_number=123)
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


def test_issue_has_label_matches_case_insensitive(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/issues/123"
        assert method == "GET"
        return {
            "number": 123,
            "state": "open",
            "title": "Case test",
            "body": "details",
            "labels": [{"name": "Healer:Ready"}, {"name": "healer:PR-APPROVED"}],
        }

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    assert tracker.issue_has_label(issue_id="123", label="healer:ready")
    assert tracker.issue_has_label(issue_id="123", label="HEALER:PR-APPROVED")


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


def test_close_pr_posts_comment_and_closes(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"
    calls: list[tuple[str, str, object | None]] = []

    def fake_request(path: str, *, method: str = "GET", body=None):
        calls.append((path, method, body))
        if path == "/repos/owner/repo/issues/77/comments":
            assert method == "POST"
            assert body == {"body": "closing note"}
            return {"id": 1001}
        if path == "/repos/owner/repo/pulls/77":
            assert method == "PATCH"
            assert body == {"state": "closed"}
            return {"number": 77, "state": "closed"}
        raise AssertionError(path)

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    ok = tracker.close_pr(pr_number=77, comment="closing note")
    assert ok is True
    assert calls == [
        ("/repos/owner/repo/issues/77/comments", "POST", {"body": "closing note"}),
        ("/repos/owner/repo/pulls/77", "PATCH", {"state": "closed"}),
    ]


def test_delete_branch(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/git/refs/heads/healer%2Fissue-123"
        assert method == "DELETE"
        assert body is None
        return {}

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    ok = tracker.delete_branch(branch="healer/issue-123")
    assert ok is True


def test_get_pr_details_includes_updated_at(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/pulls/42"
        assert method == "GET"
        return {
            "number": 42,
            "state": "open",
            "html_url": "https://github.com/owner/repo/pull/42",
            "mergeable_state": "clean",
            "updated_at": "2026-03-07T12:00:00Z",
            "user": {"login": "alice"},
            "head": {"ref": "healer/issue-42"},
        }

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    details = tracker.get_pr_details(pr_number=42)
    assert details is not None
    assert details.updated_at == "2026-03-07T12:00:00Z"


def test_find_pr_for_issue_uses_all_prs_and_detects_merged(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/pulls?state=all&per_page=100"
        assert method == "GET"
        return [
            {
                "number": 11,
                "title": "healer: fix issue #123 - older",
                "state": "closed",
                "html_url": "https://github.com/owner/repo/pull/11",
                "merged_at": "2026-03-06T00:00:00Z",
            },
            {
                "number": 12,
                "title": "healer: fix issue #123 - latest",
                "state": "closed",
                "html_url": "https://github.com/owner/repo/pull/12",
                "merged_at": "2026-03-07T00:00:00Z",
            },
        ]

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    pr = tracker.find_pr_for_issue(issue_id="123")
    assert pr is not None
    assert pr.number == 12
    assert pr.state == "merged"
    assert pr.html_url == "https://github.com/owner/repo/pull/12"


def test_pr_state_from_payload_prefers_closed_over_dirty():
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")

    assert (
        tracker._pr_state_from_payload(
            {
                "state": "closed",
                "mergeable_state": "dirty",
            }
        )
        == "closed"
    )


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


def test_open_or_update_pr_sets_auth_error_when_token_missing():
    tracker = GitHubHealerTracker(repo_path=Path("."), token="")
    tracker.repo_slug = "owner/repo"

    pr = tracker.open_or_update_pr(
        issue_id="123",
        branch="healer/issue-123",
        title="healer: fix issue #123",
        body="body",
        base="main",
    )

    assert pr is None
    error_class, error_reason = tracker.get_last_error()
    assert error_class == "github_auth_missing"
    assert "GITHUB_TOKEN" in error_reason


def test_open_or_update_pr_rejects_payload_without_number(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        if method == "GET":
            return []
        assert method == "POST"
        return {"message": "Validation Failed"}

    monkeypatch.setattr(tracker, "_request_json", fake_request)

    pr = tracker.open_or_update_pr(
        issue_id="123",
        branch="healer/issue-123",
        title="healer: fix issue #123",
        body="body",
        base="main",
    )

    assert pr is None
    error_class, error_reason = tracker.get_last_error()
    assert error_class == "github_api_error"
    assert "Validation Failed" in error_reason
