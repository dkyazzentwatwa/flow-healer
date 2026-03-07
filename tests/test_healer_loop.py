from types import SimpleNamespace
from unittest.mock import MagicMock

from flow_healer.healer_loop import AutonomousHealerLoop
from flow_healer.healer_tracker import HealerIssue
from flow_healer.store import SQLiteStore


class _HealthyConnector:
    def ensure_started(self) -> None:
        return None

    def health_snapshot(self):
        return {
            "available": True,
            "configured_command": "codex",
            "resolved_command": "/opt/homebrew/bin/codex",
            "availability_reason": "",
            "last_health_error": "",
        }


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
        healer_pr_required_label=overrides.get("healer_pr_required_label", "healer:pr-approved"),
        healer_trusted_actors=[],
        healer_scan_enable_issue_creation=overrides.get("healer_scan_enable_issue_creation", False),
        healer_scan_poll_interval_seconds=overrides.get("healer_scan_poll_interval_seconds", 180.0),
        repo_name=overrides.get("repo_name", "demo"),
        healer_retry_budget=overrides.get("healer_retry_budget", 2),
        healer_backoff_initial_seconds=overrides.get("healer_backoff_initial_seconds", 60),
        healer_backoff_max_seconds=overrides.get("healer_backoff_max_seconds", 3600),
        healer_circuit_breaker_window=overrides.get("healer_circuit_breaker_window", 4),
        healer_circuit_breaker_failure_rate=overrides.get("healer_circuit_breaker_failure_rate", 0.5),
        healer_circuit_breaker_cooldown_seconds=overrides.get("healer_circuit_breaker_cooldown_seconds", 900),
    )
    loop = AutonomousHealerLoop.__new__(AutonomousHealerLoop)
    loop.settings = settings
    loop.store = store
    loop.tracker = MagicMock()
    loop.tracker.viewer_login.return_value = "healer-service"
    loop.tracker.repo_slug = "owner/repo"
    loop.worker_id = overrides.get("worker_id", "worker-a")
    loop.dispatcher = MagicMock()
    loop.dispatcher.lease_seconds = overrides.get("lease_seconds", 180)
    loop.dispatcher.max_active_issues = overrides.get("max_active_issues", 1)
    loop.scanner = MagicMock()
    loop.reconciler = MagicMock()
    loop._last_scan_started_at = overrides.get("_last_scan_started_at", 0.0)
    loop.connector = overrides.get("connector", _HealthyConnector())
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


def test_ingest_pr_feedback_ignores_bot_comments(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="4021",
        repo="owner/repo",
        title="Issue 4021",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="4021", state="pr_open", pr_number=124)

    loop = _make_loop(store)
    loop.tracker.list_pr_comments.return_value = [
        {
            "id": 2002,
            "body": "Automated summary from a bot",
            "author": "coderabbitai[bot]",
            "created_at": "2026-03-06T01:00:00Z",
        }
    ]
    loop.tracker.list_pr_reviews.return_value = []
    loop.tracker.list_pr_review_comments.return_value = []

    loop._ingest_pr_feedback()

    issue = store.get_healer_issue("4021")
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert issue["feedback_context"] == ""
    assert issue["last_issue_comment_id"] == 2002


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


def test_ingest_ready_issues_requeues_archived_issue(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="503",
        repo="owner/repo",
        title="Issue 503",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="503", state="archived", pr_state="closed")

    loop = _make_loop(store)
    loop.tracker.list_ready_issues.return_value = [
        HealerIssue(
            issue_id="503",
            repo="owner/repo",
            title="Issue 503 reopened",
            body="new body",
            author="alice",
            labels=["healer:ready"],
            priority=5,
            html_url="https://example.test/issues/503",
        )
    ]

    loop._ingest_ready_issues()

    issue = store.get_healer_issue("503")
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["pr_state"] == ""
    loop.tracker.add_issue_reaction.assert_not_called()


def test_process_claimed_issue_archives_closed_remote_issue(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="504",
        repo="owner/repo",
        title="Issue 504",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store)
    loop.tracker.get_issue.return_value = {"issue_id": "504", "state": "closed", "labels": ["healer:ready"]}

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("504")
    assert issue is not None
    assert issue["state"] == "archived"
    assert issue["pr_state"] == "closed"
    assert issue["lease_owner"] in ("", None)


def test_claim_is_actionable_is_case_insensitive_for_labels(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    loop.tracker.get_issue.return_value = {
        "issue_id": "504",
        "state": "open",
        "labels": ["Healer:READY"],
    }

    issue = HealerIssue(
        issue_id="504",
        repo="owner/repo",
        title="Case-sensitive label issue",
        body="",
        author="alice",
        labels=["Healer:READY"],
        priority=5,
        html_url="https://example.test/issues/504",
    )

    assert loop._claim_is_actionable(issue) is True


def test_resume_approved_pending_pr_requeues_issue(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="601",
        repo="owner/repo",
        title="Issue 601",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="601", state="pr_pending_approval")

    loop = _make_loop(store)
    loop.tracker.issue_has_label.return_value = True

    resumed = loop._resume_approved_pending_prs()

    issue = store.get_healer_issue("601")
    assert resumed == 1
    assert issue is not None
    assert issue["state"] == "queued"
    loop.tracker.add_issue_comment.assert_called_once()


def test_reconcile_pr_outcomes_closes_merged_issue(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="602",
        repo="owner/repo",
        title="Issue 602",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="602", state="pr_open", pr_number=126, pr_state="open")

    loop = _make_loop(store)
    loop.tracker.get_pr_state.return_value = "merged"
    loop.tracker.close_issue.return_value = True

    resolved = loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("602")
    assert resolved == 1
    assert issue is not None
    assert issue["state"] == "resolved"
    assert issue["pr_state"] == "merged"
    loop.tracker.close_issue.assert_called_once_with(issue_id="602")
    loop.tracker.add_issue_comment.assert_called_once()


def test_maybe_run_scan_respects_interval(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()

    loop = _make_loop(
        store,
        healer_scan_enable_issue_creation=True,
        healer_scan_poll_interval_seconds=180.0,
    )
    loop.scanner.run_scan.return_value = {"created_issues": [], "findings_over_threshold": 0}

    first = loop._maybe_run_scan()
    second = loop._maybe_run_scan()

    assert first == {"created_issues": [], "findings_over_threshold": 0}
    assert second is None
    loop.scanner.run_scan.assert_called_once_with(dry_run=False)


def test_store_claim_next_issue_respects_active_budget(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="701",
        repo="owner/repo",
        title="Issue 701",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.upsert_healer_issue(
        issue_id="702",
        repo="owner/repo",
        title="Issue 702",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=6,
    )

    first = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert first is not None

    blocked = store.claim_next_healer_issue(worker_id="worker-b", lease_seconds=180, max_active_issues=1)
    assert blocked is None


def test_lease_heartbeat_renews_issue_lease(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)

    class _StopAfterOne:
        def __init__(self) -> None:
            self.calls = 0

        def wait(self, _interval: float) -> bool:
            self.calls += 1
            return self.calls > 1

    stop_event = _StopAfterOne()
    loop.store = MagicMock()
    loop.dispatcher = MagicMock()
    loop.dispatcher.lease_seconds = 180
    loop.worker_id = "worker-a"
    loop.store.renew_healer_issue_lease.return_value = True

    loop._lease_heartbeat("703", stop_event)  # type: ignore[arg-type]

    loop.store.renew_healer_issue_lease.assert_called_once_with(
        issue_id="703",
        worker_id="worker-a",
        lease_seconds=180,
    )


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

    state = loop._backoff_or_fail(
        issue_id="301",
        attempt_no=1,
        failure_class="tests_failed",
        failure_reason="pytest failed",
    )
    issue = store.get_healer_issue("301")
    assert issue is not None
    assert state == "queued"
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

    state = loop._backoff_or_fail(
        issue_id="302",
        attempt_no=2,
        failure_class="verifier_failed",
        failure_reason="verification rejected",
    )
    issue = store.get_healer_issue("302")
    assert issue is not None
    assert state == "failed"
    assert issue["state"] == "failed"
    assert issue["last_failure_class"] == "verifier_failed"


def test_backoff_or_fail_connector_failure_does_not_exhaust_retry_budget(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="303",
        repo="owner/repo",
        title="Issue 303",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store, healer_retry_budget=1, healer_backoff_initial_seconds=60)

    state = loop._backoff_or_fail(
        issue_id="303",
        attempt_no=5,
        failure_class="connector_unavailable",
        failure_reason="ConnectorUnavailable: codex missing",
    )
    issue = store.get_healer_issue("303")
    assert issue is not None
    assert state == "queued"
    assert issue["state"] == "queued"
    assert issue["last_failure_class"] == "connector_unavailable"
    assert issue["backoff_until"]


def test_backoff_or_fail_no_patch_does_not_exhaust_retry_budget(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="304",
        repo="owner/repo",
        title="Issue 304",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store, healer_retry_budget=1, healer_backoff_initial_seconds=60)

    state = loop._backoff_or_fail(
        issue_id="304",
        attempt_no=7,
        failure_class="no_patch",
        failure_reason="Proposer did not return a unified diff block.",
    )
    issue = store.get_healer_issue("304")
    assert issue is not None
    assert state == "queued"
    assert issue["state"] == "queued"
    assert issue["last_failure_class"] == "no_patch"
    assert issue["backoff_until"]
    loop.tracker.add_issue_comment.assert_called()


def test_backoff_or_fail_no_code_diff_does_not_exhaust_retry_budget(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="305",
        repo="owner/repo",
        title="Issue 305",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store, healer_retry_budget=1, healer_backoff_initial_seconds=60)

    state = loop._backoff_or_fail(
        issue_id="305",
        attempt_no=4,
        failure_class="no_code_diff",
        failure_reason="Code-change task produced only docs/artifact edits.",
    )
    issue = store.get_healer_issue("305")
    assert issue is not None
    assert state == "queued"
    assert issue["state"] == "queued"
    assert issue["last_failure_class"] == "no_code_diff"
    assert issue["backoff_until"]
    loop.tracker.add_issue_comment.assert_called()


def test_tick_once_skips_claim_when_connector_unavailable(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    connector = MagicMock()
    connector.ensure_started.return_value = None
    connector.health_snapshot.return_value = {
        "available": False,
        "configured_command": "codex",
        "resolved_command": "",
        "availability_reason": "Unable to resolve Codex command.",
        "last_health_error": "Unable to resolve Codex command.",
    }

    loop = _make_loop(store, connector=connector)
    loop._tick_once()

    loop.dispatcher.claim_next_issue.assert_not_called()
    assert store.get_state("healer_connector_available") == "false"


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


def test_circuit_breaker_ignores_interrupted_attempts(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="1000",
        repo="owner/repo",
        title="Issue 1000",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store, healer_circuit_breaker_window=5, healer_circuit_breaker_failure_rate=0.5)

    for idx, state in enumerate(["failed", "interrupted", "pr_open", "failed", "resolved"]):
        store.create_healer_attempt(
            attempt_id=f"hb_{idx}",
            issue_id="1000",
            attempt_no=idx + 1,
            state="running",
            prediction_source="path_level",
            predicted_lock_set=["repo:*"],
        )
        store.finish_healer_attempt(
            attempt_id=f"hb_{idx}",
            state=state,
            actual_diff_set=[],
            test_summary={},
            verifier_summary={},
        )

    assert loop._circuit_breaker_open() is False


def test_circuit_breaker_closes_after_cooldown(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="1001",
        repo="owner/repo",
        title="Issue 1001",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(
        store,
        healer_circuit_breaker_window=5,
        healer_circuit_breaker_failure_rate=0.5,
        healer_circuit_breaker_cooldown_seconds=60,
    )

    for idx, state in enumerate(["failed", "failed", "pr_open", "failed", "failed"]):
        store.create_healer_attempt(
            attempt_id=f"hc_{idx}",
            issue_id="1001",
            attempt_no=idx + 1,
            state="running",
            prediction_source="path_level",
            predicted_lock_set=["repo:*"],
        )
        store.finish_healer_attempt(
            attempt_id=f"hc_{idx}",
            state=state,
            actual_diff_set=[],
            test_summary={},
            verifier_summary={},
        )

    conn = store._connect()
    with store._lock:
        conn.execute(
            "UPDATE healer_attempts SET finished_at = datetime('now', '-10 minutes') WHERE issue_id = ?",
            ("1001",),
        )
        conn.commit()

    status = loop._circuit_breaker_status()
    assert status.open is False
    assert status.cooldown_remaining_seconds == 0


def test_cleanup_workspace_clears_failed_run_paths(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="1002",
        repo="owner/repo",
        title="Issue 1002",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    workspace = tmp_path / "workspaces" / "issue-1002"
    workspace.mkdir(parents=True)
    store.set_healer_issue_state(
        issue_id="1002",
        state="failed",
        workspace_path=str(workspace),
        branch_name="healer/issue-1002",
    )

    loop = _make_loop(store)
    loop.workspace_manager = MagicMock()

    loop._cleanup_workspace(issue_id="1002", state="failed", workspace_path=workspace)

    issue = store.get_healer_issue("1002")
    assert issue is not None
    assert issue["workspace_path"] == ""
    assert issue["branch_name"] == ""
    loop.workspace_manager.remove_workspace.assert_called_once_with(workspace_path=workspace)


def test_cleanup_workspace_preserves_requeued_state(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="1003",
        repo="owner/repo",
        title="Issue 1003",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    workspace = tmp_path / "workspaces" / "issue-1003"
    workspace.mkdir(parents=True)
    store.set_healer_issue_state(
        issue_id="1003",
        state="queued",
        workspace_path=str(workspace),
        branch_name="healer/issue-1003",
    )

    loop = _make_loop(store)
    loop.workspace_manager = MagicMock()

    loop._cleanup_workspace(issue_id="1003", state="queued", workspace_path=workspace)

    issue = store.get_healer_issue("1003")
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["workspace_path"] == ""
    assert issue["branch_name"] == ""
    loop.workspace_manager.remove_workspace.assert_called_once_with(workspace_path=workspace)
