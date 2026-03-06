from types import SimpleNamespace
from unittest.mock import MagicMock

from flow_healer.healer_loop import AutonomousHealerLoop
from flow_healer.healer_tracker import HealerIssue
from flow_healer.store import SQLiteStore


def _make_loop(store, **overrides):
    settings = SimpleNamespace(
        healer_repo_path="/tmp",
        enable_autonomous_healer=True,
        healer_poll_interval_seconds=60,
        healer_mode="guarded_pr",
        healer_max_concurrent_issues=1,
        healer_max_wall_clock_seconds_per_issue=300,
        healer_learning_enabled=True,
        healer_enable_review=overrides.get("healer_enable_review", True),
        healer_issue_required_labels=["healer:ready"],
        healer_trusted_actors=[],
        healer_retry_budget=overrides.get("healer_retry_budget", 2),
        healer_backoff_initial_seconds=overrides.get("healer_backoff_initial_seconds", 60),
        healer_backoff_max_seconds=overrides.get("healer_backoff_max_seconds", 3600),
        healer_circuit_breaker_window=overrides.get("healer_circuit_breaker_window", 4),
        healer_circuit_breaker_failure_rate=overrides.get("healer_circuit_breaker_failure_rate", 0.5),
    )
    loop = AutonomousHealerLoop.__new__(AutonomousHealerLoop)
    loop.settings = settings
    loop.store = store
    loop.tracker = MagicMock()
    loop.tracker.viewer_login.return_value = "healer-service"
    loop.tracker.repo_slug = "owner/repo"
    return loop


def test_ingest_pr_feedback_requeues_issue_for_new_external_feedback(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="401",
        repo="owner/repo",
        title="Issue 401",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="401", state="pr_open", pr_number=123)

    loop = _make_loop(store)
    loop.tracker.list_pr_comments.return_value = [
        {
            "id": 1001,
            "body": "Please fix this other thing too.",
            "author": "bob",
            "created_at": "2026-03-06T01:00:00Z",
        }
    ]
    loop.tracker.list_pr_reviews.return_value = []
    loop.tracker.list_pr_review_comments.return_value = []

    loop._ingest_pr_feedback()

    issue = store.get_healer_issue("401")
    assert issue is not None
    assert issue["state"] == "queued"
    assert "PR comment from @bob" in issue["feedback_context"]
    assert issue["last_issue_comment_id"] == 1001


def test_ingest_pr_feedback_ignores_healer_comments(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="402",
        repo="owner/repo",
        title="Issue 402",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="402", state="pr_open", pr_number=124)

    loop = _make_loop(store)
    loop.tracker.list_pr_comments.return_value = [
        {
            "id": 2001,
            "body": "Automated review from healer service",
            "author": "healer-service",
            "created_at": "2026-03-06T01:00:00Z",
        }
    ]
    loop.tracker.list_pr_reviews.return_value = []
    loop.tracker.list_pr_review_comments.return_value = []

    loop._ingest_pr_feedback()

    issue = store.get_healer_issue("402")
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert issue["feedback_context"] == ""
    assert issue["last_issue_comment_id"] == 2001


def test_ingest_ready_issues_adds_eyes_reaction_for_new_issue(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()

    loop = _make_loop(store)
    loop.tracker.list_ready_issues.return_value = [
        HealerIssue(
            issue_id="501",
            repo="owner/repo",
            title="Issue 501",
            body="",
            author="alice",
            labels=["healer:ready"],
            priority=5,
            html_url="https://example.test/issues/501",
        )
    ]

    loop._ingest_ready_issues()

    issue = store.get_healer_issue("501")
    assert issue is not None
    loop.tracker.add_issue_reaction.assert_called_once_with(issue_id="501", reaction="eyes")


def test_ingest_ready_issues_skips_duplicate_eyes_reaction(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="502",
        repo="owner/repo",
        title="Issue 502",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )

    loop = _make_loop(store)
    loop.tracker.list_ready_issues.return_value = [
        HealerIssue(
            issue_id="502",
            repo="owner/repo",
            title="Issue 502 updated",
            body="new body",
            author="alice",
            labels=["healer:ready"],
            priority=5,
            html_url="https://example.test/issues/502",
        )
    ]

    loop._ingest_ready_issues()

    loop.tracker.add_issue_reaction.assert_not_called()


def test_ingest_pr_feedback_collects_reviews_and_inline_comments(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="403",
        repo="owner/repo",
        title="Issue 403",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="403", state="pr_pending_approval", pr_number=125)

    loop = _make_loop(store)
    loop.tracker.list_pr_comments.return_value = []
    loop.tracker.list_pr_reviews.return_value = [
        {
            "id": 3001,
            "body": "Please cover the edge case.",
            "author": "reviewer",
            "state": "CHANGES_REQUESTED",
            "created_at": "2026-03-06T01:00:00Z",
        }
    ]
    loop.tracker.list_pr_review_comments.return_value = [
        {
            "id": 4001,
            "body": "This branch needs a nil guard.",
            "author": "reviewer",
            "path": "src/example.py",
            "created_at": "2026-03-06T01:01:00Z",
        }
    ]

    loop._ingest_pr_feedback()

    issue = store.get_healer_issue("403")
    assert issue is not None
    assert issue["state"] == "queued"
    assert "PR review (changes_requested) from @reviewer" in issue["feedback_context"]
    assert "Inline review comment on src/example.py from @reviewer" in issue["feedback_context"]
    assert issue["last_review_id"] == 3001
    assert issue["last_review_comment_id"] == 4001


def test_backoff_or_fail_requeues_before_retry_budget(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="301",
        repo="owner/repo",
        title="Issue 301",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store, healer_retry_budget=3)

    loop._backoff_or_fail(
        issue_id="301",
        attempt_no=1,
        failure_class="tests_failed",
        failure_reason="pytest failed",
    )
    issue = store.get_healer_issue("301")
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["last_failure_class"] == "tests_failed"
    assert issue["backoff_until"]
    assert "T" not in str(issue["backoff_until"])
    assert "+" not in str(issue["backoff_until"])


def test_backoff_or_fail_marks_failed_at_retry_budget(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="302",
        repo="owner/repo",
        title="Issue 302",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store, healer_retry_budget=2)

    loop._backoff_or_fail(
        issue_id="302",
        attempt_no=2,
        failure_class="verifier_failed",
        failure_reason="verification rejected",
    )
    issue = store.get_healer_issue("302")
    assert issue is not None
    assert issue["state"] == "failed"
    assert issue["last_failure_class"] == "verifier_failed"


def test_circuit_breaker_opens_when_failure_rate_exceeds_threshold(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="999",
        repo="owner/repo",
        title="Issue 999",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store, healer_circuit_breaker_window=5, healer_circuit_breaker_failure_rate=0.5)

    for idx, state in enumerate(["failed", "failed", "pr_open", "failed", "failed"]):
        store.create_healer_attempt(
            attempt_id=f"ha_{idx}",
            issue_id="999",
            attempt_no=idx + 1,
            state="running",
            prediction_source="path_level",
            predicted_lock_set=["repo:*"],
        )
        store.finish_healer_attempt(
            attempt_id=f"ha_{idx}",
            state=state,
            actual_diff_set=[],
            test_summary={},
            verifier_summary={},
        )

    assert loop._circuit_breaker_open() is True
