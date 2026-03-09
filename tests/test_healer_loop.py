import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from flow_healer.healer_loop import (
    AutonomousHealerLoop,
    _FAILURE_CLASS_STRATEGY,
    _collect_targeted_tests,
    _sanitize_execution_root,
    _push_issue_branch,
)
from flow_healer.healer_preflight import PreflightReport
from flow_healer.healer_task_spec import HealerTaskSpec
from flow_healer.healer_tracker import HealerIssue, PullRequestDetails, PullRequestResult
from flow_healer.language_strategies import UnsupportedLanguageError
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
        healer_verifier_policy=overrides.get("healer_verifier_policy", "advisory"),
        healer_issue_required_labels=["healer:ready"],
        healer_pr_actions_require_approval=overrides.get("healer_pr_actions_require_approval", False),
        healer_pr_required_label=overrides.get("healer_pr_required_label", "healer:pr-approved"),
        healer_pr_auto_approve_clean=overrides.get("healer_pr_auto_approve_clean", True),
        healer_pr_auto_merge_clean=overrides.get("healer_pr_auto_merge_clean", True),
        healer_pr_merge_method=overrides.get("healer_pr_merge_method", "squash"),
        healer_default_branch=overrides.get("healer_default_branch", "main"),
        healer_trusted_actors=[],
        healer_scan_enable_issue_creation=overrides.get("healer_scan_enable_issue_creation", False),
        healer_scan_poll_interval_seconds=overrides.get("healer_scan_poll_interval_seconds", 180.0),
        repo_name=overrides.get("repo_name", "demo"),
        healer_retry_budget=overrides.get("healer_retry_budget", 2),
        healer_backoff_initial_seconds=overrides.get("healer_backoff_initial_seconds", 60),
        healer_backoff_max_seconds=overrides.get("healer_backoff_max_seconds", 3600),
        healer_auto_clean_generated_artifacts=overrides.get("healer_auto_clean_generated_artifacts", True),
        healer_failure_fingerprint_quarantine_threshold=overrides.get(
            "healer_failure_fingerprint_quarantine_threshold", 2
        ),
        healer_circuit_breaker_window=overrides.get("healer_circuit_breaker_window", 4),
        healer_circuit_breaker_failure_rate=overrides.get("healer_circuit_breaker_failure_rate", 0.5),
        healer_circuit_breaker_cooldown_seconds=overrides.get("healer_circuit_breaker_cooldown_seconds", 900),
        healer_stuck_pr_timeout_minutes=overrides.get("healer_stuck_pr_timeout_minutes", 60),
        healer_conflict_auto_requeue_enabled=overrides.get("healer_conflict_auto_requeue_enabled", True),
        healer_conflict_auto_requeue_max_attempts=overrides.get("healer_conflict_auto_requeue_max_attempts", 3),
        healer_conflict_requeue_debounce_seconds=overrides.get("healer_conflict_requeue_debounce_seconds", 0),
        healer_overlap_scope_queue_enabled=overrides.get("healer_overlap_scope_queue_enabled", True),
        healer_dedupe_enabled=overrides.get("healer_dedupe_enabled", True),
        healer_dedupe_close_duplicates=overrides.get("healer_dedupe_close_duplicates", True),
        healer_max_diff_files=overrides.get("healer_max_diff_files", 8),
        healer_max_diff_lines=overrides.get("healer_max_diff_lines", 400),
        healer_max_failed_tests_allowed=overrides.get("healer_max_failed_tests_allowed", 0),
    )
    loop = AutonomousHealerLoop.__new__(AutonomousHealerLoop)
    loop.settings = settings
    loop.store = store
    loop.repo_path = Path(settings.healer_repo_path)
    loop.tracker = MagicMock()
    loop.tracker.viewer_login.return_value = "healer-service"
    loop.tracker.repo_slug = "owner/repo"
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=123,
        state="open",
        html_url="https://example.test/pr/123",
        mergeable_state="clean",
        author="alice",
        head_ref="healer/issue-123",
        updated_at="2026-03-06T01:05:00Z",
    )
    loop.worker_id = overrides.get("worker_id", "worker-a")
    loop.dispatcher = MagicMock()
    loop.dispatcher.lease_seconds = overrides.get("lease_seconds", 180)
    loop.dispatcher.max_active_issues = overrides.get("max_active_issues", 1)
    loop.scanner = MagicMock()
    loop.reconciler = MagicMock()
    loop.memory = MagicMock()
    loop.verifier = MagicMock()
    loop.reviewer = MagicMock()
    loop.workspace_manager = MagicMock()
    loop.runner = MagicMock()
    loop.runner.resolve_execution.return_value = SimpleNamespace(
        language_effective="python",
        execution_root="",
    )
    loop.runner.validate_workspace.return_value = {"failed_tests": 0}
    loop.preflight = MagicMock()
    loop.preflight.probe_connector.return_value = (True, "")
    loop.preflight.refresh_all.return_value = []
    loop.preflight.ensure_language_ready.return_value = PreflightReport(
        language="python",
        execution_root="e2e-smoke/python",
        gate_mode="docker_only",
        status="ready",
        failure_class="",
        summary="ready",
        output_tail="",
        checked_at="2026-03-06 20:00:00",
        test_summary={"failed_tests": 0},
    )
    loop._last_scan_started_at = overrides.get("_last_scan_started_at", 0.0)
    loop.connector = overrides.get("connector", _HealthyConnector())
    loop.connector_routing_mode = overrides.get("connector_routing_mode", "single_backend")
    loop.code_connector_backend = overrides.get("code_connector_backend", "exec")
    loop.non_code_connector_backend = overrides.get("non_code_connector_backend", "app_server")
    loop.connectors_by_backend = overrides.get("connectors_by_backend", {"exec": loop.connector})
    loop.runners_by_backend = overrides.get("runners_by_backend", {"exec": loop.runner})
    loop.verifiers_by_backend = overrides.get("verifiers_by_backend", {"exec": loop.verifier})
    loop.reviewers_by_backend = overrides.get("reviewers_by_backend", {"exec": loop.reviewer})
    loop.preflight_by_backend = overrides.get("preflight_by_backend", {"exec": loop.preflight})
    return loop


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return proc


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True, text=True, timeout=60)
    _git(repo, "config", "user.name", "Flow Healer Tests")
    _git(repo, "config", "user.email", "tests@example.com")
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")


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
    assert issue["state"] == "pr_open"
    assert issue["pr_number"] == 123
    assert "PR comment from @bob" in issue["feedback_context"]
    assert issue["last_issue_comment_id"] == 1001
    assert issue["pr_last_seen_updated_at"] == "2026-03-06T01:05:00Z"


def test_collect_targeted_tests_prefers_explicit_paths(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_healer_loop.py").write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")

    targeted = _collect_targeted_tests(
        issue_body="Please run tests/test_explicit.py and fix the issue.",
        output_targets=["src/flow_healer/healer_loop.py"],
        workspace=tmp_path,
        language="python",
        execution_root="",
    )

    assert targeted == ["tests/test_explicit.py"]


def test_collect_targeted_tests_infers_python_test_from_output_target(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_healer_loop.py").write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")

    targeted = _collect_targeted_tests(
        issue_body="No explicit pytest target here.",
        output_targets=["src/flow_healer/healer_loop.py"],
        workspace=tmp_path,
        language="python",
        execution_root="",
    )

    assert targeted == ["tests/test_healer_loop.py"]


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


def test_ingest_pr_feedback_skips_fetch_when_pr_has_not_changed(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="4022",
        repo="owner/repo",
        title="Issue 4022",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="4022",
        state="pr_open",
        pr_number=125,
        pr_last_seen_updated_at="2026-03-06T01:05:00Z",
    )

    loop = _make_loop(store)

    loop._ingest_pr_feedback()

    issue = store.get_healer_issue("4022")
    assert issue is not None
    assert issue["pr_last_seen_updated_at"] == "2026-03-06T01:05:00Z"
    loop.tracker.list_pr_comments.assert_not_called()
    loop.tracker.list_pr_reviews.assert_not_called()
    loop.tracker.list_pr_review_comments.assert_not_called()


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


def test_ingest_ready_issues_restores_pr_open_when_existing_issue_has_open_pr(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="5035",
        repo="owner/repo",
        title="Issue 5035",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="5035", state="queued", pr_number=0, pr_state="")

    loop = _make_loop(store)
    loop.tracker.list_ready_issues.return_value = [
        HealerIssue(
            issue_id="5035",
            repo="owner/repo",
            title="Issue 5035 refreshed",
            body="new body",
            author="alice",
            labels=["healer:ready"],
            priority=5,
            html_url="https://example.test/issues/5035",
        )
    ]
    loop.tracker.find_pr_for_issue.return_value = PullRequestResult(
        number=235,
        state="open",
        html_url="https://github.com/owner/repo/pull/235",
    )

    loop._ingest_ready_issues()

    issue = store.get_healer_issue("5035")
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert issue["pr_number"] == 235
    assert issue["pr_state"] == "open"
    loop.tracker.add_issue_reaction.assert_not_called()


def test_ingest_ready_issues_coalesces_duplicate_scope(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()

    loop = _make_loop(store, healer_dedupe_enabled=True, healer_dedupe_close_duplicates=True)
    loop.tracker.close_issue.return_value = True
    shared_body = (
        "Required code outputs:\n"
        "- e2e-smoke/node/src/add.js\n"
        "- e2e-smoke/node/test/add.test.js\n\n"
        "Validation:\n"
        "- cd e2e-smoke/node && npm test -- --passWithNoTests\n"
    )
    loop.tracker.list_ready_issues.return_value = [
        HealerIssue(
            issue_id="5030",
            repo="owner/repo",
            title="Node regression canonical",
            body=shared_body,
            author="alice",
            labels=["healer:ready"],
            priority=5,
            html_url="https://example.test/issues/5030",
        ),
        HealerIssue(
            issue_id="5031",
            repo="owner/repo",
            title="Node regression duplicate",
            body=shared_body,
            author="alice",
            labels=["healer:ready"],
            priority=5,
            html_url="https://example.test/issues/5031",
        ),
    ]

    loop._ingest_ready_issues()

    canonical = store.get_healer_issue("5030")
    duplicate = store.get_healer_issue("5031")
    assert canonical is not None
    assert duplicate is not None
    assert duplicate["state"] == "archived"
    assert duplicate["last_failure_class"] == "duplicate_superseded"
    assert duplicate["superseded_by_issue_id"] == "5030"
    assert "5031" in str(canonical.get("feedback_context") or "")
    loop.tracker.close_issue.assert_called_once_with(issue_id="5031")
    assert loop.tracker.add_issue_reaction.call_count == 1


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


def test_process_claimed_issue_restores_open_pr_and_skips_attempt(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="5040",
        repo="owner/repo",
        title="Issue 5040",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store)
    loop.tracker.get_issue.return_value = {"issue_id": "5040", "state": "open", "labels": ["healer:ready"]}
    loop.tracker.find_pr_for_issue.return_value = PullRequestResult(
        number=240,
        state="open",
        html_url="https://github.com/owner/repo/pull/240",
    )

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("5040")
    attempts = store.list_healer_attempts(issue_id="5040")
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert issue["pr_number"] == 240
    assert issue["pr_state"] == "open"
    assert issue["attempt_count"] == 0
    assert attempts == []
    loop.runner.run_attempt.assert_not_called()


def test_process_claimed_issue_requeues_when_language_preflight_fails(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="5041",
        repo="owner/repo",
        title="Node sandbox issue",
        body="Validation: cd e2e-smoke/node && npm test -- --passWithNoTests",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store)
    (tmp_path / "e2e-smoke" / "node").mkdir(parents=True)
    loop.repo_path = tmp_path
    loop.tracker.get_issue.return_value = {"issue_id": "5041", "state": "open", "labels": ["healer:ready"]}
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.resolve_execution.return_value = SimpleNamespace(
        language_effective="node",
        language_detected="node",
        execution_root="e2e-smoke/node",
    )
    loop.preflight.ensure_language_ready.return_value = PreflightReport(
        language="node",
        execution_root="e2e-smoke/node",
        gate_mode="docker_only",
        status="failed",
        failure_class="validation_failed",
        summary="Preflight validation failed for node in e2e-smoke/node.",
        output_tail="npm install exploded",
        checked_at="2026-03-06 20:00:00",
        test_summary={"failed_tests": 1, "docker_full_status": "failed"},
    )
    loop.workspace_manager = MagicMock()

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("5041")
    attempts = store.list_healer_attempts(issue_id="5041")
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["attempt_count"] == 0
    assert issue["last_failure_class"] == "preflight_failed"
    assert attempts == []
    loop.runner.run_attempt.assert_not_called()
    loop.workspace_manager.ensure_workspace.assert_not_called()


def test_process_claimed_issue_requeues_when_workspace_is_corrupt_before_attempt_start(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="5042",
        repo="owner/repo",
        title="Python workspace issue",
        body="Validation: pytest tests/test_example.py -q",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store)
    loop.tracker.get_issue.return_value = {"issue_id": "5042", "state": "open", "labels": ["healer:ready"]}
    loop.workspace_manager.ensure_workspace.side_effect = RuntimeError("broken .git metadata")

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("5042")
    attempts = store.list_healer_attempts(issue_id="5042")
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["attempt_count"] == 0
    assert issue["last_failure_class"] == "workspace_corrupt"
    assert attempts == []
    loop.workspace_manager.prepare_workspace.assert_not_called()


def test_process_claimed_issue_lock_conflict_requeues_without_attempt_increment(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="5043",
        repo="owner/repo",
        title="Node lock contention issue",
        body="Validation: cd e2e-smoke/node && npm test -- --passWithNoTests",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store)
    loop.tracker.get_issue.return_value = {"issue_id": "5043", "state": "open", "labels": ["healer:ready"]}
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(
        issue_id="5043",
        branch="healer/issue-5043-node-lock-contention-issue",
        path=tmp_path,
    )
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(
        acquired=False,
        reason="lock_conflict:path:e2e-smoke/node",
    )

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("5043")
    attempts = store.list_healer_attempts(issue_id="5043")
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["attempt_count"] == 0
    assert issue["last_failure_class"] == "lock_conflict"
    assert attempts == []
    loop.runner.run_attempt.assert_not_called()


def test_process_claimed_issue_archives_and_closes_unsupported_language_before_workspace(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="50431",
        repo="owner/repo",
        title="Go sandbox issue",
        body="Validation: cd e2e-smoke/go && go test ./...",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store)
    loop.tracker.get_issue.return_value = {"issue_id": "50431", "state": "open", "labels": ["healer:ready"]}
    loop.tracker.close_issue.return_value = True
    loop.runner.resolve_execution.side_effect = UnsupportedLanguageError("Language 'go' is not supported.")

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("50431")
    attempts = store.list_healer_attempts(issue_id="50431")
    assert issue is not None
    assert issue["state"] == "archived"
    assert issue["pr_state"] == "closed"
    assert issue["attempt_count"] == 0
    assert issue["last_failure_class"] == "unsupported_language"
    assert "not supported" in str(issue["last_failure_reason"] or "")
    assert attempts == []
    loop.tracker.close_issue.assert_called_once_with(issue_id="50431")
    loop.workspace_manager.ensure_workspace.assert_not_called()
    loop.runner.run_attempt.assert_not_called()
    comment_body = loop.tracker.add_issue_comment.call_args.kwargs["body"]
    assert "python" in comment_body.lower()
    assert "node" in comment_body.lower()
    assert "migrate" in comment_body.lower()


def test_process_claimed_issue_archives_and_closes_unsupported_language_after_workspace(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="50432",
        repo="owner/repo",
        title="Ruby sandbox issue",
        body="Validation: cd e2e-smoke/ruby && bundle exec rspec",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store)
    workspace = tmp_path / "workspaces" / "issue-50432"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "50432", "state": "open", "labels": ["healer:ready"]}
    loop.tracker.close_issue.return_value = True
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-50432")
    loop.runner.resolve_execution.side_effect = [
        SimpleNamespace(language_effective="python", language_detected="python", execution_root=""),
        UnsupportedLanguageError("Language 'ruby' is not supported."),
    ]

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("50432")
    attempts = store.list_healer_attempts(issue_id="50432")
    assert issue is not None
    assert issue["state"] == "archived"
    assert issue["pr_state"] == "closed"
    assert issue["attempt_count"] == 0
    assert issue["last_failure_class"] == "unsupported_language"
    assert "ruby" in str(issue["last_failure_reason"] or "").lower()
    assert attempts == []
    loop.dispatcher.acquire_prediction_locks.assert_not_called()
    loop.tracker.close_issue.assert_called_once_with(issue_id="50432")
    loop.runner.run_attempt.assert_not_called()
    comment_body = loop.tracker.add_issue_comment.call_args.kwargs["body"]
    assert "python" in comment_body.lower()
    assert "node" in comment_body.lower()
    assert "migrate" in comment_body.lower()


def test_process_claimed_issue_allows_advisory_verifier_failure_by_default(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="5044",
        repo="owner/repo",
        title="Issue 5044",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    app_server_connector = type("CodexAppServerConnector", (), {"ensure_started": lambda self: None, "health_snapshot": lambda self: {}})()
    loop = _make_loop(store, connector=app_server_connector, healer_enable_review=False)
    workspace = tmp_path / "workspaces" / "issue-5044"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "5044", "state": "open", "labels": ["healer:ready"]}
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-5044")
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.dispatcher.upgrade_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.run_attempt.return_value = SimpleNamespace(
        success=True,
        diff_paths=["src/flow_healer/service.py"],
        test_summary={"failed_tests": 0},
        proposer_output="Edited src/flow_healer/service.py",
        workspace_status={},
        failure_class="",
        failure_reason="",
        failure_fingerprint="",
    )
    loop.verifier.verify.return_value = SimpleNamespace(
        passed=False,
        summary="Verifier output was not valid JSON; treating as advisory.",
        verdict="soft_fail",
        hard_failure=False,
        parse_error=True,
    )
    loop._commit_and_push = MagicMock(return_value=(True, "ok"))
    loop.tracker.open_or_update_pr.return_value = PullRequestResult(
        number=241,
        state="open",
        html_url="https://github.com/owner/repo/pull/241",
    )

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("5044")
    attempts = store.list_healer_attempts(issue_id="5044")
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert issue["pr_number"] == 241
    assert attempts[-1]["state"] == "pr_open"
    assert attempts[-1]["verifier_summary"]["verdict"] == "soft_fail"
    loop._commit_and_push.assert_called_once()


def test_process_claimed_issue_passes_staged_diff_payload_to_verifier(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="50441",
        repo="owner/repo",
        title="Issue 50441",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store, healer_enable_review=False)
    workspace = tmp_path / "workspaces" / "issue-50441"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "50441", "state": "open", "labels": ["healer:ready"]}
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-50441")
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.dispatcher.upgrade_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.run_attempt.return_value = SimpleNamespace(
        success=True,
        diff_paths=["src/flow_healer/service.py"],
        diff_files=1,
        diff_lines=12,
        staged_diff_content="diff --git a/src/flow_healer/service.py b/src/flow_healer/service.py\n+fix",
        staged_diff_metadata={"staged_paths": ["src/flow_healer/service.py"], "diff_files": 1},
        test_summary={"failed_tests": 0},
        proposer_output="Edited src/flow_healer/service.py",
        workspace_status={"staged_paths": ["src/flow_healer/service.py"]},
        failure_class="",
        failure_reason="",
        failure_fingerprint="",
    )
    loop.verifier.verify.return_value = SimpleNamespace(
        passed=True,
        summary="ok",
        verdict="pass",
        hard_failure=False,
        parse_error=False,
    )
    loop._commit_and_push = MagicMock(return_value=(True, "ok"))
    loop.tracker.open_or_update_pr.return_value = PullRequestResult(
        number=244,
        state="open",
        html_url="https://github.com/owner/repo/pull/244",
    )

    loop._process_claimed_issue(claimed)

    verify_kwargs = loop.verifier.verify.call_args.kwargs
    assert verify_kwargs["staged_diff_content"].startswith("diff --git")
    assert verify_kwargs["staged_diff_metadata"]["diff_files"] == 1
    assert verify_kwargs["staged_diff_metadata"]["staged_paths"] == ["src/flow_healer/service.py"]


def test_process_claimed_issue_uses_tracker_error_details_when_pr_open_fails(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="50442",
        repo="owner/repo",
        title="Issue 50442",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store, healer_enable_review=False)
    workspace = tmp_path / "workspaces" / "issue-50442"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "50442", "state": "open", "labels": ["healer:ready"]}
    loop.tracker.get_last_error.return_value = (
        "github_auth_missing",
        "GITHUB_TOKEN is missing; cannot create PR.",
    )
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-50442")
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.dispatcher.upgrade_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.run_attempt.return_value = SimpleNamespace(
        success=True,
        diff_paths=["src/flow_healer/service.py"],
        test_summary={"failed_tests": 0},
        proposer_output="Edited src/flow_healer/service.py",
        workspace_status={},
        failure_class="",
        failure_reason="",
        failure_fingerprint="",
    )
    loop.verifier.verify.return_value = SimpleNamespace(
        passed=True,
        summary="ok",
        verdict="pass",
        hard_failure=False,
        parse_error=False,
    )
    loop._commit_and_push = MagicMock(return_value=(True, "ok"))
    loop.tracker.open_or_update_pr.return_value = None

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("50442")
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["last_failure_class"] == "github_auth_missing"
    assert "GITHUB_TOKEN is missing" in issue["last_failure_reason"]
    assert store.get_state("healer_tracker_last_error_class") == "github_auth_missing"


def test_process_claimed_issue_reconciles_pending_pr_mutation_after_restart(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="50443",
        repo="owner/repo",
        title="Issue 50443",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store, healer_enable_review=False)
    workspace = tmp_path / "workspaces" / "issue-50443"
    workspace.mkdir(parents=True)
    loop._workspace_head_sha = MagicMock(return_value="abc123")
    loop.tracker.get_issue.return_value = {"issue_id": "50443", "state": "open", "labels": ["healer:ready"]}
    loop.tracker.find_pr_for_issue.side_effect = [
        None,
        PullRequestResult(
            number=245,
            state="open",
            html_url="https://github.com/owner/repo/pull/245",
        ),
    ]
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-50443")
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.dispatcher.upgrade_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.run_attempt.return_value = SimpleNamespace(
        success=True,
        diff_paths=["src/flow_healer/service.py"],
        test_summary={"failed_tests": 0},
        proposer_output="Edited src/flow_healer/service.py",
        workspace_status={},
        failure_class="",
        failure_reason="",
        failure_fingerprint="",
    )
    loop.verifier.verify.return_value = SimpleNamespace(
        passed=True,
        summary="ok",
        verdict="pass",
        hard_failure=False,
        parse_error=False,
    )
    loop._commit_and_push = MagicMock(return_value=(True, "ok"))

    pr_body = loop._format_pr_description(
        issue_id="50443",
        verifier_summary="ok",
        test_summary={"failed_tests": 0},
    )
    mutation_key = loop._mutation_key(
        action="open_pr:healer/issue-50443:abc123",
        issue_id="50443",
        body=pr_body,
    )
    assert (
        store.claim_healer_mutation(
            mutation_key=mutation_key,
            lease_owner="worker-crashed",
            lease_seconds=300,
        )
        == "claimed"
    )

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("50443")
    mutation = store.get_healer_mutation(mutation_key)
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert issue["pr_number"] == 245
    assert mutation is not None
    assert mutation["status"] == "success"
    loop.tracker.open_or_update_pr.assert_not_called()


def test_process_claimed_issue_blocks_when_required_verifier_soft_fails(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="5045",
        repo="owner/repo",
        title="Issue 5045",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store, healer_verifier_policy="required")
    workspace = tmp_path / "workspaces" / "issue-5045"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "5045", "state": "open", "labels": ["healer:ready"]}
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-5045")
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.dispatcher.upgrade_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.run_attempt.return_value = SimpleNamespace(
        success=True,
        diff_paths=["src/flow_healer/service.py"],
        test_summary={"failed_tests": 0},
        proposer_output="Edited src/flow_healer/service.py",
        workspace_status={},
        failure_class="",
        failure_reason="",
        failure_fingerprint="",
    )
    loop.verifier.verify.return_value = SimpleNamespace(
        passed=False,
        summary="Need stronger semantic verification.",
        verdict="soft_fail",
        hard_failure=False,
        parse_error=False,
    )
    loop._commit_and_push = MagicMock(return_value=(True, "ok"))

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("5045")
    attempts = store.list_healer_attempts(issue_id="5045")
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["last_failure_class"] == "verifier_failed"
    assert "[verifier_feedback]" in str(issue["feedback_context"] or "")
    assert "verdict=soft_fail" in str(issue["feedback_context"] or "")
    assert "Need stronger semantic verification." in str(issue["feedback_context"] or "")
    assert attempts[-1]["state"] == "failed"
    loop._commit_and_push.assert_not_called()


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


def test_auto_approve_open_pr_approves_clean_pr_from_different_author(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="6011",
        repo="owner/repo",
        title="Issue 6011",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="6011", state="pr_open", pr_number=128, pr_state="open")

    loop = _make_loop(store)
    loop.tracker.viewer_login.return_value = "healer-reviewer"
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=128,
        state="open",
        html_url="https://github.com/owner/repo/pull/128",
        mergeable_state="clean",
        author="healer-service",
    )
    loop.tracker.list_pr_reviews.return_value = []
    loop.tracker.approve_pr.return_value = True

    approved = loop._auto_approve_open_prs()

    assert approved == 1
    loop.tracker.approve_pr.assert_called_once_with(
        pr_number=128,
        body="Auto-approving clean PR with no merge conflicts.",
    )


def test_auto_approve_open_pr_skips_prs_authored_by_viewer(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="6012",
        repo="owner/repo",
        title="Issue 6012",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="6012", state="pr_open", pr_number=129, pr_state="open")

    loop = _make_loop(store)
    loop.tracker.viewer_login.return_value = "healer-service"
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=129,
        state="open",
        html_url="https://github.com/owner/repo/pull/129",
        mergeable_state="clean",
        author="healer-service",
    )

    approved = loop._auto_approve_open_prs()

    assert approved == 0
    loop.tracker.approve_pr.assert_not_called()


def test_auto_merge_open_pr_merges_clean_pr(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="6013",
        repo="owner/repo",
        title="Issue 6013",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="6013", state="pr_open", pr_number=130, pr_state="open")

    loop = _make_loop(store)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=130,
        state="open",
        html_url="https://github.com/owner/repo/pull/130",
        mergeable_state="clean",
        author="healer-service",
    )
    loop.tracker.merge_pr.return_value = True

    merged = loop._auto_merge_open_prs()

    assert merged == 1
    loop.tracker.merge_pr.assert_called_once_with(pr_number=130, merge_method="squash")


def test_auto_merge_open_pr_skips_dirty_pr(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="6014",
        repo="owner/repo",
        title="Issue 6014",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="6014", state="pr_open", pr_number=131, pr_state="open")

    loop = _make_loop(store)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=131,
        state="open",
        html_url="https://github.com/owner/repo/pull/131",
        mergeable_state="dirty",
        author="healer-service",
    )

    merged = loop._auto_merge_open_prs()

    assert merged == 0
    loop.tracker.merge_pr.assert_not_called()


def test_reconcile_pr_outcomes_requeues_conflicted_pr_by_default(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="6015",
        repo="owner/repo",
        title="Issue 6015",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="6015", state="pr_open", pr_number=132, pr_state="open")

    loop = _make_loop(store)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=132, state="conflict", html_url="", mergeable_state="dirty", author="bot"
    )
    loop.tracker.close_pr.return_value = True
    resolved = loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("6015")
    assert resolved == 0
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["pr_number"] == 0
    assert issue["pr_state"] == ""
    assert issue["last_failure_class"] == "pr_conflict_requeued"
    assert int(issue["conflict_requeue_count"] or 0) == 1
    loop.tracker.close_pr.assert_called_once()
    loop.tracker.close_issue.assert_not_called()
    loop.tracker.add_issue_comment.assert_called_once()


def test_reconcile_pr_outcomes_debounces_conflicted_pr_before_requeue(tmp_path):
    import datetime as dt

    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="60155",
        repo="owner/repo",
        title="Issue 60155",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="60155", state="pr_open", pr_number=235, pr_state="open")

    loop = _make_loop(store, healer_conflict_requeue_debounce_seconds=120)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=235,
        state="conflict",
        html_url="",
        mergeable_state="dirty",
        author="bot",
        head_ref="healer/issue-60155",
    )
    loop.tracker.close_pr.return_value = True

    loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("60155")
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert issue["pr_number"] == 235
    assert issue.get("stuck_since") is not None
    loop.tracker.close_pr.assert_not_called()

    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    conn = store._connect()
    conn.execute("UPDATE healer_issues SET stuck_since = ? WHERE issue_id = '60155'", (past,))
    conn.commit()

    loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("60155")
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["pr_number"] == 0
    assert issue["last_failure_class"] == "pr_conflict_requeued"
    loop.tracker.close_pr.assert_called_once()
    loop.tracker.delete_branch.assert_called_once_with(branch="healer/issue-60155")


def test_reconcile_pr_outcomes_blocks_after_conflict_requeue_cap(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="60151",
        repo="owner/repo",
        title="Issue 60151",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="60151",
        state="pr_open",
        pr_number=232,
        pr_state="open",
        conflict_requeue_count=3,
    )

    loop = _make_loop(store, healer_conflict_auto_requeue_max_attempts=3)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=232, state="conflict", html_url="", mergeable_state="dirty", author="bot"
    )
    loop.tracker.close_pr.return_value = True

    loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("60151")
    assert issue is not None
    assert issue["state"] == "blocked"
    assert issue["last_failure_class"] == "pr_conflict_retry_exhausted"
    assert int(issue["conflict_requeue_count"] or 0) == 4


def test_reconcile_pr_outcomes_archives_when_conflict_auto_requeue_disabled(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="60152",
        repo="owner/repo",
        title="Issue 60152",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="60152", state="pr_open", pr_number=233, pr_state="open")

    loop = _make_loop(store, healer_conflict_auto_requeue_enabled=False)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=233, state="conflict", html_url="", mergeable_state="dirty", author="bot"
    )
    loop.tracker.close_pr.return_value = True
    loop.tracker.close_issue.return_value = True

    loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("60152")
    assert issue is not None
    assert issue["state"] == "archived"
    assert issue["last_failure_class"] == "pr_conflict_superseded"


def test_reconcile_pr_outcomes_blocks_conflict_when_close_fails(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="6016",
        repo="owner/repo",
        title="Issue 6016",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="6016", state="pr_open", pr_number=133, pr_state="open")

    loop = _make_loop(store)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=133, state="conflict", html_url="", mergeable_state="dirty", author="bot"
    )
    loop.tracker.close_pr.return_value = False

    resolved = loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("6016")
    assert resolved == 0
    assert issue is not None
    assert issue["state"] == "blocked"
    assert issue["pr_state"] == "conflict"
    assert issue["last_failure_class"] == "pr_conflict"
    loop.tracker.close_issue.assert_not_called()
    loop.tracker.add_issue_comment.assert_called_once()


def test_reconcile_pr_outcomes_requeues_closed_conflicted_pr(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="6017",
        repo="owner/repo",
        title="Issue 6017",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="6017", state="pr_open", pr_number=134, pr_state="conflict")

    loop = _make_loop(store)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=134, state="closed", html_url="", mergeable_state="", author="bot"
    )
    loop.tracker.get_issue.return_value = {"issue_id": "6017", "state": "open", "labels": ["healer:ready"]}

    resolved = loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("6017")
    assert resolved == 0
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["pr_number"] == 0
    assert issue["pr_state"] == ""
    loop.tracker.add_issue_comment.assert_called_once()


def test_reconcile_pr_outcomes_archives_closed_conflicted_pr_for_closed_issue(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="60171",
        repo="owner/repo",
        title="Issue 60171",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="60171", state="pr_open", pr_number=138, pr_state="conflict")

    loop = _make_loop(store)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=138, state="closed", html_url="", mergeable_state="", author="bot"
    )
    loop.tracker.get_issue.return_value = {"issue_id": "60171", "state": "closed", "labels": ["healer:ready"]}

    resolved = loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("60171")
    assert resolved == 0
    assert issue is not None
    assert issue["state"] == "archived"
    assert issue["pr_number"] == 138
    assert issue["pr_state"] == "closed"
    loop.tracker.add_issue_comment.assert_not_called()


def test_reconcile_pr_outcomes_restores_pr_open_after_conflict_clears(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="6018",
        repo="owner/repo",
        title="Issue 6018",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="6018",
        state="blocked",
        pr_number=135,
        pr_state="conflict",
        last_failure_class="pr_conflict",
        last_failure_reason="old conflict",
    )

    loop = _make_loop(store)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=135, state="open", html_url="", mergeable_state="clean", author="bot"
    )

    resolved = loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("6018")
    assert resolved == 0
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert issue["pr_number"] == 135
    assert issue["pr_state"] == "open"
    assert issue["last_failure_class"] == ""
    assert issue["last_failure_reason"] == ""
    loop.tracker.add_issue_comment.assert_not_called()


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
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=126, state="merged", html_url="", mergeable_state="", author="bot"
    )
    loop.tracker.close_issue.return_value = True

    resolved = loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("602")
    assert resolved == 1
    assert issue is not None
    assert issue["state"] == "resolved"
    assert issue["pr_state"] == "merged"
    loop.tracker.close_issue.assert_called_once_with(issue_id="602")
    loop.tracker.add_issue_comment.assert_called_once()


def test_reconcile_pr_outcomes_discovers_merged_pr_from_pending_approval(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="603",
        repo="owner/repo",
        title="Issue 603",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="603", state="pr_pending_approval")

    loop = _make_loop(store)
    loop.tracker.find_pr_for_issue.return_value = PullRequestResult(
        number=127,
        state="merged",
        html_url="https://github.com/owner/repo/pull/127",
    )
    loop.tracker.close_issue.return_value = True

    resolved = loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("603")
    assert resolved == 1
    assert issue is not None
    assert issue["state"] == "resolved"
    assert issue["pr_number"] == 127
    assert issue["pr_state"] == "merged"
    loop.tracker.find_pr_for_issue.assert_called_once_with(issue_id="603")
    loop.tracker.close_issue.assert_called_once_with(issue_id="603")
    loop.tracker.add_issue_comment.assert_called_once()


def test_ingest_ready_issues_does_not_requeue_conflict_blocked_issue(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="6031",
        repo="owner/repo",
        title="Issue 6031",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="6031", state="blocked", pr_number=136, pr_state="conflict")

    loop = _make_loop(store)
    loop.tracker.list_ready_issues.return_value = [
        HealerIssue(
            issue_id="6031",
            repo="owner/repo",
            title="Issue 6031",
            body="",
            author="alice",
            labels=["healer:ready"],
            priority=5,
            html_url="https://example.test/issues/6031",
        )
    ]

    loop._ingest_ready_issues()

    issue = store.get_healer_issue("6031")
    assert issue is not None
    assert issue["state"] == "blocked"
    assert issue["pr_number"] == 136
    assert issue["pr_state"] == "conflict"
    loop.tracker.add_issue_reaction.assert_not_called()


def test_conflicted_issue_is_ignored_by_auto_pr_actions_after_reconcile(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="6032",
        repo="owner/repo",
        title="Issue 6032",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="6032", state="pr_open", pr_number=137, pr_state="open")

    loop = _make_loop(store)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=137,
        state="conflict",
        html_url="https://github.com/owner/repo/pull/137",
        mergeable_state="dirty",
        author="healer-service",
    )

    loop._reconcile_pr_outcomes()
    approved = loop._auto_approve_open_prs()
    merged = loop._auto_merge_open_prs()

    issue = store.get_healer_issue("6032")
    assert issue is not None
    assert issue["state"] == "queued"
    assert approved == 0
    assert merged == 0
    loop.tracker.approve_pr.assert_not_called()
    loop.tracker.merge_pr.assert_not_called()


def test_reconcile_pr_outcomes_marks_stuck_pr_on_first_detection(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="7001",
        repo="owner/repo",
        title="Issue 7001",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="7001", state="pr_open", pr_number=200, pr_state="open")

    loop = _make_loop(store, healer_stuck_pr_timeout_minutes=60)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=200, state="open", html_url="", mergeable_state="blocked", author="bot"
    )

    loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("7001")
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert issue.get("stuck_since") is not None
    loop.tracker.close_pr.assert_not_called()
    loop.tracker.add_issue_comment.assert_not_called()


def test_reconcile_pr_outcomes_does_not_reset_stuck_since_on_subsequent_ticks(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="7002",
        repo="owner/repo",
        title="Issue 7002",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="7002", state="pr_open", pr_number=201, pr_state="open")
    # Simulate first detection already happened
    store.mark_pr_stuck(issue_id="7002", pr_number=201)
    first_stuck_since = (store.get_healer_issue("7002") or {}).get("stuck_since")

    loop = _make_loop(store, healer_stuck_pr_timeout_minutes=60)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=201, state="open", html_url="", mergeable_state="has_failure", author="bot"
    )

    loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("7002")
    assert issue is not None
    assert issue.get("stuck_since") == first_stuck_since
    loop.tracker.close_pr.assert_not_called()


def test_reconcile_pr_outcomes_closes_and_requeues_stuck_pr_after_timeout(tmp_path):
    import datetime as dt

    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="7003",
        repo="owner/repo",
        title="Issue 7003",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="7003", state="pr_open", pr_number=202, pr_state="open")
    # Set stuck_since to 2 hours ago
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    conn = store._connect()
    conn.execute("UPDATE healer_issues SET stuck_since = ? WHERE issue_id = '7003'", (past,))
    conn.commit()

    loop = _make_loop(store, healer_stuck_pr_timeout_minutes=60)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=202, state="open", html_url="", mergeable_state="behind", author="bot"
    )
    loop.tracker.close_pr.return_value = True

    loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("7003")
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["pr_number"] == 0
    assert issue["pr_state"] == ""
    assert "behind" in str(issue.get("feedback_context") or "")
    loop.tracker.close_pr.assert_called_once_with(pr_number=202, comment=loop.tracker.close_pr.call_args.kwargs["comment"])
    loop.tracker.add_issue_comment.assert_called_once()


def test_reconcile_pr_outcomes_does_not_requeue_stuck_pr_when_close_fails(tmp_path):
    import datetime as dt

    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="70031",
        repo="owner/repo",
        title="Issue 70031",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="70031", state="pr_open", pr_number=302, pr_state="open")
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    conn = store._connect()
    conn.execute("UPDATE healer_issues SET stuck_since = ? WHERE issue_id = '70031'", (past,))
    conn.commit()

    loop = _make_loop(store, healer_stuck_pr_timeout_minutes=60)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=302, state="open", html_url="", mergeable_state="behind", author="bot"
    )
    loop.tracker.close_pr.return_value = False

    loop._reconcile_pr_outcomes()

    issue = store.get_healer_issue("70031")
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert issue["pr_number"] == 302
    assert str(issue["feedback_context"] or "") == ""
    loop.tracker.add_issue_comment.assert_not_called()


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
    lease_lost = threading.Event()
    loop.store = MagicMock()
    loop.dispatcher = MagicMock()
    loop.dispatcher.lease_seconds = 180
    loop.worker_id = "worker-a"
    loop.store.renew_healer_issue_lease.return_value = True

    loop._lease_heartbeat("703", stop_event, lease_lost)  # type: ignore[arg-type]

    loop.store.renew_healer_issue_lease.assert_called_once_with(
        issue_id="703",
        worker_id="worker-a",
        lease_seconds=180,
    )
    assert lease_lost.is_set() is False


def test_lease_heartbeat_sets_event_when_renewal_fails(tmp_path):
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
    lease_lost = threading.Event()
    loop.store = MagicMock()
    loop.dispatcher = MagicMock()
    loop.dispatcher.lease_seconds = 180
    loop.worker_id = "worker-a"
    loop.store.renew_healer_issue_lease.return_value = False

    loop._lease_heartbeat("704", stop_event, lease_lost)  # type: ignore[arg-type]

    assert lease_lost.is_set() is True


def test_process_claimed_issue_requeues_when_lease_is_lost_after_runner(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="7041",
        repo="owner/repo",
        title="Issue 7041",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store)
    trip_lease = threading.Event()
    workspace = tmp_path / "workspaces" / "issue-7041"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "7041", "state": "open", "labels": ["healer:ready"]}
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(
        path=workspace,
        branch="healer/issue-7041",
    )
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.dispatcher.upgrade_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop._commit_and_push = MagicMock(return_value=(True, "ok"))
    loop.verifier.verify.return_value = SimpleNamespace(passed=True, summary="ok")

    def fake_lease_heartbeat(_issue_id, stop_event, lease_lost):
        while not stop_event.wait(0.01):
            if trip_lease.is_set():
                lease_lost.set()
                return

    loop._lease_heartbeat = fake_lease_heartbeat
    def fake_run_attempt(**_):
        trip_lease.set()
        threading.Event().wait(0.05)
        return SimpleNamespace(
            success=True,
            diff_paths=["src/flow_healer/service.py"],
            test_summary={"failed_tests": 0},
            proposer_output="```diff\ndiff --git a/x b/x\n```",
            workspace_status={},
            failure_class="",
            failure_reason="",
            failure_fingerprint="",
        )

    loop.runner.run_attempt.side_effect = fake_run_attempt

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("7041")
    attempts = store.list_healer_attempts(issue_id="7041")
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["last_failure_class"] == "lease_expired"
    assert attempts[0]["failure_class"] == "lease_expired"
    loop.verifier.verify.assert_not_called()
    loop._commit_and_push.assert_not_called()


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
    assert issue["state"] == "pr_pending_approval"
    assert issue["pr_number"] == 125
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


def test_backoff_or_fail_malformed_diff_does_not_exhaust_retry_budget(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="3041",
        repo="owner/repo",
        title="Issue 3041",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store, healer_retry_budget=1, healer_backoff_initial_seconds=60)

    state = loop._backoff_or_fail(
        issue_id="3041",
        attempt_no=7,
        failure_class="malformed_diff",
        failure_reason="Proposer returned a diff fence, but the contents were not a valid unified diff.",
    )
    issue = store.get_healer_issue("3041")
    assert issue is not None
    assert state == "queued"
    assert issue["state"] == "queued"
    assert issue["last_failure_class"] == "malformed_diff"
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


def test_backoff_or_fail_lock_conflict_does_not_exhaust_retry_budget(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="3051",
        repo="owner/repo",
        title="Issue 3051",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store, healer_retry_budget=1, healer_backoff_initial_seconds=60)

    state = loop._backoff_or_fail(
        issue_id="3051",
        attempt_no=9,
        failure_class="lock_conflict",
        failure_reason="lock_conflict:path:e2e-smoke/node",
    )
    issue = store.get_healer_issue("3051")
    assert issue is not None
    assert state == "queued"
    assert issue["state"] == "queued"
    assert issue["last_failure_class"] == "lock_conflict"
    assert issue["backoff_until"]


def test_quarantine_failure_loop_blocks_repeated_generated_artifact_fingerprint(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="390",
        repo="owner/repo",
        title="Issue 390",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.create_healer_attempt(
        attempt_id="hat_prev",
        issue_id="390",
        attempt_no=1,
        state="failed",
        predicted_lock_set=["repo:*"],
        prediction_source="test",
        task_kind="fix",
        output_targets=["e2e-smoke/ruby/add.rb"],
        tool_policy="repo_only",
        validation_profile="code_change",
    )
    store.finish_healer_attempt(
        attempt_id="hat_prev",
        state="failed",
        actual_diff_set=[],
        test_summary={
            "failure_fingerprint": "generated_artifact_contamination|e2e-smoke/ruby|e2e-smoke/ruby/gemfile.lock"
        },
        verifier_summary={},
        failure_class="generated_artifact_contamination",
        failure_reason="Gemfile.lock contamination",
    )

    loop = _make_loop(store, healer_failure_fingerprint_quarantine_threshold=2)

    blocked = loop._maybe_quarantine_failure_loop(
        issue_id="390",
        failure_class="generated_artifact_contamination",
        failure_reason="Gemfile.lock contamination",
        failure_fingerprint="generated_artifact_contamination|e2e-smoke/ruby|e2e-smoke/ruby/gemfile.lock",
        workspace_status={
            "contamination_paths": ["e2e-smoke/ruby/Gemfile.lock"],
            "execution_root": "e2e-smoke/ruby",
        },
    )

    issue = store.get_healer_issue("390")
    assert blocked is True
    assert issue is not None
    assert issue["state"] == "blocked"
    assert issue["last_failure_class"] == "generated_artifact_contamination"
    assert "Repeated failure fingerprint" in issue["feedback_context"]
    assert store.get_state("healer_last_failure_fingerprint") == (
        "generated_artifact_contamination|e2e-smoke/ruby|e2e-smoke/ruby/gemfile.lock"
    )
    assert store.get_state("healer_last_contamination_paths") == "e2e-smoke/ruby/Gemfile.lock"
    loop.tracker.add_issue_comment.assert_called()


def test_quarantine_failure_loop_blocks_repeated_no_workspace_change_without_persisted_fingerprint(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="391",
        repo="owner/repo",
        title="Issue 391",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.create_healer_attempt(
        attempt_id="hat_prev",
        issue_id="391",
        attempt_no=1,
        state="failed",
        predicted_lock_set=["repo:*"],
        prediction_source="test",
        task_kind="fix",
        output_targets=["demo.py"],
        tool_policy="repo_only",
        validation_profile="code_change",
    )
    store.finish_healer_attempt(
        attempt_id="hat_prev",
        state="failed",
        actual_diff_set=[],
        test_summary={},
        verifier_summary={},
        failure_class="no_workspace_change",
        failure_reason="Agent returned a status summary without leaving workspace edits.",
    )

    loop = _make_loop(store, healer_failure_fingerprint_quarantine_threshold=2)
    blocked = loop._maybe_quarantine_failure_loop(
        issue_id="391",
        failure_class="no_workspace_change",
        failure_reason="Agent returned a status summary without leaving workspace edits.",
        failure_fingerprint="execution_contract|workspace_edit|no_workspace_change",
        workspace_status={},
    )

    issue = store.get_healer_issue("391")
    assert blocked is True
    assert issue is not None
    assert issue["state"] == "blocked"
    assert issue["last_failure_class"] == "no_workspace_change"
    assert "Repeated failure fingerprint" in issue["feedback_context"]


def test_quarantine_failure_loop_ignores_interrupted_attempts_between_matching_failures(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="392",
        repo="owner/repo",
        title="Issue 392",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store, healer_failure_fingerprint_quarantine_threshold=2)
    loop.store.list_healer_attempts = MagicMock(
        return_value=[
            {"failure_class": "interrupted", "test_summary": {}},
            {"failure_class": "no_workspace_change", "test_summary": {}},
        ]
    )

    blocked = loop._maybe_quarantine_failure_loop(
        issue_id="392",
        failure_class="no_workspace_change",
        failure_reason="Agent returned a status summary without leaving workspace edits.",
        failure_fingerprint="execution_contract|workspace_edit|no_workspace_change",
        workspace_status={},
    )

    issue = store.get_healer_issue("392")
    assert blocked is True
    assert issue is not None
    assert issue["state"] == "blocked"
    assert issue["last_failure_class"] == "no_workspace_change"


def test_record_app_server_attempt_metrics_tracks_zero_diff_and_task_kind(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    app_server_cls = type("CodexAppServerConnector", (_HealthyConnector,), {})
    loop = _make_loop(store, connector=app_server_cls())

    loop._record_app_server_attempt_metrics(connector=loop.connector, task_kind="fix", had_material_diff=False)
    loop._record_app_server_attempt_metrics(connector=loop.connector, task_kind="fix", had_material_diff=True)

    assert store.get_state("app_server_attempts") == "2"
    assert store.get_state("app_server_attempts_with_material_diff") == "1"
    assert store.get_state("app_server_attempts_with_zero_diff") == "1"
    assert store.get_state("app_server_attempts_task_kind_fix") == "2"
    assert store.get_state("app_server_attempts_with_zero_diff_task_kind_fix") == "1"


def test_select_backend_for_task_routes_code_to_exec_in_exec_for_code_mode(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(
        store,
        connector_routing_mode="exec_for_code",
        code_connector_backend="exec",
        non_code_connector_backend="app_server",
    )
    task_spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="patch",
        output_targets=("src/flow_healer/healer_loop.py",),
        tool_policy="repo_only",
        validation_profile="code_change",
    )

    backend = loop._select_backend_for_task(task_spec)

    assert backend == "exec"


def test_select_backend_for_task_routes_docs_to_non_code_backend(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(
        store,
        connector_routing_mode="exec_for_code",
        code_connector_backend="exec",
        non_code_connector_backend="app_server",
    )
    task_spec = HealerTaskSpec(
        task_kind="docs",
        output_mode="artifact",
        output_targets=("docs/plan.md",),
        tool_policy="repo_only",
        validation_profile="artifact_only",
    )

    backend = loop._select_backend_for_task(task_spec)

    assert backend == "app_server"


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


def test_tick_once_skips_cycle_when_tracker_unavailable(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    loop.tracker.enabled = False

    loop._tick_once()

    loop.dispatcher.claim_next_issue.assert_not_called()
    assert store.get_state("healer_tracker_available") == "false"
    assert store.get_state("healer_tracker_last_error_class") == "github_auth_missing"


def test_tick_once_runs_reconciler_before_paused_return(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.set_state("healer_paused", "true")

    loop = _make_loop(store)
    loop._maybe_run_scan = MagicMock()

    loop._tick_once()

    loop.reconciler.reconcile.assert_called_once()
    loop._maybe_run_scan.assert_not_called()
    loop.dispatcher.claim_next_issue.assert_not_called()


def test_tick_once_stops_claiming_when_connector_becomes_unavailable_mid_cycle(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    connector = MagicMock()
    connector.ensure_started.return_value = None
    connector.health_snapshot.side_effect = [
        {
            "available": True,
            "configured_command": "codex",
            "resolved_command": "/opt/homebrew/bin/codex",
            "availability_reason": "",
            "last_health_error": "",
        },
        {
            "available": True,
            "configured_command": "codex",
            "resolved_command": "/opt/homebrew/bin/codex",
            "availability_reason": "",
            "last_health_error": "",
        },
        {
            "available": False,
            "configured_command": "codex",
            "resolved_command": "",
            "availability_reason": "Codex died mid-cycle.",
            "last_health_error": "Codex died mid-cycle.",
        },
    ]

    loop = _make_loop(store, connector=connector)
    loop.settings.healer_max_concurrent_issues = 2
    loop.dispatcher.claim_next_issue.side_effect = [{"issue_id": "a"}, {"issue_id": "b"}]
    loop._process_claimed_issue = MagicMock()

    loop._tick_once()

    loop.dispatcher.claim_next_issue.assert_called_once()
    loop._process_claimed_issue.assert_called_once_with({"issue_id": "a"})


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
            failure_class="tests_failed" if state == "failed" else "",
            failure_reason="Targeted sandbox validation failed." if state == "failed" else "",
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


def test_cleanup_workspace_tracks_failure_state_when_removal_fails(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="1004",
        repo="owner/repo",
        title="Issue 1004",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    workspace = tmp_path / "workspaces" / "issue-1004"
    workspace.mkdir(parents=True)

    loop = _make_loop(store)
    loop.workspace_manager = MagicMock()
    loop.workspace_manager.remove_workspace.side_effect = RuntimeError("disk full")

    loop._cleanup_workspace(issue_id="1004", state="failed", workspace_path=workspace)

    assert store.get_state("healer_last_workspace_cleanup_error") == "disk full"


def test_post_issue_status_retries_once(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    loop.tracker.add_issue_comment.side_effect = [RuntimeError("boom"), None]
    sleep_calls: list[int | float] = []

    monkeypatch.setattr("flow_healer.healer_loop.time.sleep", lambda seconds: sleep_calls.append(seconds))

    loop._post_issue_status(issue_id="1005", body="hello")

    assert loop.tracker.add_issue_comment.call_count == 2
    assert sleep_calls == [2]


def test_sanitize_execution_root_rejects_escape_and_keeps_nested_path(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "src" / "pkg").mkdir(parents=True)

    assert _sanitize_execution_root(execution_root="../outside", workspace=workspace) == ""
    assert _sanitize_execution_root(execution_root="src/pkg", workspace=workspace) == "src/pkg"


# --- Change 1: Failure-class-aware retry strategy ---


def test_backoff_tests_failed_produces_shorter_delay(tmp_path):
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
    store.upsert_healer_issue(
        issue_id="402",
        repo="owner/repo",
        title="Issue 402",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store, healer_retry_budget=3, healer_backoff_initial_seconds=100, healer_backoff_max_seconds=3600)

    loop._backoff_or_fail(issue_id="401", attempt_no=1, failure_class="tests_failed", failure_reason="pytest failed")
    loop._backoff_or_fail(issue_id="402", attempt_no=1, failure_class="push_failed", failure_reason="push failed")
    tests_backoff = store.get_healer_issue("401")["backoff_until"]
    push_backoff = store.get_healer_issue("402")["backoff_until"]
    # tests_failed has 0.5x multiplier, push_failed has 2.0x — push should be later
    assert tests_backoff < push_backoff


def test_backoff_sets_feedback_context_with_hint(tmp_path):
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
    loop = _make_loop(store, healer_retry_budget=3, healer_backoff_initial_seconds=60, healer_backoff_max_seconds=3600)

    loop._backoff_or_fail(issue_id="403", attempt_no=1, failure_class="tests_failed", failure_reason="pytest failed")
    issue = store.get_healer_issue("403")
    assert issue is not None
    hint = _FAILURE_CLASS_STRATEGY["tests_failed"]["feedback_hint"]
    assert issue["feedback_context"] == hint


def test_backoff_push_failed_requeues_without_consuming_issue_trust(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    for iid in ("410", "411"):
        store.upsert_healer_issue(
            issue_id=iid,
            repo="owner/repo",
            title=f"Issue {iid}",
            body="",
            author="alice",
            labels=["healer:ready"],
            priority=5,
        )
    loop = _make_loop(store, healer_retry_budget=3, healer_backoff_initial_seconds=100, healer_backoff_max_seconds=10000)

    loop._backoff_or_fail(issue_id="410", attempt_no=1, failure_class="verifier_failed", failure_reason="rejected")
    push_state = loop._backoff_or_fail(issue_id="411", attempt_no=3, failure_class="push_failed", failure_reason="push error")
    push_issue = store.get_healer_issue("411")
    assert push_state == "queued"
    assert push_issue is not None
    assert push_issue["state"] == "queued"
    assert push_issue["backoff_until"] is not None
    assert push_issue["last_failure_class"] == "push_failed"
    assert store.get_healer_issue("410")["state"] == "queued"


def test_backoff_push_non_fast_forward_requeues_without_failing_issue(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="412",
        repo="owner/repo",
        title="Issue 412",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store, healer_retry_budget=1, healer_backoff_initial_seconds=60, healer_backoff_max_seconds=3600)

    state = loop._backoff_or_fail(
        issue_id="412",
        attempt_no=1,
        failure_class="push_non_fast_forward",
        failure_reason="non-fast-forward",
    )

    issue = store.get_healer_issue("412")
    assert state == "queued"
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["last_failure_class"] == "push_non_fast_forward"


def test_push_issue_branch_force_with_lease_updates_stale_managed_remote_branch(tmp_path):
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True, timeout=60)
    _init_repo(repo)
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")

    branch = "healer/issue-999-example"
    _git(repo, "checkout", "-B", branch)
    (repo / "feature.txt").write_text("old remote content\n", encoding="utf-8")
    _git(repo, "add", "feature.txt")
    _git(repo, "commit", "-m", "old remote commit")
    _git(repo, "push", "-u", "origin", f"HEAD:refs/heads/{branch}")

    _git(repo, "checkout", "main")
    _git(repo, "branch", "-D", branch)
    _git(repo, "checkout", "-B", branch, "main")
    (repo / "feature.txt").write_text("fresh retry content\n", encoding="utf-8")
    _git(repo, "add", "feature.txt")
    _git(repo, "commit", "-m", "fresh retry commit")

    push = _push_issue_branch(workspace=repo, branch=branch)

    remote_feature = _git(repo, "show", f"origin/{branch}:feature.txt").stdout
    assert push.returncode == 0, push.stderr or push.stdout
    assert remote_feature == "fresh retry content\n"


# --- Change 3: Automated merge conflict resolution ---


def test_conflict_resolution_succeeds_with_clean_rebase(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace = tmp_path / "workspaces" / "issue-501"
    workspace.mkdir(parents=True)
    store.upsert_healer_issue(
        issue_id="501",
        repo="owner/repo",
        title="Issue 501",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="501",
        state="pr_open",
        pr_number=10,
        workspace_path=str(workspace),
        branch_name="healer/issue-501",
    )

    loop = _make_loop(store, healer_repo_path=str(tmp_path))
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=10, state="conflict", html_url="", mergeable_state="dirty", author="bot", head_ref="healer/issue-501"
    )

    call_log = []
    def fake_run(cmd, **kwargs):
        call_log.append(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    monkeypatch.setattr("flow_healer.healer_loop.subprocess.run", fake_run)

    row = store.get_healer_issue("501")
    resolved = loop._attempt_conflict_resolution(issue_id="501", pr_number=10, row=row)
    assert resolved is True
    cmds = [c[0] if isinstance(c, list) and c else "" for c in call_log]
    assert "git" in cmds[0]
    loop.runner.validate_workspace.assert_called_once()


def test_conflict_resolution_fails_with_too_many_files(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace = tmp_path / "workspaces" / "issue-502"
    workspace.mkdir(parents=True)
    store.upsert_healer_issue(
        issue_id="502",
        repo="owner/repo",
        title="Issue 502",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="502",
        state="pr_open",
        pr_number=11,
        workspace_path=str(workspace),
        branch_name="healer/issue-502",
    )

    loop = _make_loop(store, healer_repo_path=str(tmp_path))
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=11, state="conflict", html_url="", mergeable_state="dirty", author="bot", head_ref="healer/issue-502"
    )

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        cmd_str = " ".join(str(c) for c in cmd)
        if "rebase" in cmd_str and "--abort" not in cmd_str and "origin/" in cmd_str:
            result.returncode = 1  # Rebase fails with conflicts
        elif "diff" in cmd_str and "--name-only" in cmd_str:
            result.returncode = 0
            result.stdout = "\n".join([f"file{i}.py" for i in range(6)])  # 6 files > 5 limit
        else:
            result.returncode = 0
            result.stdout = ""
        result.stderr = ""
        return result

    monkeypatch.setattr("flow_healer.healer_loop.subprocess.run", fake_run)

    row = store.get_healer_issue("502")
    resolved = loop._attempt_conflict_resolution(issue_id="502", pr_number=11, row=row)
    assert resolved is False


def test_conflict_resolution_fails_when_connector_errors(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace = tmp_path / "workspaces" / "issue-503"
    workspace.mkdir(parents=True)
    (workspace / "conflict.py").write_text("<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> branch\n")
    store.upsert_healer_issue(
        issue_id="503",
        repo="owner/repo",
        title="Issue 503",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="503",
        state="pr_open",
        pr_number=12,
        workspace_path=str(workspace),
        branch_name="healer/issue-503",
    )

    loop = _make_loop(store, healer_repo_path=str(tmp_path))
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=12, state="conflict", html_url="", mergeable_state="dirty", author="bot", head_ref="healer/issue-503"
    )
    loop.connector = MagicMock()
    loop.connector.get_or_create_thread.return_value = "thread-1"
    loop.connector.run_turn.side_effect = RuntimeError("connector down")

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        cmd_str = " ".join(str(c) for c in cmd)
        if "rebase" in cmd_str and "--abort" not in cmd_str and "origin/" in cmd_str:
            result.returncode = 1  # Rebase has conflicts
        elif "diff" in cmd_str and "--name-only" in cmd_str:
            result.returncode = 0
            result.stdout = "conflict.py"
        else:
            result.returncode = 0
            result.stdout = ""
        result.stderr = ""
        return result

    monkeypatch.setattr("flow_healer.healer_loop.subprocess.run", fake_run)

    row = store.get_healer_issue("503")
    resolved = loop._attempt_conflict_resolution(issue_id="503", pr_number=12, row=row)
    assert resolved is False


def test_conflict_resolution_aborts_on_test_failure(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace = tmp_path / "workspaces" / "issue-504"
    workspace.mkdir(parents=True)
    (workspace / "fix.py").write_text("<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> branch\n")
    store.upsert_healer_issue(
        issue_id="504",
        repo="owner/repo",
        title="Issue 504",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="504",
        state="pr_open",
        pr_number=13,
        workspace_path=str(workspace),
        branch_name="healer/issue-504",
    )

    loop = _make_loop(store, healer_repo_path=str(tmp_path))
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=13, state="conflict", html_url="", mergeable_state="dirty", author="bot", head_ref="healer/issue-504"
    )
    loop.runner.validate_workspace.return_value = {"failed_tests": 1}
    loop.connector = MagicMock()
    loop.connector.get_or_create_thread.return_value = "thread-1"
    loop.connector.run_turn.return_value = "resolved content without conflict markers"

    call_log = []

    def fake_run(cmd, **kwargs):
        call_log.append(cmd)
        result = MagicMock()
        cmd_str = " ".join(str(c) for c in cmd)
        if "rebase" in cmd_str and "--abort" not in cmd_str and "--continue" not in cmd_str and "origin/" in cmd_str:
            result.returncode = 1  # Conflicts on initial rebase
        elif "rebase" in cmd_str and "--continue" in cmd_str:
            result.returncode = 0
        elif "diff" in cmd_str and "--name-only" in cmd_str:
            result.returncode = 0
            result.stdout = "fix.py"
        else:
            result.returncode = 0
            result.stdout = ""
        result.stderr = ""
        return result

    monkeypatch.setattr("flow_healer.healer_loop.subprocess.run", fake_run)

    row = store.get_healer_issue("504")
    resolved = loop._attempt_conflict_resolution(issue_id="504", pr_number=13, row=row)
    assert resolved is False
    loop.runner.validate_workspace.assert_called_once()
    assert all("pytest" not in " ".join(str(part) for part in cmd) for cmd in call_log)


def test_format_test_summary_bullets_produces_compact_markdown():
    bullets = AutonomousHealerLoop._format_test_summary_bullets(
        {
            "mode": "local_then_docker",
            "failed_tests": 0,
            "targeted_tests": ["tests/test_add.py", "tests/test_math.py"],
            "language_effective": "node",
            "execution_root": "e2e-smoke/node",
            "local_full_status": "passed",
            "local_full_exit_code": 0,
            "local_full_output_tail": "this should not appear in rendered bullets",
        }
    )

    assert "Test gates: `passed`" in bullets
    assert "Failed tests: `0`" in bullets
    assert any(item.startswith("Targeted tests: ") for item in bullets)
    assert all("output_tail" not in item for item in bullets)


def test_format_pr_description_uses_markdown_sections():
    body = AutonomousHealerLoop._format_pr_description(
        issue_id="155",
        verifier_summary="Verified and approved.",
        test_summary={"failed_tests": 0, "mode": "local_only"},
    )

    assert body.startswith("Flow Healer rolled in with an automated proposal for issue #155.")
    assert "### Verification" in body
    assert "### Test Summary" in body
    assert "- Test gates: `passed`" in body
    assert "Built with a little hustle by Flow Healer" in body
