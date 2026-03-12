from __future__ import annotations

import io
import logging
from urllib.error import HTTPError
from pathlib import Path

from flow_healer.healer_tracker import GitHubHealerTracker


def test_list_ready_issues_paginates_and_sorts_oldest_first(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"
    calls: list[str] = []
    page_one: list[dict[str, object]] = []
    for issue_number in range(30, 49):
        page_one.append(
            {
                "number": issue_number,
                "title": f"Issue {issue_number}",
                "body": "details",
                "created_at": f"2026-03-09T02:{issue_number - 30:02d}:00Z",
                "updated_at": f"2026-03-09T02:{issue_number - 30:02d}:30Z",
                "html_url": f"https://github.com/owner/repo/issues/{issue_number}",
                "user": {"login": "alice"},
                "labels": [{"name": "healer:ready"}],
            }
        )
    page_one.append(
        {
            "number": 13,
            "title": "PR entry",
            "body": "skip me",
            "created_at": "2026-03-09T02:30:00Z",
            "updated_at": "2026-03-09T02:31:00Z",
            "html_url": "https://github.com/owner/repo/issues/13",
            "user": {"login": "alice"},
            "labels": [{"name": "healer:ready"}],
            "pull_request": {"url": "https://api.github.com/repos/owner/repo/pulls/13"},
        }
    )

    def fake_request(path: str, *, method: str = "GET", body=None):
        calls.append(path)
        assert method == "GET"
        if "page=1" in path:
            return page_one
        if "page=2" in path:
            return [
                {
                    "number": 11,
                    "title": "Older issue",
                    "body": "details",
                    "created_at": "2026-03-09T01:00:00Z",
                    "updated_at": "2026-03-09T01:10:00Z",
                    "html_url": "https://github.com/owner/repo/issues/11",
                    "user": {"login": "alice"},
                    "labels": [{"name": "healer:ready"}],
                }
            ]
        raise AssertionError(path)

    monkeypatch.setattr(tracker, "_request_json", fake_request)

    issues = tracker.list_ready_issues(required_labels=["healer:ready"], trusted_actors=[], limit=20)

    assert [issue.issue_id for issue in issues[:2]] == ["11", "30"]
    assert calls == [
        "/repos/owner/repo/issues?state=open&page=1&per_page=20&labels=healer%3Aready",
        "/repos/owner/repo/issues?state=open&page=2&per_page=20&labels=healer%3Aready",
    ]


def test_list_ready_issues_prefers_priority_before_age(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert method == "GET"
        return [
            {
                "number": 50,
                "title": "Older normal issue",
                "body": "",
                "created_at": "2026-03-09T01:00:00Z",
                "updated_at": "2026-03-09T01:05:00Z",
                "html_url": "https://github.com/owner/repo/issues/50",
                "user": {"login": "alice"},
                "labels": [{"name": "healer:ready"}],
            },
            {
                "number": 51,
                "title": "Priority issue",
                "body": "",
                "created_at": "2026-03-09T02:00:00Z",
                "updated_at": "2026-03-09T02:05:00Z",
                "html_url": "https://github.com/owner/repo/issues/51",
                "user": {"login": "alice"},
                "labels": [{"name": "healer:ready"}, {"name": "priority:p1"}],
            },
        ]

    monkeypatch.setattr(tracker, "_request_json", fake_request)

    issues = tracker.list_ready_issues(required_labels=["healer:ready"], trusted_actors=[], limit=2)

    assert [issue.issue_id for issue in issues] == ["51", "50"]


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


def test_add_issue_label(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/issues/123/labels"
        assert method == "POST"
        assert body == {"labels": ["agent:blocked"]}
        return [{"name": "healer:ready"}, {"name": "agent:blocked"}]

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    assert tracker.add_issue_label(issue_id="123", label="agent:blocked") is True


def test_remove_issue_label(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/issues/123/labels/agent%3Ablocked"
        assert method == "DELETE"
        assert body is None
        return [{"name": "healer:ready"}]

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    assert tracker.remove_issue_label(issue_id="123", label="agent:blocked") is True


def test_remove_issue_label_treats_missing_label_404_as_noop(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_urlopen(req, timeout=20):
        raise HTTPError(
            req.full_url,
            404,
            "Not Found",
            hdrs={},
            fp=io.BytesIO(
                b'{"message":"Label does not exist","documentation_url":"https://docs.github.com/rest/issues/labels#remove-a-label-from-an-issue","status":"404"}'
            ),
        )

    monkeypatch.setattr("flow_healer.healer_tracker.urlopen", fake_urlopen)

    assert tracker.remove_issue_label(issue_id="123", label="healer:done-code") is True


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


def test_find_pr_for_issue_uses_search_and_detects_merged(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"
    calls: list[str] = []

    def fake_request(path: str, *, method: str = "GET", body=None):
        calls.append(path)
        assert method == "GET"
        if path == '/search/issues?q=repo%3Aowner/repo%20is%3Apr%20%22issue%20%23123%22&per_page=20':
            return {
                "items": [
                    {
                        "number": 11,
                        "state": "closed",
                        "updated_at": "2026-03-06T00:00:00Z",
                        "html_url": "https://github.com/owner/repo/pull/11",
                    },
                    {
                        "number": 12,
                        "state": "closed",
                        "updated_at": "2026-03-07T00:00:00Z",
                        "html_url": "https://github.com/owner/repo/pull/12",
                    },
                ]
            }
        if path == "/repos/owner/repo/pulls/11":
            return {
                "number": 11,
                "state": "closed",
                "html_url": "https://github.com/owner/repo/pull/11",
                "merged_at": "2026-03-06T00:00:00Z",
                "mergeable_state": "clean",
                "updated_at": "2026-03-06T00:00:00Z",
                "user": {"login": "alice"},
                "head": {"ref": "healer/issue-11"},
            }
        if path == "/repos/owner/repo/pulls/12":
            return {
                "number": 12,
                "state": "closed",
                "html_url": "https://github.com/owner/repo/pull/12",
                "merged_at": "2026-03-07T00:00:00Z",
                "mergeable_state": "clean",
                "updated_at": "2026-03-07T00:00:00Z",
                "user": {"login": "alice"},
                "head": {"ref": "healer/issue-12"},
            }
        raise AssertionError(path)

    monkeypatch.setattr(tracker, "_request_json", fake_request)
    pr = tracker.find_pr_for_issue(issue_id="123")
    assert pr is not None
    assert pr.number == 12
    assert pr.state == "merged"
    assert pr.html_url == "https://github.com/owner/repo/pull/12"
    assert calls[0].startswith("/search/issues?q=")


def test_request_metrics_snapshot_aggregates_by_path(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_urlopen(req, timeout=20):
        class _Response:
            status = 200
            headers = {}

            def read(self):
                return b'{"number": 42, "state": "open", "html_url": "https://github.com/owner/repo/pull/42", "mergeable_state": "clean", "updated_at": "2026-03-07T12:00:00Z", "user": {"login": "alice"}, "head": {"ref": "healer/issue-42"}}'

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        return _Response()

    monkeypatch.setattr("flow_healer.healer_tracker.urlopen", fake_urlopen)

    assert tracker.get_pr_details(pr_number=42) is not None
    metrics = tracker.request_metrics_snapshot()

    assert metrics["counts"]["GET /repos/owner/repo/pulls/:id 200"] == 1


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


def test_open_or_update_pr_sets_auth_error_when_token_missing(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
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


def test_publish_artifact_files_creates_branch_and_returns_markdown_ready_urls(monkeypatch, tmp_path):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"
    screenshot = tmp_path / "failure.png"
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    console_log = tmp_path / "failure-console.log"
    console_log.write_text("console output", encoding="utf-8")
    calls: list[tuple[str, str, object]] = []

    def fake_request(path: str, *, method: str = "GET", body=None):
        calls.append((path, method, body))
        if path == "/repos/owner/repo/git/ref/heads/flow-healer-artifacts":
            assert method == "GET"
            return {}
        if path == "/repos/owner/repo/git/ref/heads/main":
            assert method == "GET"
            return {"object": {"sha": "base123"}}
        if path == "/repos/owner/repo/git/refs":
            assert method == "POST"
            assert body == {
                "ref": "refs/heads/flow-healer-artifacts",
                "sha": "base123",
            }
            return {"ref": "refs/heads/flow-healer-artifacts"}
        if path == "/repos/owner/repo/contents/flow-healer/evidence/issue-123/attempt-1/failure.png?ref=flow-healer-artifacts":
            assert method == "GET"
            return {}
        if path == "/repos/owner/repo/contents/flow-healer/evidence/issue-123/attempt-1/failure-console.log?ref=flow-healer-artifacts":
            assert method == "GET"
            return {}
        if path == "/repos/owner/repo/contents/flow-healer/evidence/issue-123/attempt-1/failure.png":
            assert method == "PUT"
            assert body is not None
            assert body["branch"] == "flow-healer-artifacts"
            assert body["message"] == "chore: publish flow-healer evidence for issue #123"
            assert body["content"] == "iVBORw0KGgpmYWtl"
            assert "sha" not in body
            return {"content": {"path": "flow-healer/evidence/issue-123/attempt-1/failure.png", "sha": "pngsha"}}
        if path == "/repos/owner/repo/contents/flow-healer/evidence/issue-123/attempt-1/failure-console.log":
            assert method == "PUT"
            assert body is not None
            assert body["branch"] == "flow-healer-artifacts"
            assert body["message"] == "chore: publish flow-healer evidence for issue #123"
            assert body["content"] == "Y29uc29sZSBvdXRwdXQ="
            assert "sha" not in body
            return {"content": {"path": "flow-healer/evidence/issue-123/attempt-1/failure-console.log", "sha": "logsha"}}
        raise AssertionError(path)

    monkeypatch.setattr(tracker, "_request_json", fake_request)

    published = tracker.publish_artifact_files(
        issue_id="123",
        files=[screenshot, console_log],
        branch="flow-healer-artifacts",
        source_branch="main",
        run_key="attempt-1",
    )

    assert [artifact.name for artifact in published] == ["failure.png", "failure-console.log"]
    assert published[0].remote_path == "flow-healer/evidence/issue-123/attempt-1/failure.png"
    assert published[0].html_url == "https://github.com/owner/repo/blob/flow-healer-artifacts/flow-healer/evidence/issue-123/attempt-1/failure.png"
    assert published[0].markdown_url == "https://raw.githubusercontent.com/owner/repo/flow-healer-artifacts/flow-healer/evidence/issue-123/attempt-1/failure.png"
    assert published[0].download_url == "https://raw.githubusercontent.com/owner/repo/flow-healer-artifacts/flow-healer/evidence/issue-123/attempt-1/failure.png"
    assert published[0].content_type == "image/png"
    assert published[1].content_type == "text/plain"


def test_artifact_content_type_prefers_stable_known_text_mappings(monkeypatch):
    monkeypatch.setattr("flow_healer.healer_tracker.mimetypes.guess_type", lambda filename: (None, None))

    assert GitHubHealerTracker._artifact_content_type("failure-console.log") == "text/plain"
    assert GitHubHealerTracker._artifact_content_type("network.jsonl") == "application/x-ndjson"
    assert GitHubHealerTracker._artifact_content_type("resolution.png") == "image/png"


def test_publish_artifact_files_updates_existing_artifact_sha(monkeypatch, tmp_path):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"
    screenshot = tmp_path / "resolution.png"
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\nupdated")
    calls: list[tuple[str, str, object]] = []

    def fake_request(path: str, *, method: str = "GET", body=None):
        calls.append((path, method, body))
        if path == "/repos/owner/repo/git/ref/heads/flow-healer-artifacts":
            assert method == "GET"
            return {"ref": "refs/heads/flow-healer-artifacts", "object": {"sha": "branchsha"}}
        if path == "/repos/owner/repo/contents/flow-healer/evidence/issue-123/latest/resolution.png?ref=flow-healer-artifacts":
            assert method == "GET"
            return {"sha": "existingsha"}
        if path == "/repos/owner/repo/contents/flow-healer/evidence/issue-123/latest/resolution.png":
            assert method == "PUT"
            assert body is not None
            assert body["branch"] == "flow-healer-artifacts"
            assert body["sha"] == "existingsha"
            return {"content": {"path": "flow-healer/evidence/issue-123/latest/resolution.png", "sha": "newsha"}}
        raise AssertionError(path)

    monkeypatch.setattr(tracker, "_request_json", fake_request)

    published = tracker.publish_artifact_files(
        issue_id="123",
        files=[screenshot],
        branch="flow-healer-artifacts",
    )

    assert len(published) == 1
    assert published[0].sha == "newsha"
    assert calls == [
        ("/repos/owner/repo/git/ref/heads/flow-healer-artifacts", "GET", None),
        (
            "/repos/owner/repo/contents/flow-healer/evidence/issue-123/latest/resolution.png?ref=flow-healer-artifacts",
            "GET",
            None,
        ),
        (
            "/repos/owner/repo/contents/flow-healer/evidence/issue-123/latest/resolution.png",
            "PUT",
            {
                "message": "chore: publish flow-healer evidence for issue #123",
                "content": "iVBORw0KGgp1cGRhdGVk",
                "branch": "flow-healer-artifacts",
                "sha": "existingsha",
            },
        ),
    ]


def test_publish_artifact_files_skips_unsupported_files(monkeypatch, tmp_path):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"
    artifact = tmp_path / "dump.sqlite"
    artifact.write_bytes(b"sqlite")
    calls: list[tuple[str, str, object]] = []

    def fake_request(path: str, *, method: str = "GET", body=None):
        calls.append((path, method, body))
        if path == "/repos/owner/repo/git/ref/heads/flow-healer-artifacts":
            assert method == "GET"
            return {"ref": "refs/heads/flow-healer-artifacts", "object": {"sha": "branchsha"}}
        raise AssertionError(path)

    monkeypatch.setattr(tracker, "_request_json", fake_request)

    published = tracker.publish_artifact_files(
        issue_id="123",
        files=[artifact],
        branch="flow-healer-artifacts",
    )

    assert published == []
    assert calls == [
        ("/repos/owner/repo/git/ref/heads/flow-healer-artifacts", "GET", None),
    ]


def test_request_json_suppresses_expected_artifact_publish_404_warnings(monkeypatch, caplog):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_urlopen(_req, timeout=20):
        raise HTTPError(
            url="https://api.github.com/repos/owner/repo/git/ref/heads/flow-healer-artifacts",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=io.BytesIO(b'{"message":"Not Found"}'),
        )

    monkeypatch.setattr("flow_healer.healer_tracker.urlopen", fake_urlopen)

    with caplog.at_level(logging.WARNING, logger="apple_flow.healer_tracker"):
        payload = tracker._request_json("/repos/owner/repo/git/ref/heads/flow-healer-artifacts")

    assert payload == {}
    assert "GitHub API GET /repos/owner/repo/git/ref/heads/flow-healer-artifacts failed" not in caplog.text


def test_get_pr_ci_status_summary_combines_check_runs_statuses_and_workflows(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"
    calls: list[str] = []

    def fake_request(path: str, *, method: str = "GET", body=None):
        calls.append(path)
        assert method == "GET"
        if path == "/repos/owner/repo/pulls/91":
            return {
                "number": 91,
                "state": "open",
                "html_url": "https://github.com/owner/repo/pull/91",
                "mergeable_state": "clean",
                "user": {"login": "alice"},
                "head": {"ref": "healer/issue-91", "sha": "abc123"},
                "updated_at": "2026-03-11T21:00:00Z",
            }
        if path == "/repos/owner/repo/commits/abc123/check-runs?per_page=100":
            return {
                "check_runs": [
                    {
                        "name": "unit",
                        "status": "completed",
                        "conclusion": "success",
                        "completed_at": "2026-03-11T21:03:00Z",
                    },
                    {
                        "name": "lint",
                        "status": "completed",
                        "conclusion": "failure",
                        "completed_at": "2026-03-11T21:04:00Z",
                    },
                    {
                        "name": "e2e",
                        "status": "in_progress",
                        "conclusion": None,
                    },
                ]
            }
        if path == "/repos/owner/repo/commits/abc123/status":
            return {
                "state": "pending",
                "statuses": [
                    {
                        "context": "status/lint",
                        "state": "failure",
                        "updated_at": "2026-03-11T21:04:30Z",
                    },
                    {
                        "context": "status/typecheck",
                        "state": "pending",
                        "updated_at": "2026-03-11T21:05:00Z",
                    },
                ],
            }
        if path == "/repos/owner/repo/actions/runs?head_sha=abc123&per_page=100":
            return {
                "workflow_runs": [
                    {
                        "name": "CI",
                        "status": "completed",
                        "conclusion": "failure",
                        "updated_at": "2026-03-11T21:06:00Z",
                    },
                    {
                        "name": "Preview",
                        "status": "queued",
                        "conclusion": None,
                        "updated_at": "2026-03-11T21:06:30Z",
                    },
                ]
            }
        raise AssertionError(path)

    monkeypatch.setattr(tracker, "_request_json", fake_request)

    summary = tracker.get_pr_ci_status_summary(pr_number=91)

    assert summary["head_sha"] == "abc123"
    assert summary["overall_state"] == "failure"
    assert summary["check_runs"]["failure"] == 1
    assert summary["check_runs"]["pending"] == 1
    assert summary["status_checks"]["failure"] == 1
    assert summary["status_checks"]["pending"] == 1
    assert summary["workflow_runs"]["failure"] == 1
    assert summary["workflow_runs"]["pending"] == 1
    assert summary["failure_buckets"] == ["lint", "unknown"]
    assert summary["pending_buckets"] == ["deploy_blocked", "test", "typecheck"]
    assert "lint" in summary["failing_contexts"]
    assert "CI" in summary["failing_contexts"]
    assert "e2e" in summary["pending_contexts"]
    assert "status/typecheck" in summary["pending_contexts"]
    assert {
        "source": "check_run",
        "name": "lint",
        "state": "failure",
        "bucket": "lint",
        "failure_kind": "deterministic_code",
        "updated_at": "2026-03-11T21:04:00Z",
    } in summary["failing_entries"]
    assert {
        "source": "workflow_run",
        "name": "CI",
        "state": "failure",
        "bucket": "unknown",
        "failure_kind": "unknown",
        "updated_at": "2026-03-11T21:06:00Z",
    } in summary["failing_entries"]
    assert {"source": "status_check", "name": "status/typecheck", "state": "pending", "bucket": "typecheck", "updated_at": "2026-03-11T21:05:00Z"} in summary["pending_entries"]
    assert {"source": "workflow_run", "name": "Preview", "state": "pending", "bucket": "deploy_blocked", "updated_at": "2026-03-11T21:06:30Z"} in summary["pending_entries"]
    assert summary["updated_at"] == "2026-03-11T21:06:30Z"
    assert calls == [
        "/repos/owner/repo/pulls/91",
        "/repos/owner/repo/commits/abc123/check-runs?per_page=100",
        "/repos/owner/repo/commits/abc123/status",
        "/repos/owner/repo/actions/runs?head_sha=abc123&per_page=100",
    ]


def test_get_pr_ci_status_summary_returns_empty_when_head_sha_missing(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert path == "/repos/owner/repo/pulls/91"
        return {
            "number": 91,
            "state": "open",
            "html_url": "https://github.com/owner/repo/pull/91",
            "mergeable_state": "clean",
            "user": {"login": "alice"},
            "head": {"ref": "healer/issue-91"},
            "updated_at": "2026-03-11T21:00:00Z",
        }

    monkeypatch.setattr(tracker, "_request_json", fake_request)

    assert tracker.get_pr_ci_status_summary(pr_number=91) == {}


def test_get_pr_ci_status_summary_distinguishes_transient_infra_failures(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"

    def fake_request(path: str, *, method: str = "GET", body=None):
        assert method == "GET"
        if path == "/repos/owner/repo/pulls/92":
            return {
                "number": 92,
                "state": "open",
                "html_url": "https://github.com/owner/repo/pull/92",
                "mergeable_state": "clean",
                "user": {"login": "alice"},
                "head": {"ref": "healer/issue-92", "sha": "def456"},
                "updated_at": "2026-03-11T22:00:00Z",
            }
        if path == "/repos/owner/repo/commits/def456/check-runs?per_page=100":
            return {
                "check_runs": [
                    {
                        "name": "runner bootstrap timeout",
                        "status": "completed",
                        "conclusion": "timed_out",
                        "completed_at": "2026-03-11T22:01:00Z",
                    },
                    {
                        "name": "lint",
                        "status": "completed",
                        "conclusion": "failure",
                        "completed_at": "2026-03-11T22:02:00Z",
                    },
                ]
            }
        if path == "/repos/owner/repo/commits/def456/status":
            return {"state": "pending", "statuses": []}
        if path == "/repos/owner/repo/actions/runs?head_sha=def456&per_page=100":
            return {"workflow_runs": []}
        raise AssertionError(path)

    monkeypatch.setattr(tracker, "_request_json", fake_request)

    summary = tracker.get_pr_ci_status_summary(pr_number=92)

    assert summary["transient_failure_contexts"] == ["runner bootstrap timeout"]
    assert summary["deterministic_failure_contexts"] == ["lint"]
    assert summary["transient_failure_entries"] == [
        {
            "source": "check_run",
            "name": "runner bootstrap timeout",
            "state": "failure",
            "bucket": "setup",
            "failure_kind": "transient_infra",
            "updated_at": "2026-03-11T22:01:00Z",
        }
    ]
    assert summary["deterministic_failure_entries"] == [
        {
            "source": "check_run",
            "name": "lint",
            "state": "failure",
            "bucket": "lint",
            "failure_kind": "deterministic_code",
            "updated_at": "2026-03-11T22:02:00Z",
        }
    ]


def test_open_or_update_pr_updates_existing_pull_request_body(monkeypatch):
    tracker = GitHubHealerTracker(repo_path=Path("."), token="x")
    tracker.repo_slug = "owner/repo"
    calls: list[tuple[str, str, object]] = []

    def fake_request(path: str, *, method: str = "GET", body=None):
        calls.append((path, method, body))
        if method == "GET":
            return [
                {
                    "number": 91,
                    "state": "open",
                    "html_url": "https://github.com/owner/repo/pull/91",
                }
            ]
        assert path == "/repos/owner/repo/pulls/91"
        assert method == "PATCH"
        assert body == {
            "title": "healer: fix issue #123",
            "body": "updated body",
            "base": "main",
        }
        return {
            "number": 91,
            "state": "open",
            "html_url": "https://github.com/owner/repo/pull/91",
        }

    monkeypatch.setattr(tracker, "_request_json", fake_request)

    pr = tracker.open_or_update_pr(
        issue_id="123",
        branch="healer/issue-123",
        title="healer: fix issue #123",
        body="updated body",
        base="main",
    )

    assert pr is not None
    assert pr.number == 91
    assert calls == [
        ("/repos/owner/repo/pulls?state=open&head=owner%3Ahealer/issue-123", "GET", None),
        (
            "/repos/owner/repo/pulls/91",
            "PATCH",
            {
                "title": "healer: fix issue #123",
                "body": "updated body",
                "base": "main",
            },
        ),
    ]
