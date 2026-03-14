import asyncio
import os
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from flow_healer.app_harness import AppRuntimeProfile
from flow_healer.browser_harness import BrowserJourneyResult
from flow_healer.healer_loop import (
    AutonomousHealerLoop,
    _FAILURE_CLASS_STRATEGY,
    _collect_targeted_tests,
    _failure_user_hint,
    _sanitize_execution_root,
    _push_issue_branch,
)
from flow_healer.healer_swarm import SwarmRecoveryOutcome, SwarmRecoveryPlan
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
        healer_repo_path=overrides.get("healer_repo_path", "/tmp"),
        enable_autonomous_healer=True,
        healer_poll_interval_seconds=60,
        healer_pulse_interval_seconds=overrides.get("healer_pulse_interval_seconds", 60),
        healer_mode="guarded_pr",
        healer_max_concurrent_issues=1,
        healer_max_wall_clock_seconds_per_issue=300,
        healer_learning_enabled=True,
        healer_enable_review=overrides.get("healer_enable_review", True),
        healer_enable_security_review=overrides.get("healer_enable_security_review", True),
        healer_issue_contract_mode=overrides.get("healer_issue_contract_mode", "lenient"),
        healer_parse_confidence_threshold=overrides.get("healer_parse_confidence_threshold", 0.3),
        healer_codex_native_multi_agent_enabled=overrides.get("healer_codex_native_multi_agent_enabled", False),
        healer_codex_native_multi_agent_max_subagents=overrides.get(
            "healer_codex_native_multi_agent_max_subagents", 3
        ),
        healer_swarm_enabled=overrides.get("healer_swarm_enabled", False),
        healer_swarm_mode=overrides.get("healer_swarm_mode", "failure_repair"),
        healer_swarm_max_parallel_agents=overrides.get("healer_swarm_max_parallel_agents", 4),
        healer_swarm_max_repair_cycles_per_attempt=overrides.get("healer_swarm_max_repair_cycles_per_attempt", 1),
        healer_swarm_trigger_failure_classes=overrides.get(
            "healer_swarm_trigger_failure_classes",
            [
                "tests_failed",
                "verifier_failed",
                "no_workspace_change*",
                "patch_apply_failed",
                "malformed_diff",
                "scope_violation",
                "generated_artifact_contamination",
            ],
        ),
        healer_swarm_backend_strategy=overrides.get("healer_swarm_backend_strategy", "match_selected_backend"),
        healer_verifier_policy=overrides.get("healer_verifier_policy", "advisory"),
        healer_issue_required_labels=["healer:ready"],
        healer_pr_actions_require_approval=overrides.get("healer_pr_actions_require_approval", False),
        healer_pr_required_label=overrides.get("healer_pr_required_label", "healer:pr-approved"),
        healer_pr_auto_approve_clean=overrides.get("healer_pr_auto_approve_clean", True),
        healer_pr_auto_merge_clean=overrides.get("healer_pr_auto_merge_clean", True),
        healer_pr_merge_method=overrides.get("healer_pr_merge_method", "squash"),
        healer_github_artifact_publish_enabled=overrides.get("healer_github_artifact_publish_enabled", True),
        healer_github_artifact_branch=overrides.get("healer_github_artifact_branch", "flow-healer-artifacts"),
        healer_github_artifact_retention_days=overrides.get("healer_github_artifact_retention_days", 30),
        healer_browser_log_publish_mode=overrides.get("healer_browser_log_publish_mode", "always"),
        healer_github_artifact_max_file_bytes=overrides.get("healer_github_artifact_max_file_bytes", 5 * 1024 * 1024),
        healer_github_artifact_max_run_bytes=overrides.get("healer_github_artifact_max_run_bytes", 25 * 1024 * 1024),
        healer_github_artifact_max_branch_bytes=overrides.get(
            "healer_github_artifact_max_branch_bytes", 250 * 1024 * 1024
        ),
        healer_harness_canary_interval_seconds=overrides.get("healer_harness_canary_interval_seconds", 21600),
        healer_app_runtime_stale_days=overrides.get("healer_app_runtime_stale_days", 14),
        healer_app_runtime_profiles=overrides.get("healer_app_runtime_profiles", {}),
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
        healer_infra_dlq_threshold=overrides.get("healer_infra_dlq_threshold", 8),
        healer_infra_dlq_cooldown_seconds=overrides.get("healer_infra_dlq_cooldown_seconds", 3600),
        healer_housekeeping_interval_seconds=overrides.get("healer_housekeeping_interval_seconds", 300),
        healer_processing_pr_maintenance_interval_seconds=overrides.get(
            "healer_processing_pr_maintenance_interval_seconds", 120
        ),
        healer_blocked_label_repair_interval_seconds=overrides.get(
            "healer_blocked_label_repair_interval_seconds", 600
        ),
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
    loop.tracker.publish_artifact_files.return_value = []
    loop.tracker.get_pr_ci_status_summary.return_value = {}
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
    loop.swarm = MagicMock()
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
    loop.swarms_by_backend = overrides.get("swarms_by_backend", {"exec": loop.swarm})
    loop.preflight_by_backend = overrides.get("preflight_by_backend", {"exec": loop.preflight})
    loop._sticky_runtime_status = overrides.get("_sticky_runtime_status", "")
    loop._sticky_runtime_issue_id = overrides.get("_sticky_runtime_issue_id", "")
    loop._last_harness_canary_at = overrides.get("_last_harness_canary_at", 0.0)
    loop._last_processing_pr_maintenance_at = overrides.get("_last_processing_pr_maintenance_at", 0.0)
    loop._processing_pr_maintenance_lock = threading.Lock()
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


def test_sync_blocked_issue_label_adds_label_for_blocked_issue(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="430",
        repo="owner/repo",
        title="Issue 430",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store)
    loop.tracker.get_issue.return_value = {
        "issue_id": "430",
        "state": "open",
        "labels": ["healer:ready"],
    }

    loop._sync_blocked_issue_label(issue_id="430", state="blocked")

    loop.tracker.add_issue_label.assert_called_once_with(issue_id="430", label="agent:blocked")
    loop.tracker.remove_issue_label.assert_not_called()


def test_reconcile_blocked_issue_labels_removes_stale_blocked_label(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="431",
        repo="owner/repo",
        title="Issue 431",
        body="",
        author="alice",
        labels=["healer:ready", "agent:blocked"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="431", state="resolved")

    loop = _make_loop(store)
    loop.tracker.get_issue.return_value = {
        "issue_id": "431",
        "state": "open",
        "labels": ["healer:ready", "agent:blocked"],
    }

    loop._reconcile_blocked_issue_labels()

    loop.tracker.remove_issue_label.assert_called_once_with(issue_id="431", label="agent:blocked")


def test_maybe_reconcile_blocked_issue_labels_respects_interval(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="432",
        repo="owner/repo",
        title="Issue 432",
        body="",
        author="alice",
        labels=["healer:ready", "agent:blocked"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="432", state="blocked")

    loop = _make_loop(store, healer_blocked_label_repair_interval_seconds=600)
    loop.tracker.get_issue.return_value = {
        "issue_id": "432",
        "state": "open",
        "labels": ["healer:ready", "agent:blocked"],
    }

    loop._maybe_reconcile_blocked_issue_labels()
    loop._maybe_reconcile_blocked_issue_labels()

    loop.tracker.get_issue.assert_called_once_with(issue_id="432")


def test_sync_outcome_issue_label_sets_target_and_clears_other_labels(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)

    loop._sync_outcome_issue_label(issue_id="499", label="healer:needs-clarification")

    loop.tracker.add_issue_label.assert_called_once_with(issue_id="499", label="healer:needs-clarification")
    removed = {call.kwargs.get("label") for call in loop.tracker.remove_issue_label.call_args_list}
    assert removed == {
        "healer:done-code",
        "healer:done-artifact",
        "healer:blocked-environment",
        "healer:retry-exhausted",
    }


def test_reconcile_outcome_issue_labels_backfills_artifact_done_label(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="4991",
        repo="owner/repo",
        title="Issue 4991",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="4991", state="pr_open")
    store.create_healer_attempt(
        attempt_id="ha_4991_1",
        issue_id="4991",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
        validation_profile="artifact_only",
    )
    store.finish_healer_attempt(
        attempt_id="ha_4991_1",
        state="pr_open",
        actual_diff_set=["docs/summary.md"],
        test_summary={"mode": "skipped_artifact_only"},
        verifier_summary={},
        failure_class="",
        failure_reason="",
    )

    loop = _make_loop(store)

    loop._reconcile_outcome_issue_labels()

    assert any(
        call.kwargs.get("label") == "healer:done-artifact"
        for call in loop.tracker.add_issue_label.call_args_list
    )


def test_reconcile_outcome_issue_labels_backfills_retry_exhausted_label(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="4992",
        repo="owner/repo",
        title="Issue 4992",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="4992",
        state="failed",
        last_failure_class="verifier_failed",
        last_failure_reason="Verifier failed repeatedly.",
    )
    loop = _make_loop(store)

    loop._reconcile_outcome_issue_labels()

    assert any(
        call.kwargs.get("label") == "healer:retry-exhausted"
        for call in loop.tracker.add_issue_label.call_args_list
    )


def test_process_claimed_issue_low_confidence_sets_needs_clarification_label(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="433",
        repo="owner/repo",
        title="Issue 433",
        body="Please investigate and report back.",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store)
    loop.tracker.get_issue.return_value = {
        "issue_id": "433",
        "state": "open",
        "labels": ["healer:ready"],
    }
    monkeypatch.setattr(
        "flow_healer.healer_loop.compile_task_spec",
        lambda issue_title, issue_body: HealerTaskSpec(
            task_kind="research",
            output_mode="artifact_file",
            output_targets=("docs/issue-433.md",),
            tool_policy="summary_only",
            validation_profile="artifact_only",
            parse_confidence=0.1,
        ),
    )

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("433")
    assert issue is not None
    assert issue["state"] == "needs_clarification"
    assert any(
        call.kwargs.get("label") == "healer:needs-clarification"
        for call in loop.tracker.add_issue_label.call_args_list
    )


def test_process_claimed_issue_baseline_validation_blocked_routes_to_needs_clarification(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="4331",
        repo="owner/repo",
        title="Issue 4331",
        body=(
            "Required code outputs:\n"
            "- e2e-apps/ruby-rails-web/app/controllers/dashboard_controller.rb\n\n"
            "app_target: ruby-rails-web\n"
            "entry_url: http://127.0.0.1:3101/dashboard\n"
            "browser_repro_mode: allow_success\n"
            "repro_steps:\n"
            "- goto /dashboard\n"
            "- expect_text Ruby Browser Signal R1\n\n"
            "Validation:\n"
            "- cd e2e-apps/ruby-rails-web && bundle exec rspec\n"
        ),
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store, healer_enable_review=False)
    workspace = tmp_path / "workspaces" / "issue-4331"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "4331", "state": "open", "labels": ["healer:ready"]}
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-4331")
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.run_attempt.return_value = SimpleNamespace(
        success=False,
        diff_paths=[],
        test_summary={
            "failed_tests": 1,
            "baseline_validation": {
                "unsafe_paths": ["tests/test_repo_health.py"],
                "follow_up_issue": {
                    "title": "Follow-up: unblock baseline validation for e2e-apps/ruby-rails-web",
                    "body": "Required code outputs:\n- tests/test_repo_health.py\n",
                },
            },
        },
        proposer_output="",
        workspace_status={},
        failure_class="baseline_validation_blocked",
        failure_reason=(
            "I can complete this, but the repo currently fails validation in file(s) outside the declared output "
            "targets: tests/test_repo_health.py. Approve widening scope to include that fix, or accept "
            "browser-evidence-only completion."
        ),
        failure_fingerprint="",
    )
    loop.tracker.create_issue.return_value = {
        "number": 987,
        "html_url": "https://github.com/owner/repo/issues/987",
        "state": "open",
    }
    monkeypatch.setattr(
        "flow_healer.healer_loop.compile_task_spec",
        lambda issue_title, issue_body: HealerTaskSpec(
            task_kind="edit",
            output_mode="patch",
            output_targets=("e2e-apps/ruby-rails-web/app/controllers/dashboard_controller.rb",),
            tool_policy="repo_only",
            validation_profile="code_change",
            execution_root="e2e-apps/ruby-rails-web",
            app_target="ruby-rails-web",
            entry_url="http://127.0.0.1:3111/dashboard",
            browser_repro_mode="allow_success",
            artifact_requirements=("screenshot: artifacts/ruby-dashboard.png",),
            validation_commands=("cd e2e-apps/ruby-rails-web && bundle exec rspec",),
        ),
    )

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("4331")
    attempts = store.list_healer_attempts(issue_id="4331")
    assert issue is not None
    assert issue["state"] == "needs_clarification"
    assert issue["last_failure_class"] == "baseline_validation_blocked"
    assert attempts[-1]["state"] == "needs_clarification"
    assert any(
        call.kwargs.get("label") == "healer:needs-clarification"
        for call in loop.tracker.add_issue_label.call_args_list
    )
    loop.tracker.create_issue.assert_called_once()
    posted_body = loop.tracker.add_issue_comment.call_args.kwargs["body"]
    assert "Approve widening scope" in posted_body
    assert "#987" in posted_body


def test_process_claimed_issue_baseline_validation_blocked_reuses_existing_follow_up_issue(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="4332",
        repo="owner/repo",
        title="Issue 4332",
        body=(
            "Required code outputs:\n"
            "- e2e-apps/ruby-rails-web/app/controllers/dashboard_controller.rb\n\n"
            "app_target: ruby-rails-web\n"
            "entry_url: http://127.0.0.1:3101/dashboard\n"
            "browser_repro_mode: allow_success\n"
            "repro_steps:\n"
            "- goto /dashboard\n"
            "- expect_text Ruby Browser Signal R1\n\n"
            "Validation:\n"
            "- cd e2e-apps/ruby-rails-web && bundle exec rspec\n"
        ),
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store, healer_enable_review=False)
    workspace = tmp_path / "workspaces" / "issue-4332"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "4332", "state": "open", "labels": ["healer:ready"]}
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-4332")
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.run_attempt.return_value = SimpleNamespace(
        success=False,
        diff_paths=[],
        test_summary={
            "failed_tests": 1,
            "baseline_validation": {
                "unsafe_paths": ["tests/test_repo_health.py"],
                "follow_up_issue": {
                    "title": "Follow-up: unblock baseline validation for e2e-apps/ruby-rails-web",
                    "body": "Required code outputs:\n- tests/test_repo_health.py\n",
                },
            },
        },
        proposer_output="",
        workspace_status={},
        failure_class="baseline_validation_blocked",
        failure_reason="Approve widening scope to include that fix.",
        failure_fingerprint="",
    )
    loop.tracker.find_open_issue_by_fingerprint.return_value = {
        "number": 988,
        "html_url": "https://github.com/owner/repo/issues/988",
        "title": "Follow-up: unblock baseline validation for e2e-apps/ruby-rails-web",
    }
    monkeypatch.setattr(
        "flow_healer.healer_loop.compile_task_spec",
        lambda issue_title, issue_body: HealerTaskSpec(
            task_kind="edit",
            output_mode="patch",
            output_targets=("e2e-apps/ruby-rails-web/app/controllers/dashboard_controller.rb",),
            tool_policy="repo_only",
            validation_profile="code_change",
            execution_root="e2e-apps/ruby-rails-web",
            app_target="ruby-rails-web",
            entry_url="http://127.0.0.1:3111/dashboard",
            browser_repro_mode="allow_success",
            artifact_requirements=("screenshot: artifacts/ruby-dashboard.png",),
            validation_commands=("cd e2e-apps/ruby-rails-web && bundle exec rspec",),
        ),
    )

    loop._process_claimed_issue(claimed)

    loop.tracker.create_issue.assert_not_called()
    posted_body = loop.tracker.add_issue_comment.call_args.kwargs["body"]
    assert "#988" in posted_body


def test_process_claimed_issue_baseline_validation_blocked_tolerates_follow_up_issue_creation_failure(
    tmp_path, monkeypatch
):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="4333",
        repo="owner/repo",
        title="Issue 4333",
        body=(
            "Required code outputs:\n"
            "- e2e-apps/ruby-rails-web/app/controllers/dashboard_controller.rb\n\n"
            "app_target: ruby-rails-web\n"
            "entry_url: http://127.0.0.1:3101/dashboard\n"
            "browser_repro_mode: allow_success\n"
            "repro_steps:\n"
            "- goto /dashboard\n"
            "- expect_text Ruby Browser Signal R1\n\n"
            "Validation:\n"
            "- cd e2e-apps/ruby-rails-web && bundle exec rspec\n"
        ),
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store, healer_enable_review=False)
    workspace = tmp_path / "workspaces" / "issue-4333"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "4333", "state": "open", "labels": ["healer:ready"]}
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-4333")
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.run_attempt.return_value = SimpleNamespace(
        success=False,
        diff_paths=[],
        test_summary={
            "failed_tests": 1,
            "baseline_validation": {
                "unsafe_paths": ["tests/test_repo_health.py"],
                "follow_up_issue": {
                    "title": "Follow-up: unblock baseline validation for e2e-apps/ruby-rails-web",
                    "body": "Required code outputs:\n- tests/test_repo_health.py\n",
                },
            },
        },
        proposer_output="",
        workspace_status={},
        failure_class="baseline_validation_blocked",
        failure_reason="Approve widening scope to include that fix.",
        failure_fingerprint="",
    )
    loop.tracker.find_open_issue_by_fingerprint.side_effect = RuntimeError("tracker lookup boom")
    loop.tracker.create_issue.side_effect = RuntimeError("tracker create boom")
    monkeypatch.setattr(
        "flow_healer.healer_loop.compile_task_spec",
        lambda issue_title, issue_body: HealerTaskSpec(
            task_kind="edit",
            output_mode="patch",
            output_targets=("e2e-apps/ruby-rails-web/app/controllers/dashboard_controller.rb",),
            tool_policy="repo_only",
            validation_profile="code_change",
            execution_root="e2e-apps/ruby-rails-web",
            app_target="ruby-rails-web",
            entry_url="http://127.0.0.1:3111/dashboard",
            browser_repro_mode="allow_success",
            artifact_requirements=("screenshot: artifacts/ruby-dashboard.png",),
            validation_commands=("cd e2e-apps/ruby-rails-web && bundle exec rspec",),
        ),
    )

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("4333")
    attempts = store.list_healer_attempts(issue_id="4333")
    assert issue is not None
    assert issue["state"] == "needs_clarification"
    assert issue["last_failure_class"] == "baseline_validation_blocked"
    assert attempts[-1]["state"] == "needs_clarification"
    posted_body = loop.tracker.add_issue_comment.call_args.kwargs["body"]
    assert "Approve widening scope" in posted_body
    assert "Follow-up issue:" not in posted_body


def test_clarification_reasons_strict_mode_requires_validation_and_outputs(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(
        store,
        healer_issue_contract_mode="strict",
        healer_parse_confidence_threshold=0.3,
    )
    spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="code_patch",
        output_targets=(),
        tool_policy="restricted_patch",
        validation_profile="code_change",
        parse_confidence=0.95,
        validation_commands=(),
    )

    reasons = loop._clarification_reasons_for_task_spec(task_spec=spec)

    assert reasons == ["missing_required_outputs", "missing_validation"]


def test_clarification_reasons_include_ambiguous_execution_root(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(
        store,
        healer_issue_contract_mode="lenient",
        healer_parse_confidence_threshold=0.3,
    )
    spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="code_patch",
        output_targets=(
            "e2e-smoke/node/src/app.js",
            "e2e-smoke/python/app/main.py",
        ),
        tool_policy="restricted_patch",
        validation_profile="code_change",
        parse_confidence=0.6,
        validation_commands=(),
        execution_root="",
    )

    reasons = loop._clarification_reasons_for_task_spec(task_spec=spec)

    assert reasons == ["ambiguous_execution_root"]


def test_clarification_reasons_include_validation_root_mismatch(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(
        store,
        healer_issue_contract_mode="lenient",
        healer_parse_confidence_threshold=0.3,
    )
    spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="code_patch",
        output_targets=("e2e-smoke/python/app/main.py",),
        tool_policy="restricted_patch",
        validation_profile="code_change",
        parse_confidence=0.8,
        validation_commands=("cd e2e-smoke/node && npm test -- --passWithNoTests",),
        execution_root="e2e-smoke/node",
    )

    reasons = loop._clarification_reasons_for_task_spec(task_spec=spec)

    assert reasons == ["validation_root_mismatch"]


def test_clarification_reasons_lenient_mode_only_uses_confidence_threshold(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(
        store,
        healer_issue_contract_mode="lenient",
        healer_parse_confidence_threshold=0.4,
    )
    spec = HealerTaskSpec(
        task_kind="docs",
        output_mode="artifact_file",
        output_targets=(),
        tool_policy="summary_only",
        validation_profile="artifact_only",
        parse_confidence=0.35,
        validation_commands=(),
    )

    reasons = loop._clarification_reasons_for_task_spec(task_spec=spec)

    assert reasons == ["low_confidence"]


def test_build_needs_clarification_comment_includes_contract_skeleton_for_root_and_validation_gaps(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="code_patch",
        output_targets=(
            "e2e-smoke/node/src/app.js",
            "e2e-smoke/node/test/app.test.js",
        ),
        tool_policy="restricted_patch",
        validation_profile="code_change",
        parse_confidence=0.6,
        validation_commands=(),
        execution_root="",
    )

    comment = loop._build_needs_clarification_comment(
        reasons=["missing_validation", "ambiguous_execution_root"],
        task_spec=spec,
    )

    assert "Suggested issue-contract skeleton" in comment
    assert "Execution root:" in comment
    assert "- e2e-smoke/node" in comment
    assert "Required code outputs:" in comment
    assert "- e2e-smoke/node/src/app.js" in comment
    assert "Validation:" in comment


def test_build_needs_clarification_comment_describes_validation_root_mismatch(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="code_patch",
        output_targets=("e2e-smoke/python/app/main.py",),
        tool_policy="restricted_patch",
        validation_profile="code_change",
        parse_confidence=0.8,
        validation_commands=("cd e2e-smoke/node && npm test -- --passWithNoTests",),
        execution_root="e2e-smoke/node",
    )

    comment = loop._build_needs_clarification_comment(
        reasons=["validation_root_mismatch"],
        task_spec=spec,
    )

    assert "Validation:` command root conflicts with the declared output targets" in comment
    assert "Execution root:" in comment
    assert "- e2e-smoke/python" in comment


def test_process_claimed_issue_posts_stronger_contract_remediation_comment(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="434",
        repo="owner/repo",
        title="Fix smoke fixture",
        body="Fix the smoke test under e2e-smoke/node.",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store, healer_issue_contract_mode="strict")
    loop.tracker.get_issue.return_value = {
        "issue_id": "434",
        "state": "open",
        "labels": ["healer:ready"],
    }
    posted: list[str] = []
    loop._post_issue_status = lambda issue_id, body: posted.append(body)
    monkeypatch.setattr(
        "flow_healer.healer_loop.compile_task_spec",
        lambda issue_title, issue_body: HealerTaskSpec(
            task_kind="fix",
            output_mode="code_patch",
            output_targets=("e2e-smoke/node/src/app.js",),
            tool_policy="restricted_patch",
            validation_profile="code_change",
            parse_confidence=0.8,
            validation_commands=(),
            execution_root="",
        ),
    )

    loop._process_claimed_issue(claimed)

    assert posted
    assert "Suggested issue-contract skeleton" in posted[0]
    assert "Validation:" in posted[0]
    assert "Execution root:" in posted[0]


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
    _, kwargs = loop.tracker.list_ready_issues.call_args
    assert kwargs["limit"] == 50


def test_failure_user_hint_avoids_required_outputs_advice_when_issue_is_structured():
    hint = _failure_user_hint(
        "empty_diff",
        issue_body=(
            "Required code outputs:\n"
            "- e2e-smoke/node/src/add.js\n"
            "- e2e-smoke/node/test/add.test.js\n\n"
            "Validation:\n"
            "- cd e2e-smoke/node && npm test -- --passWithNoTests\n"
        ),
    )

    assert "Required code outputs" not in hint
    assert "structured issue contract" in hint


def test_record_worker_heartbeat_emits_visible_pulse_event(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store, healer_pulse_interval_seconds=60)

    loop._record_worker_heartbeat(status="idle")

    events = store.list_healer_events(limit=5)
    runtime = store.get_runtime_status()

    assert events
    assert events[0]["event_type"] == "worker_pulse"
    assert events[0]["payload"]["status"] == "idle"
    assert runtime is not None
    assert runtime["status"] == "idle"
    assert runtime["heartbeat_at"]


def test_record_worker_heartbeat_logs_pulse_message(tmp_path, caplog):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store, healer_pulse_interval_seconds=60)
    caplog.set_level("INFO", logger="apple_flow.healer_loop")

    loop._record_worker_heartbeat(status="idle")

    assert "Worker pulse emitted" in caplog.text


def test_record_worker_heartbeat_allows_ten_second_pulse_interval(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store, healer_pulse_interval_seconds=10)

    loop._record_worker_heartbeat(status="idle")
    monkeypatch.setattr("flow_healer.healer_loop._minutes_since", lambda _timestamp: 11.0)
    loop._record_worker_heartbeat(status="idle")

    pulse_events = [
        event
        for event in store.list_healer_events(limit=10)
        if event.get("event_type") == "worker_pulse"
    ]
    assert len(pulse_events) >= 2


def test_record_worker_heartbeat_processing_infers_active_issue_id(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store, healer_pulse_interval_seconds=10, worker_id="worker-a")
    store.upsert_healer_issue(
        issue_id="919",
        repo="owner/repo",
        title="Issue 919",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None
    store.set_healer_issue_state(issue_id="919", state="running")

    loop._record_worker_heartbeat(status="processing", force_emit=True)

    events = store.list_healer_events(limit=5)
    assert events
    assert events[0]["event_type"] == "worker_pulse"
    assert events[0]["issue_id"] == "919"


def test_run_forever_emits_pulses_while_tick_in_progress(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store, healer_pulse_interval_seconds=0.02)

    stop_flag = {"value": False}
    pulse_statuses: list[str] = []

    monkeypatch.setattr("flow_healer.healer_loop._MIN_PULSE_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(loop, "_tick_once", lambda: time.sleep(0.06))
    monkeypatch.setattr(
        loop,
        "_record_worker_heartbeat",
        lambda *, status="idle", issue_id="", attempt_id="", force_emit=False: pulse_statuses.append(status),
    )

    async def _fake_sleep_until_next_tick(*, is_shutdown):
        stop_flag["value"] = True

    monkeypatch.setattr(loop, "_sleep_until_next_tick", _fake_sleep_until_next_tick)

    asyncio.run(loop.run_forever(lambda: stop_flag["value"]))

    assert pulse_statuses
    assert all(status in {"idle", "ticking"} for status in pulse_statuses)


def test_maybe_run_harness_canaries_skips_on_cold_start_when_persisted_run_is_recent(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.set_state("healer_harness_canary_last_run_at", datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"))
    loop = _make_loop(
        store,
        healer_harness_canary_interval_seconds=21600,
        healer_app_runtime_profiles={
            "node-next-web": {
                "name": "node-next-web",
                "start_command": "npm run dev",
                "working_directory": ".",
                "ready_url": "http://127.0.0.1:3000/",
            }
        },
    )

    called = {"value": False}

    def _should_not_run(*, profile):
        called["value"] = True
        return True

    monkeypatch.setattr(loop, "_run_harness_canary_for_profile", _should_not_run)

    summary = loop._maybe_run_harness_canaries()

    assert summary is None
    assert called["value"] is False


def test_record_worker_heartbeat_force_emits_swarm_stage_statuses(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store, healer_pulse_interval_seconds=60)

    loop._record_worker_heartbeat(status="swarm_analyzing", issue_id="811", attempt_id="hat_811", force_emit=True)
    loop._record_worker_heartbeat(status="swarm_repairing", issue_id="811", attempt_id="hat_811", force_emit=True)

    events = store.list_healer_events(limit=5)
    runtime = store.get_runtime_status()
    statuses = [str(event["payload"].get("status") or "") for event in events if event["event_type"] == "worker_pulse"]

    assert "swarm_analyzing" in statuses
    assert "swarm_repairing" in statuses
    assert runtime is not None
    assert runtime["status"] == "swarm_repairing"


def test_record_worker_heartbeat_keeps_swarm_status_sticky_for_processing(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(
        store,
        healer_pulse_interval_seconds=60,
        _sticky_runtime_status="swarm_analyzing",
        _sticky_runtime_issue_id="811",
    )

    loop._record_worker_heartbeat(status="processing", issue_id="811", attempt_id="hat_811", force_emit=True)

    events = store.list_healer_events(limit=5)
    runtime = store.get_runtime_status()

    assert events
    assert events[0]["event_type"] == "worker_pulse"
    assert events[0]["payload"]["status"] == "swarm_analyzing"
    assert runtime is not None
    assert runtime["status"] == "swarm_analyzing"


def test_lease_heartbeat_emits_processing_pulse(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store, lease_seconds=30, healer_pulse_interval_seconds=15)
    store.upsert_healer_issue(
        issue_id="777",
        repo="owner/repo",
        title="Issue 777",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id=loop.worker_id, lease_seconds=30, max_active_issues=1)
    assert claimed is not None
    stop_event = threading.Event()
    lease_lost = threading.Event()

    thread = threading.Thread(
        target=loop._lease_heartbeat,
        args=("777", stop_event, lease_lost),
        daemon=True,
    )
    thread.start()
    thread.join(timeout=16)
    stop_event.set()
    thread.join(timeout=2)

    events = store.list_healer_events(limit=5)
    assert any(event["event_type"] == "worker_pulse" and event["issue_id"] == "777" for event in events)


def test_backoff_or_fail_uses_explicit_issue_body_for_hint(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="900",
        repo="owner/repo",
        title="Issue 900",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )

    loop = _make_loop(store, healer_retry_budget=2, healer_backoff_initial_seconds=60)
    posted: list[str] = []
    loop._post_issue_status = lambda issue_id, body: posted.append(body)

    state = loop._backoff_or_fail(
        issue_id="900",
        attempt_no=1,
        failure_class="empty_diff",
        failure_reason="Proposer returned an empty diff fenced block.",
        issue_body=(
            "Required code outputs:\n"
            "- e2e-smoke/node/src/add.js\n"
            "- e2e-smoke/node/test/add.test.js\n\n"
            "Validation:\n"
            "- cd e2e-smoke/node && npm test -- --passWithNoTests\n"
        ),
    )

    assert state == "queued"
    assert posted
    assert "structured issue contract" in posted[0]


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


def test_ingest_ready_issues_archives_local_queued_issue_when_remote_closed(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="5034",
        repo="owner/repo",
        title="Issue 5034",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="5034", state="queued")

    loop = _make_loop(store)
    loop.tracker.list_ready_issues.return_value = []
    loop.tracker.get_issue.return_value = {"issue_id": "5034", "state": "closed", "labels": ["healer:ready"]}

    loop._ingest_ready_issues()

    issue = store.get_healer_issue("5034")
    assert issue is not None
    assert issue["state"] == "archived"
    assert issue["pr_state"] == "closed"
    assert issue["last_failure_class"] == ""
    assert issue["last_failure_reason"] == ""


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


def test_ingest_ready_issues_preserves_queued_ci_requeue_with_open_pr(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="5036",
        repo="owner/repo",
        title="Issue 5036",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="5036",
        state="queued",
        pr_number=236,
        pr_state="open",
        last_failure_class="ci_failed",
    )

    loop = _make_loop(store)
    loop.tracker.list_ready_issues.return_value = [
        HealerIssue(
            issue_id="5036",
            repo="owner/repo",
            title="Issue 5036 refreshed",
            body="new body",
            author="alice",
            labels=["healer:ready"],
            priority=5,
            html_url="https://example.test/issues/5036",
        )
    ]
    loop.tracker.find_pr_for_issue.return_value = PullRequestResult(
        number=236,
        state="open",
        html_url="https://github.com/owner/repo/pull/236",
    )

    loop._ingest_ready_issues()

    issue = store.get_healer_issue("5036")
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["pr_number"] == 236
    assert issue["pr_state"] == "open"


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


def test_process_claimed_issue_forces_preflight_refresh_for_app_execution_roots(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="5041a",
        repo="owner/repo",
        title="Ruby app issue",
        body="Validation: cd e2e-apps/ruby-rails-web && bundle exec rspec",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store)
    (tmp_path / "e2e-apps" / "ruby-rails-web").mkdir(parents=True)
    loop.repo_path = tmp_path
    loop.tracker.get_issue.return_value = {"issue_id": "5041a", "state": "open", "labels": ["healer:ready"]}
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.resolve_execution.return_value = SimpleNamespace(
        language_effective="ruby",
        language_detected="ruby",
        execution_root="e2e-apps/ruby-rails-web",
    )
    loop.preflight.ensure_language_ready.return_value = PreflightReport(
        language="ruby",
        execution_root="e2e-apps/ruby-rails-web",
        gate_mode="docker_only",
        status="failed",
        failure_class="validation_failed",
        summary="Preflight validation failed for ruby in e2e-apps/ruby-rails-web.",
        output_tail="bundle check failed",
        checked_at="2026-03-06 20:00:00",
        test_summary={"failed_tests": 1, "docker_full_status": "failed"},
    )

    loop._process_claimed_issue(claimed)

    loop.preflight.ensure_language_ready.assert_called_once_with(
        language="ruby",
        execution_root="e2e-apps/ruby-rails-web",
        force=True,
    )
    loop.runner.run_attempt.assert_not_called()


def test_process_claimed_issue_uses_execution_root_language_when_task_language_missing(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="5041b",
        repo="owner/repo",
        title="Ruby app issue missing language hints",
        body="Validation: cd e2e-apps/ruby-rails-web && bundle exec rspec",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store)
    (tmp_path / "e2e-apps" / "ruby-rails-web").mkdir(parents=True)
    loop.repo_path = tmp_path
    loop.tracker.get_issue.return_value = {"issue_id": "5041b", "state": "open", "labels": ["healer:ready"]}
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.resolve_execution.return_value = SimpleNamespace(
        language_effective="",
        language_detected="",
        execution_root="e2e-apps/ruby-rails-web",
    )
    loop.preflight.ensure_language_ready.return_value = PreflightReport(
        language="ruby",
        execution_root="e2e-apps/ruby-rails-web",
        gate_mode="docker_only",
        status="failed",
        failure_class="validation_failed",
        summary="Preflight validation failed for ruby in e2e-apps/ruby-rails-web.",
        output_tail="bundle exec rspec failed",
        checked_at="2026-03-06 20:00:00",
        test_summary={"failed_tests": 1},
    )

    loop._process_claimed_issue(claimed)

    loop.preflight.ensure_language_ready.assert_called_once_with(
        language="ruby",
        execution_root="e2e-apps/ruby-rails-web",
        force=True,
    )
    loop.runner.run_attempt.assert_not_called()


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


def test_process_claimed_issue_archives_already_satisfied_sql_validation_issue(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    body = (
        "Required code outputs:\n"
        "- e2e-apps/prosper-chat/supabase/migrations/20260301190615_15638062-0f7f-4cc7-96f5-79466e4cb26b.sql\n"
        "- e2e-apps/prosper-chat/supabase/assertions/schema_core.sql\n\n"
        "Validation:\n"
        "- cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh db\n"
    )
    store.upsert_healer_issue(
        issue_id="50433",
        repo="owner/repo",
        title="Prosper chat DB task 12: Prosper chat DB: base schema helper functions remain complete",
        body=body,
        author="alice",
        labels=["healer:ready", "area:db"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store)
    workspace = tmp_path / "workspaces" / "issue-50433"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "50433", "state": "open", "labels": ["healer:ready", "area:db"]}
    loop.tracker.close_issue.return_value = True
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-50433")
    loop.runner.resolve_execution.side_effect = [
        SimpleNamespace(language_effective="node", language_detected="node", execution_root="e2e-apps/prosper-chat"),
        SimpleNamespace(language_effective="node", language_detected="node", execution_root="e2e-apps/prosper-chat"),
    ]
    loop.runner.validate_workspace.return_value = {"failed_tests": 0}

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("50433")
    attempts = store.list_healer_attempts(issue_id="50433")
    assert issue is not None
    assert issue["state"] == "archived"
    assert issue["pr_state"] == "closed"
    assert issue["attempt_count"] == 1
    assert issue["last_failure_class"] == "already_satisfied"
    assert "already satisfies" in str(issue["last_failure_reason"] or "")
    assert len(attempts) == 1
    assert attempts[0]["state"] == "archived"
    loop.tracker.close_issue.assert_called_once_with(issue_id="50433")
    loop.runner.validate_workspace.assert_called_once()
    loop.runner.run_attempt.assert_not_called()
    comment_body = loop.tracker.add_issue_comment.call_args.kwargs["body"]
    assert "already satisfied" in comment_body.lower()
    assert "archived" in comment_body.lower()


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
    assert any(
        call.kwargs.get("label") == "healer:done-code"
        for call in loop.tracker.add_issue_label.call_args_list
    )


def test_process_claimed_issue_blocks_when_judgment_is_required_before_pr(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="50440",
        repo="owner/repo",
        title="Issue 50440",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store, healer_enable_review=False)
    workspace = tmp_path / "workspaces" / "issue-50440"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "50440", "state": "open", "labels": ["healer:ready"]}
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-50440")
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.dispatcher.upgrade_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.run_attempt.return_value = SimpleNamespace(
        success=True,
        diff_paths=["src/flow_healer/service.py"],
        test_summary={
            "failed_tests": 0,
            "judgment_reason_code": "product_ambiguity",
            "judgment_summary": "The issue leaves the expected banner behavior undefined.",
            "escalation_packet": {
                "reason_code": "product_ambiguity",
                "summary": "The issue leaves the expected banner behavior undefined.",
                "decision_needed": "Choose whether save should keep the banner visible or auto-dismiss it.",
                "attempted_actions": ["Validated the scoped contract.", "Ran the verifier."],
            },
        },
        proposer_output="Edited src/flow_healer/service.py",
        workspace_status={},
        failure_class="",
        failure_reason="",
        failure_fingerprint="",
    )
    loop.verifier.verify.return_value = SimpleNamespace(
        passed=True,
        summary="A product decision is required before behavior can be changed safely.",
        verdict="soft_fail",
        hard_failure=False,
        parse_error=False,
    )
    loop._commit_and_push = MagicMock(return_value=(True, "ok"))

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("50440")
    attempts = store.list_healer_attempts(issue_id="50440")
    assert issue is not None
    assert issue["state"] == "blocked"
    assert issue["last_failure_class"] == "judgment_required"
    assert "expected banner behavior undefined" in str(issue["last_failure_reason"] or "")
    assert attempts[-1]["state"] == "blocked"
    assert attempts[-1]["judgment_reason_code"] == "product_ambiguity"
    assert attempts[-1]["test_summary"]["escalation_packet"]["decision_needed"].startswith("Choose whether save")
    loop._commit_and_push.assert_not_called()
    loop.tracker.open_or_update_pr.assert_not_called()
    assert "Judgment required" in loop.tracker.add_issue_comment.call_args.kwargs["body"]


def test_process_claimed_issue_keeps_existing_pr_open_when_judgment_is_required(tmp_path):
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
    store.set_healer_issue_state(
        issue_id="50441",
        state="queued",
        pr_number=411,
        pr_state="open",
        feedback_context=(
            "PR review (approved) from @alice: Ship this as-is.\n\n"
            "PR review (changes_requested) from @bob: Please reverse the behavior before merge."
        ),
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
        test_summary={"failed_tests": 0},
        proposer_output="Edited src/flow_healer/service.py",
        workspace_status={},
        failure_class="",
        failure_reason="",
        failure_fingerprint="",
    )
    loop.verifier.verify.return_value = SimpleNamespace(
        passed=True,
        summary="Verifier passed.",
        verdict="pass",
        hard_failure=False,
        parse_error=False,
    )
    loop._commit_and_push = MagicMock(return_value=(True, "ok"))

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("50441")
    attempts = store.list_healer_attempts(issue_id="50441")
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert issue["pr_number"] == 411
    assert issue["last_failure_class"] == "judgment_required"
    assert attempts[-1]["state"] == "pr_open"
    assert attempts[-1]["judgment_reason_code"] == "conflicting_feedback"
    assert attempts[-1]["test_summary"]["escalation_packet"]["pr_number"] == 411
    loop._commit_and_push.assert_not_called()
    loop.tracker.open_or_update_pr.assert_not_called()


def test_process_claimed_issue_swarm_recovers_failed_run(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="50445",
        repo="owner/repo",
        title="Issue 50445",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(store, healer_enable_review=False, healer_swarm_enabled=True)
    workspace = tmp_path / "workspaces" / "issue-50445"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "50445", "state": "open", "labels": ["healer:ready"]}
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-50445")
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.dispatcher.upgrade_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.run_attempt.return_value = SimpleNamespace(
        success=False,
        diff_paths=[],
        test_summary={"failed_tests": 1, "failure_class": "tests_failed", "failure_reason": "boom"},
        proposer_output="Initial attempt failed",
        workspace_status={},
        failure_class="tests_failed",
        failure_reason="boom",
        failure_fingerprint="",
    )
    loop.verifier.verify.return_value = SimpleNamespace(
        passed=True,
        summary="ok",
        verdict="pass",
        hard_failure=False,
        parse_error=False,
    )
    posted: list[str] = []
    loop._post_issue_status = lambda issue_id, body: posted.append(body)
    loop._commit_and_push = MagicMock(return_value=(True, "ok"))
    loop.tracker.open_or_update_pr.return_value = PullRequestResult(
        number=245,
        state="open",
        html_url="https://github.com/owner/repo/pull/245",
    )
    expected_outcome = SwarmRecoveryOutcome(
        recovered=True,
        strategy="repair",
        summary="Swarm repaired the failing path.",
        analyzer_results=(),
        plan=SwarmRecoveryPlan(
            strategy="repair",
            summary="Swarm repaired the failing path.",
            root_cause="bad branch",
            edit_scope=("src/flow_healer/service.py",),
            targeted_tests=(),
            validation_focus=("service",),
        ),
        repair_output="Edited service",
        run_result=SimpleNamespace(
            success=True,
            diff_paths=["src/flow_healer/service.py"],
            test_summary={"failed_tests": 0},
            proposer_output="Edited service",
            workspace_status={},
            failure_class="",
            failure_reason="",
            failure_fingerprint="",
        ),
    )

    def _swarm_recover(**kwargs):
        telemetry = kwargs["telemetry_callback"]
        telemetry(
            "swarm_started",
            {"failure_class": kwargs["failure_class"], "failure_reason": kwargs["failure_reason"]},
        )
        telemetry(
            "swarm_role_completed",
            {"role": "failure-triager", "stage": "analysis", "success": True, "summary": "triaged failure"},
        )
        telemetry(
            "swarm_role_completed",
            {"role": "recovery-manager", "stage": "planning", "success": True, "summary": "repair plan"},
        )
        telemetry(
            "swarm_plan_ready",
            {
                "strategy": "repair",
                "summary": expected_outcome.summary,
                "root_cause": "bad branch",
                "edit_scope": ["src/flow_healer/service.py"],
                "targeted_tests": [],
                "validation_focus": ["service"],
            },
        )
        telemetry(
            "swarm_role_completed",
            {"role": "repair-executor", "stage": "repair", "success": True, "summary": "edited service"},
        )
        telemetry(
            "swarm_finished",
            {
                "recovered": True,
                "strategy": "repair",
                "summary": expected_outcome.summary,
                "failure_class": "",
                "failure_reason": "",
            },
        )
        return expected_outcome

    loop.swarm.recover.side_effect = _swarm_recover

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("50445")
    attempts = store.list_healer_attempts(issue_id="50445")
    events = store.list_healer_events(limit=20)
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert attempts[-1]["state"] == "pr_open"
    assert attempts[-1]["swarm_summary"]["cycles"][0]["recovered"] is True
    event_types = {event["event_type"] for event in events}
    assert {"swarm_started", "swarm_role_completed", "swarm_plan_ready", "swarm_finished"}.issubset(event_types)
    pulse_statuses = {
        str(event["payload"].get("status") or "")
        for event in events
        if event["event_type"] == "worker_pulse"
    }
    assert {"swarm_analyzing", "swarm_repairing"}.issubset(pulse_statuses)
    assert any("Swarm recovery started" in body for body in posted)
    assert any("Swarm recovery finished" in body for body in posted)
    loop.swarm.recover.assert_called_once()
    loop._commit_and_push.assert_called_once()


def test_process_claimed_issue_swarm_recovers_verifier_failure(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="50446",
        repo="owner/repo",
        title="Issue 50446",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(
        store,
        healer_enable_review=False,
        healer_swarm_enabled=True,
        healer_verifier_policy="required",
    )
    workspace = tmp_path / "workspaces" / "issue-50446"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "50446", "state": "open", "labels": ["healer:ready"]}
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-50446")
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.dispatcher.upgrade_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.run_attempt.return_value = SimpleNamespace(
        success=True,
        diff_paths=["src/flow_healer/service.py"],
        test_summary={"failed_tests": 0},
        proposer_output="Initial patch",
        workspace_status={},
        failure_class="",
        failure_reason="",
        failure_fingerprint="",
    )
    loop.verifier.verify.side_effect = [
        SimpleNamespace(
            passed=False,
            summary="Need stronger validation.",
            verdict="hard_fail",
            hard_failure=True,
            parse_error=False,
        ),
        SimpleNamespace(
            passed=True,
            summary="ok",
            verdict="pass",
            hard_failure=False,
            parse_error=False,
        ),
    ]
    posted: list[str] = []
    loop._post_issue_status = lambda issue_id, body: posted.append(body)
    loop._commit_and_push = MagicMock(return_value=(True, "ok"))
    loop.tracker.open_or_update_pr.return_value = PullRequestResult(
        number=246,
        state="open",
        html_url="https://github.com/owner/repo/pull/246",
    )
    expected_outcome = SwarmRecoveryOutcome(
        recovered=True,
        strategy="repair",
        summary="Swarm addressed the verifier concern.",
        analyzer_results=(),
        plan=SwarmRecoveryPlan(
            strategy="repair",
            summary="Swarm addressed the verifier concern.",
            root_cause="missing edge case",
            edit_scope=("src/flow_healer/service.py",),
            targeted_tests=(),
            validation_focus=("verifier",),
        ),
        repair_output="Edited service again",
        run_result=SimpleNamespace(
            success=True,
            diff_paths=["src/flow_healer/service.py"],
            test_summary={"failed_tests": 0},
            proposer_output="Edited service again",
            workspace_status={},
            failure_class="",
            failure_reason="",
            failure_fingerprint="",
        ),
    )

    def _swarm_recover(**kwargs):
        telemetry = kwargs["telemetry_callback"]
        telemetry(
            "swarm_started",
            {"failure_class": kwargs["failure_class"], "failure_reason": kwargs["failure_reason"]},
        )
        telemetry(
            "swarm_role_completed",
            {"role": "scope-guard", "stage": "analysis", "success": True, "summary": "scope safe"},
        )
        telemetry(
            "swarm_role_completed",
            {"role": "recovery-manager", "stage": "planning", "success": True, "summary": "repair plan"},
        )
        telemetry(
            "swarm_plan_ready",
            {
                "strategy": "repair",
                "summary": expected_outcome.summary,
                "root_cause": "missing edge case",
                "edit_scope": ["src/flow_healer/service.py"],
                "targeted_tests": [],
                "validation_focus": ["verifier"],
            },
        )
        telemetry(
            "swarm_role_completed",
            {"role": "repair-executor", "stage": "repair", "success": True, "summary": "edited service again"},
        )
        telemetry(
            "swarm_finished",
            {
                "recovered": True,
                "strategy": "repair",
                "summary": expected_outcome.summary,
                "failure_class": "",
                "failure_reason": "",
            },
        )
        return expected_outcome

    loop.swarm.recover.side_effect = _swarm_recover

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("50446")
    attempts = store.list_healer_attempts(issue_id="50446")
    events = store.list_healer_events(limit=20)
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert attempts[-1]["state"] == "pr_open"
    assert attempts[-1]["swarm_summary"]["cycles"][0]["strategy"] == "repair"
    assert any(event["event_type"] == "swarm_plan_ready" for event in events)
    assert any("Swarm recovery started" in body for body in posted)
    assert any("Swarm recovery finished" in body for body in posted)
    assert loop.verifier.verify.call_count == 2
    loop.swarm.recover.assert_called_once()
    loop._commit_and_push.assert_called_once()


def test_maybe_recover_with_swarm_skips_infra_failure_domain(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store, healer_swarm_enabled=True)
    workspace = tmp_path / "workspaces" / "issue-504461"
    workspace.mkdir(parents=True)
    issue = HealerIssue(
        issue_id="504461",
        repo="owner/repo",
        title="Issue 504461",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
        html_url="https://github.com/owner/repo/issues/504461",
    )
    task_spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="code_patch",
        output_targets=("src/flow_healer/service.py",),
        tool_policy="restricted_patch",
        validation_profile="code_change",
    )

    outcome = loop._maybe_recover_with_swarm(
        selected_backend="exec",
        selected_swarm=loop.swarm,
        selected_runner=loop.runner,
        issue=issue,
        attempt_id="hat_504461",
        attempt_no=1,
        task_spec=task_spec,
        learned_context="",
        feedback_context="",
        failure_class="tests_failed",
        failure_reason="Cannot connect to the Docker daemon at unix:///var/run/docker.sock.",
        proposer_output="",
        test_summary={"failed_tests": 1},
        verifier_summary={},
        workspace_status={},
        workspace=workspace,
        targeted_tests=[],
    )

    assert outcome is None
    loop.swarm.recover.assert_not_called()
    assert store.get_state("healer_swarm_skipped_domain") == "1"
    assert store.get_state("healer_swarm_skipped_domain_infra") == "1"
    events = store.list_healer_events(issue_id="504461", limit=5)
    assert events
    assert events[0]["event_type"] == "swarm_skipped_domain"
    assert events[0]["payload"]["failure_domain"] == "infra"


def test_maybe_recover_with_swarm_runs_for_code_failure_domain(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store, healer_swarm_enabled=True)
    workspace = tmp_path / "workspaces" / "issue-504462"
    workspace.mkdir(parents=True)
    issue = HealerIssue(
        issue_id="504462",
        repo="owner/repo",
        title="Issue 504462",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
        html_url="https://github.com/owner/repo/issues/504462",
    )
    task_spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="code_patch",
        output_targets=("src/flow_healer/service.py",),
        tool_policy="restricted_patch",
        validation_profile="code_change",
    )
    loop.swarm.recover.return_value = SwarmRecoveryOutcome(
        recovered=False,
        strategy="repair",
        summary="Could not recover",
        analyzer_results=(),
        plan=SwarmRecoveryPlan(
            strategy="repair",
            summary="Could not recover",
            root_cause="assertion mismatch",
            edit_scope=("src/flow_healer/service.py",),
            targeted_tests=(),
            validation_focus=("service",),
        ),
        failure_class="tests_failed",
        failure_reason="AssertionError",
    )

    outcome = loop._maybe_recover_with_swarm(
        selected_backend="exec",
        selected_swarm=loop.swarm,
        selected_runner=loop.runner,
        issue=issue,
        attempt_id="hat_504462",
        attempt_no=1,
        task_spec=task_spec,
        learned_context="",
        feedback_context="",
        failure_class="tests_failed",
        failure_reason="AssertionError: expected 200 got 500",
        proposer_output="",
        test_summary={"failed_tests": 1},
        verifier_summary={},
        workspace_status={},
        workspace=workspace,
        targeted_tests=[],
    )

    assert outcome is not None
    loop.swarm.recover.assert_called_once()
    assert store.get_state("healer_swarm_runs") == "1"
    assert store.get_state("healer_swarm_unrecovered") == "1"
    assert store.get_state("healer_swarm_skipped_domain") in {None, ""}


def test_maybe_recover_with_native_codex_skips_non_exec_backend(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store, healer_codex_native_multi_agent_enabled=True)
    workspace = tmp_path / "workspaces" / "issue-504463"
    workspace.mkdir(parents=True)
    issue = HealerIssue(
        issue_id="504463",
        repo="owner/repo",
        title="Issue 504463",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
        html_url="https://github.com/owner/repo/issues/504463",
    )
    task_spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="code_patch",
        output_targets=("src/flow_healer/service.py",),
        tool_policy="restricted_patch",
        validation_profile="code_change",
    )

    outcome = loop._maybe_recover_with_native_codex(
        selected_backend="app_server",
        selected_runner=loop.runner,
        issue=issue,
        task_spec=task_spec,
        learned_context="",
        feedback_context="",
        failure_class="tests_failed",
        failure_reason="AssertionError: expected 200 got 500",
        workspace=workspace,
        targeted_tests=[],
    )

    assert outcome is None
    loop.runner.run_attempt.assert_not_called()
    assert store.get_state("healer_codex_native_multi_agent_skipped_backend") == "1"


def test_process_claimed_issue_tries_native_codex_recovery_before_swarm(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="504464",
        repo="owner/repo",
        title="Issue 504464",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(
        store,
        healer_enable_review=False,
        healer_codex_native_multi_agent_enabled=True,
        healer_swarm_enabled=True,
    )
    workspace = tmp_path / "workspaces" / "issue-504464"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "504464", "state": "open", "labels": ["healer:ready"]}
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-504464")
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.dispatcher.upgrade_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.run_attempt.return_value = SimpleNamespace(
        success=False,
        diff_paths=[],
        test_summary={"failed_tests": 1},
        proposer_output="Initial attempt failed",
        workspace_status={},
        failure_class="tests_failed",
        failure_reason="AssertionError",
        failure_fingerprint="",
    )
    call_order: list[str] = []
    loop._maybe_recover_with_native_codex = MagicMock(
        side_effect=lambda **kwargs: call_order.append("native") or None
    )
    expected_outcome = SwarmRecoveryOutcome(
        recovered=True,
        strategy="repair",
        summary="Swarm repaired the failing path.",
        analyzer_results=(),
        plan=SwarmRecoveryPlan(
            strategy="repair",
            summary="Swarm repaired the failing path.",
            root_cause="bad branch",
            edit_scope=("src/flow_healer/service.py",),
            targeted_tests=(),
            validation_focus=("service",),
        ),
        repair_output="Edited service",
        run_result=SimpleNamespace(
            success=True,
            diff_paths=["src/flow_healer/service.py"],
            test_summary={"failed_tests": 0},
            proposer_output="Edited service",
            workspace_status={},
            failure_class="",
            failure_reason="",
            failure_fingerprint="",
        ),
    )
    loop._maybe_recover_with_swarm = MagicMock(
        side_effect=lambda **kwargs: call_order.append("swarm") or expected_outcome
    )
    loop._commit_and_push = MagicMock(return_value=(True, "ok"))
    loop.tracker.open_or_update_pr.return_value = PullRequestResult(
        number=246,
        state="open",
        html_url="https://github.com/owner/repo/pull/246",
    )
    loop.verifier.verify.return_value = SimpleNamespace(
        passed=True,
        summary="ok",
        verdict="pass",
        hard_failure=False,
        parse_error=False,
    )

    loop._process_claimed_issue(claimed)

    assert call_order == ["native", "swarm"]
    loop._maybe_recover_with_native_codex.assert_called_once()


def test_process_claimed_issue_swarm_infra_pause_requeues_with_infra_failure_class(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="50447",
        repo="owner/repo",
        title="Issue 50447",
        body="Fix e2e-apps/prosper-chat/supabase/assertions/subscription_visibility.sql",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None

    loop = _make_loop(
        store,
        healer_enable_review=False,
        healer_swarm_enabled=True,
        healer_infra_dlq_cooldown_seconds=1800,
    )
    workspace = tmp_path / "workspaces" / "issue-50447"
    workspace.mkdir(parents=True)
    loop.tracker.get_issue.return_value = {"issue_id": "50447", "state": "open", "labels": ["healer:ready"]}
    loop.workspace_manager.ensure_workspace.return_value = SimpleNamespace(path=workspace, branch="healer/issue-50447")
    loop.dispatcher.acquire_prediction_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.dispatcher.upgrade_locks.return_value = SimpleNamespace(acquired=True, reason="")
    loop.runner.run_attempt.return_value = SimpleNamespace(
        success=False,
        diff_paths=["e2e-apps/prosper-chat/supabase/assertions/subscription_visibility.sql"],
        test_summary={"failed_tests": 1},
        proposer_output="Initial attempt failed",
        workspace_status={},
        failure_class="tests_failed",
        failure_reason="Failed tests=1 exceeds cap=0",
        failure_fingerprint="",
    )
    loop._post_issue_status = MagicMock()
    loop.swarm.recover.return_value = SwarmRecoveryOutcome(
        recovered=False,
        strategy="infra_pause",
        summary="Cannot connect to the Docker daemon while launching validator containers.",
        analyzer_results=(),
        plan=SwarmRecoveryPlan(
            strategy="infra_pause",
            summary="Cannot connect to the Docker daemon while launching validator containers.",
            root_cause="docker daemon unavailable",
            edit_scope=("e2e-apps/prosper-chat/supabase/assertions/subscription_visibility.sql",),
            targeted_tests=(),
            validation_focus=("supabase",),
        ),
        failure_class="tests_failed",
        failure_reason="Cannot connect to the Docker daemon at unix:///var/run/docker.sock.",
    )

    loop._process_claimed_issue(claimed)

    issue = store.get_healer_issue("50447")
    attempts = store.list_healer_attempts(issue_id="50447")
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["last_failure_class"] == "infra_pause"
    assert issue["backoff_until"] == store.get_state("healer_infra_pause_until")
    assert attempts[-1]["failure_class"] == "infra_pause"
    assert store.get_state("healer_infra_pause_reason").startswith("infra_pause:")
    loop.swarm.recover.assert_called_once()


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


def test_claim_is_actionable_allows_queued_repair_on_existing_open_pr(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="505",
        repo="owner/repo",
        title="Repair failing CI on existing PR",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="505",
        state="queued",
        pr_number=250,
        pr_state="open",
        last_failure_class="ci_failed",
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-a", lease_seconds=180, max_active_issues=1)
    assert claimed is not None
    loop = _make_loop(store)
    loop.tracker.get_issue.return_value = {
        "issue_id": "505",
        "state": "open",
        "labels": ["healer:ready"],
    }
    loop.tracker.find_pr_for_issue.return_value = PullRequestResult(
        number=250,
        state="open",
        html_url="https://github.com/owner/repo/pull/250",
    )

    issue = HealerIssue(
        issue_id="505",
        repo="owner/repo",
        title="Repair failing CI on existing PR",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
        html_url="https://example.test/issues/505",
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
    store.set_healer_issue_state(
        issue_id="6013",
        state="pr_open",
        pr_number=130,
        pr_state="open",
        ci_status_summary={"overall_state": "success"},
    )
    store.create_healer_attempt(
        attempt_id="ha_6013_1",
        issue_id="6013",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="ha_6013_1",
        state="pr_open",
        actual_diff_set=["src/demo.py"],
        test_summary={"promotion_state": "promotion_ready"},
        verifier_summary={},
    )

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


def test_auto_merge_open_pr_skips_when_ci_is_pending(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="60131",
        repo="owner/repo",
        title="Issue 60131",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="60131",
        state="pr_open",
        pr_number=230,
        pr_state="open",
        ci_status_summary={"overall_state": "pending", "pending_contexts": ["CI"]},
    )
    store.create_healer_attempt(
        attempt_id="ha_60131_1",
        issue_id="60131",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="ha_60131_1",
        state="pr_open",
        actual_diff_set=["src/demo.py"],
        test_summary={"promotion_state": "promotion_ready"},
        verifier_summary={},
    )

    loop = _make_loop(store)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=230,
        state="open",
        html_url="https://github.com/owner/repo/pull/230",
        mergeable_state="clean",
        author="healer-service",
    )

    merged = loop._auto_merge_open_prs()

    assert merged == 0
    loop.tracker.merge_pr.assert_not_called()


def test_auto_merge_open_pr_refreshes_stale_pending_ci_before_merging(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="60131b",
        repo="owner/repo",
        title="Issue 60131b",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="60131b",
        state="pr_open",
        pr_number=2301,
        pr_state="open",
        ci_status_summary={"overall_state": "pending", "pending_contexts": ["CI"]},
    )
    store.create_healer_attempt(
        attempt_id="ha_60131b_1",
        issue_id="60131b",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="ha_60131b_1",
        state="pr_open",
        actual_diff_set=["src/demo.py"],
        test_summary={"promotion_state": "promotion_ready"},
        verifier_summary={},
    )

    loop = _make_loop(store)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=2301,
        state="open",
        html_url="https://github.com/owner/repo/pull/2301",
        mergeable_state="clean",
        author="healer-service",
        head_sha="abc123",
    )
    loop.tracker.get_pr_ci_status_summary.return_value = {
        "overall_state": "success",
        "head_sha": "abc123",
    }
    loop.tracker.merge_pr.return_value = True

    merged = loop._auto_merge_open_prs()

    assert merged == 1
    loop.tracker.get_pr_ci_status_summary.assert_called_once_with(pr_number=2301, head_sha="abc123")
    loop.tracker.merge_pr.assert_called_once_with(pr_number=2301, merge_method="squash")


def test_maybe_maintain_open_prs_during_processing_runs_reconcile_and_pr_actions(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="60131c",
        repo="owner/repo",
        title="Issue 60131c",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="60131c",
        state="pr_open",
        pr_number=2310,
        pr_state="open",
        ci_status_summary={"overall_state": "pending", "pending_contexts": ["CI"]},
    )

    loop = _make_loop(store)
    loop._reconcile_pr_outcomes = MagicMock()
    loop._requeue_ci_failed_prs = MagicMock()
    loop._auto_approve_open_prs = MagicMock()
    loop._auto_merge_open_prs = MagicMock(return_value=0)
    loop.tracker.viewer_login.return_value = "healer-service"

    loop._maybe_maintain_open_prs_during_processing(issue_id="60131c", force=True)

    loop._reconcile_pr_outcomes.assert_called_once()
    _, reconcile_kwargs = loop._reconcile_pr_outcomes.call_args
    assert reconcile_kwargs["force_refresh"] is True
    loop._requeue_ci_failed_prs.assert_called_once()
    loop._auto_approve_open_prs.assert_called_once()
    loop._auto_merge_open_prs.assert_called_once()


def test_maybe_maintain_open_prs_during_processing_respects_interval(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="60131d",
        repo="owner/repo",
        title="Issue 60131d",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="60131d",
        state="pr_open",
        pr_number=2311,
        pr_state="open",
        ci_status_summary={"overall_state": "pending", "pending_contexts": ["CI"]},
    )

    loop = _make_loop(
        store,
        healer_processing_pr_maintenance_interval_seconds=3600,
    )
    loop._reconcile_pr_outcomes = MagicMock()
    loop._requeue_ci_failed_prs = MagicMock()
    loop._auto_approve_open_prs = MagicMock()
    loop._auto_merge_open_prs = MagicMock(return_value=0)
    loop.tracker.viewer_login.return_value = "healer-service"

    loop._maybe_maintain_open_prs_during_processing(issue_id="60131d")
    loop._maybe_maintain_open_prs_during_processing(issue_id="60131d")

    loop._reconcile_pr_outcomes.assert_called_once()


def test_auto_merge_open_pr_skips_when_local_promotion_is_blocked(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="60132",
        repo="owner/repo",
        title="Issue 60132",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="60132",
        state="pr_open",
        pr_number=231,
        pr_state="open",
        ci_status_summary={"overall_state": "success"},
    )
    store.create_healer_attempt(
        attempt_id="ha_60132_1",
        issue_id="60132",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="ha_60132_1",
        state="pr_open",
        actual_diff_set=["src/demo.py"],
        test_summary={"promotion_state": "merge_blocked"},
        verifier_summary={},
    )

    loop = _make_loop(store)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=231,
        state="open",
        html_url="https://github.com/owner/repo/pull/231",
        mergeable_state="clean",
        author="healer-service",
    )

    merged = loop._auto_merge_open_prs()

    assert merged == 0
    loop.tracker.merge_pr.assert_not_called()


def test_auto_merge_open_pr_skips_when_browser_artifact_proof_is_missing(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="60133",
        repo="owner/repo",
        title="Issue 60133",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="60133",
        state="pr_open",
        pr_number=232,
        pr_state="open",
        ci_status_summary={"overall_state": "success"},
    )
    store.create_healer_attempt(
        attempt_id="ha_60133_1",
        issue_id="60133",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="ha_60133_1",
        state="pr_open",
        actual_diff_set=["src/demo.py"],
        test_summary={
            "promotion_state": "promotion_ready",
            "browser_evidence_required": True,
            "artifact_proof_ready": False,
        },
        verifier_summary={},
    )

    loop = _make_loop(store)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=232,
        state="open",
        html_url="https://github.com/owner/repo/pull/232",
        mergeable_state="clean",
        author="healer-service",
    )

    merged = loop._auto_merge_open_prs()

    assert merged == 0
    loop.tracker.merge_pr.assert_not_called()


def test_auto_merge_open_pr_skips_when_judgment_is_required(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="60134",
        repo="owner/repo",
        title="Issue 60134",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="60134",
        state="pr_open",
        pr_number=233,
        pr_state="open",
        ci_status_summary={"overall_state": "success"},
    )
    store.create_healer_attempt(
        attempt_id="ha_60134_1",
        issue_id="60134",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="ha_60134_1",
        state="pr_open",
        actual_diff_set=["src/demo.py"],
        test_summary={"promotion_state": "promotion_ready"},
        verifier_summary={},
        judgment_reason_code="product_ambiguity",
    )

    loop = _make_loop(store)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=233,
        state="open",
        html_url="https://github.com/owner/repo/pull/233",
        mergeable_state="clean",
        author="healer-service",
    )

    merged = loop._auto_merge_open_prs()

    assert merged == 0
    loop.tracker.merge_pr.assert_not_called()


def test_build_judgment_assessment_uses_explicit_packet_from_test_summary(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    task_spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="patch",
        output_targets=("src/demo.py",),
        tool_policy="repo_only",
        validation_profile="code_change",
    )

    assessment = loop._build_judgment_assessment(
        task_spec=task_spec,
        feedback_context="",
        test_summary={
            "judgment_reason_code": "product_ambiguity",
            "judgment_summary": "The issue supports two valid UX outcomes.",
            "escalation_packet": {
                "reason_code": "product_ambiguity",
                "summary": "The issue supports two valid UX outcomes.",
                "decision_needed": "Choose whether the banner should stay persistent or dismiss after save.",
                "attempted_actions": ["Validated the current issue contract."],
                "evidence_links": [{"label": "failure_screenshot", "href": "https://example.test/failure.png"}],
            },
        },
        verifier_summary={"summary": "A human decision is required before mutating behavior."},
        workspace_status={},
        pr_number=0,
    )

    assert assessment.requires_human is True
    assert assessment.reason_code == "product_ambiguity"
    assert assessment.summary == "The issue supports two valid UX outcomes."
    assert assessment.packet["decision_needed"] == (
        "Choose whether the banner should stay persistent or dismiss after save."
    )


def test_build_judgment_assessment_detects_conflicting_feedback_reviews(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    task_spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="patch",
        output_targets=("src/demo.py",),
        tool_policy="repo_only",
        validation_profile="code_change",
    )

    assessment = loop._build_judgment_assessment(
        task_spec=task_spec,
        feedback_context=(
            "PR review (approved) from @alice: Ship this as-is.\n\n"
            "PR review (changes_requested) from @bob: Please reverse the behavior before merge."
        ),
        test_summary={"failed_tests": 0},
        verifier_summary={"summary": "Verifier passed."},
        workspace_status={},
        pr_number=222,
    )

    assert assessment.requires_human is True
    assert assessment.reason_code == "conflicting_feedback"
    assert "Conflicting human review states" in assessment.summary
    assert assessment.packet["pr_number"] == 222


def test_build_judgment_assessment_ignores_superseded_review_state_from_same_author(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    task_spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="patch",
        output_targets=("src/demo.py",),
        tool_policy="repo_only",
        validation_profile="code_change",
    )

    assessment = loop._build_judgment_assessment(
        task_spec=task_spec,
        feedback_context=(
            "PR review (changes_requested) from @reviewer: Please reverse the behavior.\n\n"
            "PR review (approved) from @reviewer: The follow-up looks good now."
        ),
        test_summary={"failed_tests": 0},
        verifier_summary={"summary": "Verifier passed."},
        workspace_status={},
        pr_number=222,
    )

    assert assessment.requires_human is False


def test_build_judgment_assessment_uses_summary_field_from_dict_shaped_judgment_summary(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    task_spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="patch",
        output_targets=("src/demo.py",),
        tool_policy="repo_only",
        validation_profile="code_change",
    )

    assessment = loop._build_judgment_assessment(
        task_spec=task_spec,
        feedback_context="",
        test_summary={
            "judgment_reason_code": "product_ambiguity",
            "judgment_summary": {
                "reason_code": "product_ambiguity",
                "summary": "Use the structured summary text instead of the dict repr.",
            },
        },
        verifier_summary={"summary": "A product decision is required before mutating behavior."},
        workspace_status={},
        pr_number=0,
    )

    assert assessment.requires_human is True
    assert assessment.summary == "Use the structured summary text instead of the dict repr."


def test_build_judgment_comment_includes_decision_evidence_and_pr(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)

    body = loop._build_judgment_comment(
        {
            "reason_code": "product_ambiguity",
            "summary": "The issue supports two valid UX outcomes.",
            "decision_needed": "Choose the desired post-save banner behavior.",
            "attempted_actions": ["Validated the issue contract.", "Ran the scoped verifier."],
            "evidence_links": [{"label": "failure_screenshot", "href": "https://example.test/failure.png"}],
            "pr_number": 233,
        }
    )

    assert "Judgment required" in body
    assert "Reason code: `product_ambiguity`" in body
    assert "Choose the desired post-save banner behavior." in body
    assert "failure_screenshot" in body
    assert "PR: `#233`" in body


def test_with_promotion_transitions_adds_remote_states_for_green_pr(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)

    summary = loop._with_promotion_transitions(
        test_summary={
            "promotion_state": "promotion_ready",
            "promotion_transitions": ["local_validated"],
        },
        issue_state="pr_open",
        pr_number=450,
        ci_status_summary={"overall_state": "success"},
    )

    assert summary["promotion_transitions"] == [
        "local_validated",
        "pr_open",
        "ci_green",
        "promotion_ready",
    ]


def test_with_promotion_transitions_marks_merge_blocked_for_missing_browser_artifacts(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)

    summary = loop._with_promotion_transitions(
        test_summary={
            "promotion_state": "promotion_ready",
            "browser_evidence_required": True,
            "artifact_proof_ready": False,
            "promotion_transitions": ["failure_artifacts_captured"],
        },
        issue_state="pr_open",
        pr_number=451,
        ci_status_summary={"overall_state": "success"},
    )

    assert summary["promotion_transitions"] == [
        "failure_artifacts_captured",
        "pr_open",
        "ci_green",
        "merge_blocked",
    ]


def test_with_promotion_transitions_keeps_pending_approval_out_of_promotion_ready(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)

    summary = loop._with_promotion_transitions(
        test_summary={
            "promotion_state": "promotion_ready",
            "promotion_transitions": ["local_validated"],
        },
        issue_state="pr_pending_approval",
        pr_number=452,
        ci_status_summary={"overall_state": "success"},
    )

    assert summary["promotion_transitions"] == [
        "local_validated",
        "pr_open",
        "ci_green",
    ]
    assert "promotion_ready" not in summary["promotion_transitions"]


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


def test_ingest_ready_issues_keeps_non_conflict_blocked_issue_blocked_when_contract_unchanged(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="60311",
        repo="owner/repo",
        title="Issue 60311",
        body="Keep current contract",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="60311", state="blocked", pr_state="closed")

    loop = _make_loop(store)
    loop.tracker.list_ready_issues.return_value = [
        HealerIssue(
            issue_id="60311",
            repo="owner/repo",
            title="Issue 60311",
            body="Keep current contract",
            author="alice",
            labels=["healer:ready"],
            priority=5,
            html_url="https://example.test/issues/60311",
        )
    ]

    loop._ingest_ready_issues()

    issue = store.get_healer_issue("60311")
    assert issue is not None
    assert issue["state"] == "blocked"
    assert issue["pr_state"] == "closed"
    loop.tracker.add_issue_reaction.assert_not_called()


def test_ingest_ready_issues_requeues_blocked_issue_when_contract_changes(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="60312",
        repo="owner/repo",
        title="Issue 60312",
        body="Original body",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="60312",
        state="blocked",
        pr_state="closed",
        last_failure_class="tests_failed",
        last_failure_reason="deterministic failure",
    )

    loop = _make_loop(store)
    loop.tracker.list_ready_issues.return_value = [
        HealerIssue(
            issue_id="60312",
            repo="owner/repo",
            title="Issue 60312",
            body="Updated body with new validation",
            author="alice",
            labels=["healer:ready"],
            priority=5,
            html_url="https://example.test/issues/60312",
        )
    ]

    loop._ingest_ready_issues()

    issue = store.get_healer_issue("60312")
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["last_failure_class"] == ""
    assert issue["last_failure_reason"] == ""


def test_ingest_ready_issues_skips_pr_discovery_for_existing_queued_issue(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="60315",
        repo="owner/repo",
        title="Issue 60315",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )

    loop = _make_loop(store)
    loop.tracker.list_ready_issues.return_value = [
        HealerIssue(
            issue_id="60315",
            repo="owner/repo",
            title="Issue 60315",
            body="Fix src/flow_healer/service.py",
            author="alice",
            labels=["healer:ready"],
            priority=5,
            html_url="https://example.test/issues/60315",
        )
    ]

    loop._ingest_ready_issues()

    loop.tracker.find_pr_for_issue.assert_not_called()


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


def test_lease_heartbeat_runs_open_pr_maintenance_hook(tmp_path):
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
    loop._maybe_maintain_open_prs_during_processing = MagicMock()

    loop._lease_heartbeat("703", stop_event, lease_lost)  # type: ignore[arg-type]

    loop._maybe_maintain_open_prs_during_processing.assert_called_once_with(issue_id="703")
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
    loop.store.get_healer_issue.return_value = {"issue_id": "704", "state": "running"}

    loop._lease_heartbeat("704", stop_event, lease_lost)  # type: ignore[arg-type]

    assert lease_lost.is_set() is True


def test_lease_heartbeat_exits_quietly_after_issue_leaves_active_lease_states(tmp_path, caplog):
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
    loop.store.get_healer_issue.return_value = {"issue_id": "705", "state": "pr_open"}

    with caplog.at_level("WARNING"):
        loop._lease_heartbeat("705", stop_event, lease_lost)  # type: ignore[arg-type]

    assert lease_lost.is_set() is False
    assert "Lease heartbeat stopped for issue #705" not in caplog.text


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
    assert store.get_state("healer_failure_domain_total") == "1"
    assert store.get_state("healer_failure_domain_code") == "1"
    assert store.get_state("healer_retry_playbook_total") == "1"
    assert store.get_state("healer_retry_playbook_class_tests_failed") == "1"
    assert store.get_state("healer_retry_playbook_domain_code") == "1"
    assert store.get_state("healer_retry_playbook_strategy_adaptive_failure_strategy") == "1"
    assert store.get_state("healer_retry_playbook_last_failure_class") == "tests_failed"
    assert store.get_state("healer_retry_playbook_last_strategy") == "adaptive_failure_strategy"
    assert int(store.get_state("healer_retry_playbook_last_backoff_seconds") or 0) >= 15
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
    assert any(
        call.kwargs.get("label") == "healer:retry-exhausted"
        for call in loop.tracker.add_issue_label.call_args_list
    )


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


def test_backoff_or_fail_uses_reason_to_classify_infra_domain(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="3030",
        repo="owner/repo",
        title="Issue 3030",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store, healer_retry_budget=1, healer_backoff_initial_seconds=60)

    state = loop._backoff_or_fail(
        issue_id="3030",
        attempt_no=1,
        failure_class="tests_failed",
        failure_reason="Cannot connect to the Docker daemon at unix:///var/run/docker.sock.",
    )
    issue = store.get_healer_issue("3030")
    assert issue is not None
    assert state == "queued"
    assert issue["state"] == "queued"
    assert store.get_state("healer_failure_domain_total") == "1"
    assert store.get_state("healer_failure_domain_infra") == "1"


def test_backoff_or_fail_infra_pause_sets_long_pause_and_queue_backoff(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="3031",
        repo="owner/repo",
        title="Issue 3031",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    loop = _make_loop(store, healer_retry_budget=1, healer_infra_dlq_cooldown_seconds=1800)

    state = loop._backoff_or_fail(
        issue_id="3031",
        attempt_no=4,
        failure_class="infra_pause",
        failure_reason="local Supabase stack would not start",
    )
    issue = store.get_healer_issue("3031")

    assert state == "queued"
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["last_failure_class"] == "infra_pause"
    assert issue["backoff_until"] == store.get_state("healer_infra_pause_until")
    assert store.get_state("healer_infra_pause_reason").startswith("infra_pause:")
    assert any(
        call.kwargs.get("label") == "healer:blocked-environment"
        for call in loop.tracker.add_issue_label.call_args_list
    )


def test_infra_pause_auto_clears_when_toolchain_reason_is_resolved(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    until = (datetime.now(UTC) + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    store.set_states(
        {
            "healer_infra_failure_streak": "3",
            "healer_infra_pause_until": until,
            "healer_infra_pause_reason": "preflight_failed: Preflight requires `pnpm` for e2e-smoke/js-vue-vite but it is not available in PATH.",
        }
    )

    monkeypatch.setattr("flow_healer.healer_loop.shutil.which", lambda tool: "/opt/homebrew/bin/pnpm" if tool == "pnpm" else None)

    assert loop._infra_pause_active() is False
    assert store.get_state("healer_infra_pause_until") == ""
    assert store.get_state("healer_infra_pause_reason") == ""
    assert store.get_state("healer_infra_failure_streak") == "0"


def test_infra_pause_stays_active_for_unresolved_reason(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    until = (datetime.now(UTC) + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    store.set_states(
        {
            "healer_infra_pause_until": until,
            "healer_infra_pause_reason": "infra_pause: custom unresolved blocker",
        }
    )

    assert loop._infra_pause_active() is True


def test_infra_pause_auto_clears_when_bundler_artifact_reason_has_no_remaining_contamination(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    until = (datetime.now(UTC) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    store.set_states(
        {
            "healer_infra_pause_until": until,
            "healer_infra_pause_reason": (
                "infra_pause: Pause autonomous repair in this worktree because it is contaminated "
                "with out-of-scope Bundler artifacts."
            ),
            "healer_last_contamination_paths": "",
        }
    )
    loop = _make_loop(store, healer_repo_path=str(tmp_path))

    assert loop._infra_pause_active() is False
    assert store.get_state("healer_infra_pause_until") == ""
    assert store.get_state("healer_infra_pause_reason") == ""


def test_swarm_quarantine_with_sql_bootstrap_context_stays_quarantine(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    outcome = SwarmRecoveryOutcome(
        recovered=False,
        strategy="quarantine",
        summary="Validation never reached the SQL assertion because the local Supabase stack would not start.",
        analyzer_results=(),
        plan=SwarmRecoveryPlan(
            strategy="quarantine",
            summary="Validation never reached the SQL assertion because the local Supabase stack would not start.",
            root_cause="local Supabase bootstrap failure",
            edit_scope=(),
            targeted_tests=(),
            validation_focus=(),
        ),
        failure_class="tests_failed",
        failure_reason="The local Supabase runtime is broken.",
    )

    failure_class, failure_reason = loop._swarm_failure_override(
        base_failure_class="tests_failed",
        base_failure_reason="Failed tests=1 exceeds cap=0",
        swarm_outcome=outcome,
    )

    assert failure_class == "swarm_quarantine"
    assert "Supabase" in failure_reason


def test_swarm_quarantine_with_daemon_connectivity_maps_to_infra_pause(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    outcome = SwarmRecoveryOutcome(
        recovered=False,
        strategy="quarantine",
        summary="Cannot connect to the Docker daemon while launching validator containers.",
        analyzer_results=(),
        plan=SwarmRecoveryPlan(
            strategy="quarantine",
            summary="Cannot connect to the Docker daemon while launching validator containers.",
            root_cause="docker daemon unavailable",
            edit_scope=(),
            targeted_tests=(),
            validation_focus=(),
        ),
        failure_class="tests_failed",
        failure_reason="Cannot connect to the Docker daemon at unix:///var/run/docker.sock.",
    )

    failure_class, failure_reason = loop._swarm_failure_override(
        base_failure_class="tests_failed",
        base_failure_reason="Failed tests=1 exceeds cap=0",
        swarm_outcome=outcome,
    )

    assert failure_class == "infra_pause"
    assert "docker daemon" in failure_reason.lower()


def test_swarm_infra_pause_strategy_with_sql_path_resolution_stays_issue_scoped(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    outcome = SwarmRecoveryOutcome(
        recovered=False,
        strategy="infra_pause",
        summary=(
            "Pause autonomous repair because the current failure is a validation-path routing problem "
            "outside the issue's exact allowed edit set, not a confirmed defect in the named migration/assertion pair."
        ),
        analyzer_results=(),
        plan=SwarmRecoveryPlan(
            strategy="infra_pause",
            summary=(
                "Pause autonomous repair because the current failure is a validation-path routing problem "
                "outside the issue's exact allowed edit set, not a confirmed defect in the named migration/assertion pair."
            ),
            root_cause="sql_assertion_path_resolution_mismatch",
            edit_scope=("e2e-apps/prosper-chat/supabase/assertions/bot_widget_integrity.sql",),
            targeted_tests=(),
            validation_focus=("supabase",),
        ),
        failure_class="tests_failed",
        failure_reason=(
            "Requested SQL assertion path does not exist: "
            "e2e-apps/prosper-chat/supabase/assertions/bot_widget_integrity.sql"
        ),
    )

    failure_class, failure_reason = loop._swarm_failure_override(
        base_failure_class="tests_failed",
        base_failure_reason="Failed tests=1 exceeds cap=0",
        swarm_outcome=outcome,
    )

    assert failure_class == "swarm_quarantine"
    assert "Requested SQL assertion path does not exist" in failure_reason


def test_swarm_quarantine_scope_limited_redirect_failure_stays_issue_scoped(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    outcome = SwarmRecoveryOutcome(
        recovered=False,
        strategy="quarantine",
        summary=(
            "The failing Ruby Rails request spec is blocked by redirect header serialization outside the issue's "
            "allowed edit set. The staged route change for GET / should not be promoted, but a safe autonomous "
            "fix cannot be completed by editing only the named dashboard files."
        ),
        analyzer_results=(),
        plan=SwarmRecoveryPlan(
            strategy="quarantine",
            summary=(
                "The failing Ruby Rails request spec is blocked by redirect header serialization outside the issue's "
                "allowed edit set. The staged route change for GET / should not be promoted, but a safe autonomous "
                "fix cannot be completed by editing only the named dashboard files."
            ),
            root_cause="redirect_location_contract_mismatch_outside_allowed_scope",
            edit_scope=(
                "e2e-apps/ruby-rails-web/app/controllers/dashboard_controller.rb",
                "e2e-apps/ruby-rails-web/config/routes.rb",
            ),
            targeted_tests=("cd e2e-apps/ruby-rails-web && bundle exec rspec",),
            validation_focus=(),
        ),
        failure_class="tests_failed",
        failure_reason=(
            "The failing Ruby Rails request spec is blocked by redirect header serialization outside the issue's "
            "allowed edit set."
        ),
    )

    failure_class, failure_reason = loop._swarm_failure_override(
        base_failure_class="tests_failed",
        base_failure_reason="Failed tests=1 exceeds cap=0",
        swarm_outcome=outcome,
    )

    assert failure_class == "swarm_quarantine"
    assert "allowed edit set" in failure_reason


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


def test_record_reconcile_summary_accumulates_cleanup_counters(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)

    loop._record_reconcile_summary(
        {
            "reaped_orphan_app_runtimes": 2,
            "cleaned_artifact_roots": 3,
        }
    )

    assert store.get_state("healer_orphan_runtime_reap_events") == "2"
    assert store.get_state("healer_orphan_artifact_cleanup_events") == "3"


def test_record_harness_attempt_observability_tracks_refs_and_failure_counters(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store, healer_github_artifact_retention_days=14)
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    loop._record_harness_attempt_observability(
        issue_id="42",
        attempt_id="hat_test42",
        test_summary={
            "browser_failure_family": "artifact_capture",
            "artifact_publish_status": "failed",
            "runtime_summary": {
                "app_harness": {
                    "profile": "web",
                    "process": {"pid": 4321, "profile": "web", "command": ["npm", "run", "dev"], "cwd": str(tmp_path)},
                }
            },
            "artifact_bundle": {"artifact_root": str(artifact_root)},
        },
        workspace_status={},
        failure_class="browser_artifact_capture_failed",
    )

    assert store.get_state("healer_app_runtime_profile_last_seen_at:web")
    assert store.get_state("healer_artifact_publish_failures") == "1"
    assert store.get_state("healer_browser_artifact_capture_failures") == "1"
    assert "\"path\": \"" in str(store.get_state("healer_artifact_root_ref:42:hat_test42") or "")
    assert "\"path\": \"" in str(store.get_state("healer_browser_session_ref:42:hat_test42") or "")
    assert "\"pid\": 4321" in str(store.get_state("healer_app_runtime_ref:42:hat_test42") or "")


def test_maybe_run_harness_canaries_records_success(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    profile = AppRuntimeProfile(
        name="web",
        command=("npm", "run", "dev"),
        cwd=tmp_path,
        readiness_url="http://127.0.0.1:3000/",
    )
    loop = _make_loop(
        store,
        healer_app_runtime_profiles={"web": profile},
        healer_harness_canary_interval_seconds=300,
    )
    loop.tracker.publish_artifact_files.return_value = [SimpleNamespace(name="canary.png")]

    class _FakeCanarySession:
        def stop(self) -> int:
            return 0

    class _FakeCanaryAppHarness:
        def boot(self, runtime_profile):
            return SimpleNamespace(profile=runtime_profile), _FakeCanarySession()

    class _FakeCanaryBrowserHarness:
        def check_runtime_available(self):
            return True, ""

        def capture_journey(self, *, profile, entry_url, repro_steps, artifact_root, phase, expect_failure):
            phase_root = artifact_root / phase
            phase_root.mkdir(parents=True, exist_ok=True)
            screenshot = phase_root / "canary.png"
            console = phase_root / "canary-console.log"
            network = phase_root / "canary-network.jsonl"
            screenshot.write_text("png", encoding="utf-8")
            console.write_text("console", encoding="utf-8")
            network.write_text("{}", encoding="utf-8")
            return BrowserJourneyResult(
                phase=phase,
                passed=True,
                expected_failure_observed=False,
                final_url=entry_url,
                screenshot_path=str(screenshot),
                console_log_path=str(console),
                network_log_path=str(network),
            )

    monkeypatch.setattr(loop, "_new_canary_app_harness", lambda: _FakeCanaryAppHarness())
    monkeypatch.setattr(loop, "_new_canary_browser_harness", lambda: _FakeCanaryBrowserHarness())

    summary = loop._maybe_run_harness_canaries(force=True)

    assert summary == {"profiles": 1, "passed": 1, "failed": 0}
    assert store.get_state("healer_app_runtime_canary_last_success_at:web")
    assert store.get_state("healer_harness_canary_failures") is None


def test_maybe_run_harness_canaries_use_boot_result_readiness_url(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    profile = AppRuntimeProfile(
        name="web",
        command=("npm", "run", "dev"),
        cwd=tmp_path,
        readiness_url="http://127.0.0.1:3000/",
    )
    loop = _make_loop(
        store,
        healer_app_runtime_profiles={"web": profile},
        healer_harness_canary_interval_seconds=300,
    )
    seen_entry_urls: list[str] = []

    class _FakeCanarySession:
        def stop(self) -> int:
            return 0

    class _FakeCanaryAppHarness:
        def boot(self, runtime_profile):
            return (
                SimpleNamespace(
                    profile=runtime_profile,
                    readiness_url="http://localhost:3001/",
                    pid=4321,
                    ready_via_url=True,
                    ready_via_log=False,
                    startup_seconds=0.2,
                    output_tail="Local: http://localhost:3001",
                ),
                _FakeCanarySession(),
            )

    class _FakeCanaryBrowserHarness:
        def check_runtime_available(self):
            return True, ""

        def capture_journey(self, *, profile, entry_url, repro_steps, artifact_root, phase, expect_failure):
            seen_entry_urls.append(entry_url)
            phase_root = artifact_root / phase
            phase_root.mkdir(parents=True, exist_ok=True)
            screenshot = phase_root / "canary.png"
            console = phase_root / "canary-console.log"
            network = phase_root / "canary-network.jsonl"
            screenshot.write_text("png", encoding="utf-8")
            console.write_text("console", encoding="utf-8")
            network.write_text("{}", encoding="utf-8")
            return BrowserJourneyResult(
                phase=phase,
                passed=True,
                expected_failure_observed=False,
                final_url=entry_url,
                screenshot_path=str(screenshot),
                console_log_path=str(console),
                network_log_path=str(network),
            )

    monkeypatch.setattr(loop, "_new_canary_app_harness", lambda: _FakeCanaryAppHarness())
    monkeypatch.setattr(loop, "_new_canary_browser_harness", lambda: _FakeCanaryBrowserHarness())

    summary = loop._maybe_run_harness_canaries(force=True)

    assert summary == {"profiles": 1, "passed": 1, "failed": 0}
    assert seen_entry_urls == ["http://localhost:3001/"]


def test_maybe_run_harness_canaries_records_failure_counters(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    profile = AppRuntimeProfile(
        name="web",
        command=("npm", "run", "dev"),
        cwd=tmp_path,
        readiness_url="http://127.0.0.1:3000/",
    )
    loop = _make_loop(
        store,
        healer_app_runtime_profiles={"web": profile},
        healer_harness_canary_interval_seconds=300,
    )

    class _FakeCanarySession:
        def stop(self) -> int:
            return 0

    class _FakeCanaryAppHarness:
        def boot(self, runtime_profile):
            return SimpleNamespace(profile=runtime_profile), _FakeCanarySession()

    class _FailingCanaryBrowserHarness:
        def check_runtime_available(self):
            return True, ""

        def capture_journey(self, *, profile, entry_url, repro_steps, artifact_root, phase, expect_failure):
            raise RuntimeError("artifact capture failed: screenshot missing")

    monkeypatch.setattr(loop, "_new_canary_app_harness", lambda: _FakeCanaryAppHarness())
    monkeypatch.setattr(loop, "_new_canary_browser_harness", lambda: _FailingCanaryBrowserHarness())

    summary = loop._maybe_run_harness_canaries(force=True)

    assert summary == {"profiles": 1, "passed": 0, "failed": 1}
    assert store.get_state("healer_harness_canary_failures") == "1"
    assert store.get_state("healer_browser_artifact_capture_failures") == "1"
    assert "artifact capture failed" in str(store.get_state("healer_app_runtime_canary_last_failure_reason:web") or "")


def test_maybe_run_harness_canaries_coerces_dict_backed_profiles(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    repo_path = tmp_path / "repo"
    runtime_root = repo_path / "runtime"
    runtime_root.mkdir(parents=True)
    loop = _make_loop(
        store,
        healer_repo_path=str(repo_path),
        healer_app_runtime_profiles={
            "web": {
                "name": "web",
                "start_command": "npm run dev",
                "working_directory": "runtime",
                "ready_url": "http://127.0.0.1:3000/",
                "browser": "chromium",
                "headless": True,
                "viewport": {"width": 1280, "height": 800},
            }
        },
        healer_harness_canary_interval_seconds=300,
    )

    class _FakeCanarySession:
        def stop(self) -> int:
            return 0

    class _FakeCanaryAppHarness:
        def boot(self, runtime_profile):
            assert isinstance(runtime_profile, AppRuntimeProfile)
            assert runtime_profile.command == ("npm", "run", "dev")
            assert runtime_profile.cwd == runtime_root.resolve()
            return SimpleNamespace(profile=runtime_profile), _FakeCanarySession()

    class _FakeCanaryBrowserHarness:
        def check_runtime_available(self):
            return True, ""

        def capture_journey(self, *, profile, entry_url, repro_steps, artifact_root, phase, expect_failure):
            screenshot = Path(artifact_root) / "canary.png"
            console = Path(artifact_root) / "canary-console.log"
            network = Path(artifact_root) / "canary-network.jsonl"
            screenshot.write_text("png", encoding="utf-8")
            console.write_text("console", encoding="utf-8")
            network.write_text("network", encoding="utf-8")
            return BrowserJourneyResult(
                phase=phase,
                passed=True,
                expected_failure_observed=False,
                final_url=entry_url,
                screenshot_path=str(screenshot),
                console_log_path=str(console),
                network_log_path=str(network),
            )

    monkeypatch.setattr(loop, "_new_canary_app_harness", lambda: _FakeCanaryAppHarness())
    monkeypatch.setattr(loop, "_new_canary_browser_harness", lambda: _FakeCanaryBrowserHarness())
    loop.tracker.publish_artifact_files = MagicMock(return_value=[{"label": "canary"}])

    summary = loop._maybe_run_harness_canaries(force=True)

    assert summary == {"profiles": 1, "passed": 1, "failed": 0}
    assert store.get_state("healer_app_runtime_canary_last_success_at:web")


def test_maybe_run_harness_canaries_covers_multiple_reference_app_profiles(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()

    def _profile(name: str, port: int) -> AppRuntimeProfile:
        return AppRuntimeProfile(
            name=name,
            command=("npm", "run", "dev"),
            cwd=tmp_path,
            readiness_url=f"http://127.0.0.1:{port}/healthz",
        )

    loop = _make_loop(
        store,
        healer_app_runtime_profiles={
            "node-next-web": _profile("node-next-web", 3000),
            "ruby-rails-web": _profile("ruby-rails-web", 3101),
            "java-spring-web": _profile("java-spring-web", 3201),
        },
        healer_harness_canary_interval_seconds=300,
    )

    class _FakeCanarySession:
        def stop(self) -> int:
            return 0

    class _FakeCanaryAppHarness:
        def boot(self, runtime_profile):
            return SimpleNamespace(profile=runtime_profile), _FakeCanarySession()

    class _FakeCanaryBrowserHarness:
        def check_runtime_available(self):
            return True, ""

        def capture_journey(self, *, artifact_root, phase, profile, entry_url, **_kwargs):
            phase_root = artifact_root / phase
            phase_root.mkdir(parents=True, exist_ok=True)
            screenshot = phase_root / f"{profile.name}-{phase}.png"
            console = phase_root / f"{profile.name}-{phase}-console.log"
            network = phase_root / f"{profile.name}-{phase}-network.jsonl"
            screenshot.write_text("png", encoding="utf-8")
            console.write_text(entry_url, encoding="utf-8")
            network.write_text("{}\n", encoding="utf-8")
            return BrowserJourneyResult(
                phase=phase,
                passed=True,
                expected_failure_observed=False,
                final_url=entry_url,
                screenshot_path=str(screenshot),
                console_log_path=str(console),
                network_log_path=str(network),
            )

    monkeypatch.setattr(loop, "_new_canary_app_harness", lambda: _FakeCanaryAppHarness())
    monkeypatch.setattr(loop, "_new_canary_browser_harness", lambda: _FakeCanaryBrowserHarness())
    loop.tracker.publish_artifact_files = MagicMock(return_value=[{"label": "canary"}])

    summary = loop._maybe_run_harness_canaries(force=True)

    assert summary == {"profiles": 3, "passed": 3, "failed": 0}
    assert store.get_state("healer_app_runtime_canary_last_success_at:node-next-web")
    assert store.get_state("healer_app_runtime_canary_last_success_at:ruby-rails-web")
    assert store.get_state("healer_app_runtime_canary_last_success_at:java-spring-web")
    assert loop.tracker.publish_artifact_files.call_count == 3


def test_maybe_run_harness_canaries_validates_multiple_browser_stacks(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    repo_path = tmp_path / "repo"
    runtime_roots = {
        "node-next-web": repo_path / "node-next",
        "ruby-rails-web": repo_path / "ruby-rails",
        "java-spring-web": repo_path / "java-spring",
    }
    for runtime_root in runtime_roots.values():
        runtime_root.mkdir(parents=True)

    loop = _make_loop(
        store,
        healer_repo_path=str(repo_path),
        healer_app_runtime_profiles={
            "node-next-web": {
                "name": "node-next-web",
                "start_command": "npm run dev",
                "working_directory": "node-next",
                "ready_url": "http://127.0.0.1:3000/",
                "browser": "chromium",
                "headless": True,
            },
            "ruby-rails-web": {
                "name": "ruby-rails-web",
                "start_command": "ruby server.rb",
                "working_directory": "ruby-rails",
                "ready_url": "http://127.0.0.1:3101/healthz",
                "browser": "chromium",
                "headless": True,
            },
            "java-spring-web": {
                "name": "java-spring-web",
                "start_command": "./gradlew bootRun",
                "working_directory": "java-spring",
                "ready_url": "http://127.0.0.1:3201/healthz",
                "browser": "chromium",
                "headless": True,
            },
        },
        healer_harness_canary_interval_seconds=300,
    )

    class _FakeCanarySession:
        def stop(self) -> int:
            return 0

    class _FakeCanaryAppHarness:
        def boot(self, runtime_profile):
            assert isinstance(runtime_profile, AppRuntimeProfile)
            assert runtime_profile.cwd == runtime_roots[runtime_profile.name].resolve()
            return SimpleNamespace(profile=runtime_profile), _FakeCanarySession()

    class _FakeCanaryBrowserHarness:
        def check_runtime_available(self):
            return True, ""

        def capture_journey(self, *, profile, entry_url, repro_steps, artifact_root, phase, expect_failure):
            phase_root = Path(artifact_root) / phase
            phase_root.mkdir(parents=True, exist_ok=True)
            screenshot = phase_root / f"{profile.name}.png"
            console = phase_root / f"{profile.name}-console.log"
            network = phase_root / f"{profile.name}-network.jsonl"
            screenshot.write_text("png", encoding="utf-8")
            console.write_text("console", encoding="utf-8")
            network.write_text("network", encoding="utf-8")
            return BrowserJourneyResult(
                phase=phase,
                passed=True,
                expected_failure_observed=False,
                final_url=entry_url,
                screenshot_path=str(screenshot),
                console_log_path=str(console),
                network_log_path=str(network),
            )

    monkeypatch.setattr(loop, "_new_canary_app_harness", lambda: _FakeCanaryAppHarness())
    monkeypatch.setattr(loop, "_new_canary_browser_harness", lambda: _FakeCanaryBrowserHarness())
    loop.tracker.publish_artifact_files = MagicMock(return_value=[{"label": "canary"}])

    summary = loop._maybe_run_harness_canaries(force=True)

    assert summary == {"profiles": 3, "passed": 3, "failed": 0}
    assert store.get_state("healer_app_runtime_canary_last_success_at:node-next-web")
    assert store.get_state("healer_app_runtime_canary_last_success_at:ruby-rails-web")
    assert store.get_state("healer_app_runtime_canary_last_success_at:java-spring-web")
    assert loop.tracker.publish_artifact_files.call_count == 3


def test_tick_once_defers_helper_recycle_when_idle_only_and_active_issue_exists(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.set_state("healer_helper_recycle_requested_at", "2026-03-08 19:00:00")
    store.set_state("healer_helper_recycle_idle_only", "true")
    store.upsert_healer_issue(
        issue_id="123",
        repo="owner/repo",
        title="Busy issue",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=1,
    )
    store.set_healer_issue_state(issue_id="123", state="running")

    connector = MagicMock()
    connector.ensure_started.return_value = None
    connector.health_snapshot.return_value = {
        "available": True,
        "configured_command": "codex",
        "resolved_command": "/opt/homebrew/bin/codex",
        "availability_reason": "",
        "last_health_error": "",
    }
    loop = _make_loop(store, connector=connector)
    loop.dispatcher.claim_next_issue.return_value = None

    loop._tick_once()

    connector.shutdown.assert_not_called()
    assert store.get_state("healer_helper_recycle_requested_at") == "2026-03-08 19:00:00"
    assert store.get_state("healer_helper_recycle_status") == "deferred_busy"


def test_tick_once_recycles_helpers_when_request_is_pending_and_loop_is_idle(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.set_state("healer_helper_recycle_requested_at", "2026-03-08 19:00:00")
    store.set_state("healer_helper_recycle_idle_only", "true")

    connector = MagicMock()
    connector.ensure_started.return_value = None
    connector.health_snapshot.return_value = {
        "available": True,
        "configured_command": "codex",
        "resolved_command": "/opt/homebrew/bin/codex",
        "availability_reason": "",
        "last_health_error": "",
    }
    loop = _make_loop(store, connector=connector)
    loop.connectors_by_backend = {"exec": connector}
    loop.dispatcher.claim_next_issue.return_value = None

    loop._tick_once()

    connector.shutdown.assert_called_once()
    assert store.get_state("healer_helper_recycle_requested_at") == ""
    assert store.get_state("healer_helper_recycle_idle_only") == ""
    assert store.get_state("healer_helper_recycle_status") == "completed"
    assert "restart lazily on next use" in str(store.get_state("healer_helper_recycle_reason") or "")


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


def test_loop_passes_app_runtime_profiles_to_runner(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()

    captured_runner_kwargs: list[dict[str, object]] = []

    class _FakeRunner:
        def __init__(self, connector, **kwargs):
            captured_runner_kwargs.append(dict(kwargs))

    class _FakeVerifier:
        def __init__(self, connector, timeout_seconds=300):
            self.connector = connector
            self.timeout_seconds = timeout_seconds

    class _FakeReviewer:
        def __init__(self, connector):
            self.connector = connector

    class _FakeSwarm:
        def __init__(self, *args, **kwargs):
            pass

    class _FakePreflight:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _FakeDispatcher:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("flow_healer.healer_loop.HealerRunner", _FakeRunner)
    monkeypatch.setattr("flow_healer.healer_loop.HealerVerifier", _FakeVerifier)
    monkeypatch.setattr("flow_healer.healer_loop.HealerReviewer", _FakeReviewer)
    monkeypatch.setattr("flow_healer.healer_loop.HealerSwarm", _FakeSwarm)
    monkeypatch.setattr("flow_healer.healer_loop.HealerPreflight", _FakePreflight)
    monkeypatch.setattr("flow_healer.healer_loop.HealerDispatcher", _FakeDispatcher)
    monkeypatch.setattr("flow_healer.healer_loop.build_connector_subagent_backend", lambda connector: connector)

    settings = SimpleNamespace(
        healer_repo_path=str(repo),
        healer_poll_interval_seconds=60,
        healer_max_concurrent_issues=1,
        healer_max_wall_clock_seconds_per_issue=300,
        healer_test_gate_mode="local_then_docker",
        healer_local_gate_policy="auto",
        healer_completion_artifact_mode="fallback_only",
        healer_language="",
        healer_docker_image="",
        healer_test_command="",
        healer_install_command="",
        healer_auto_clean_generated_artifacts=True,
        healer_app_default_runtime_profile="web",
        healer_app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/health",
                "working_directory": "e2e-apps/node-next",
            }
        ],
        healer_swarm_max_parallel_agents=2,
        healer_swarm_max_repair_cycles_per_attempt=1,
        healer_swarm_analysis_timeout_seconds=60,
        healer_swarm_recovery_timeout_seconds=120,
        healer_learning_enabled=False,
        healer_enable_review=False,
        healer_issue_required_labels=["healer:ready"],
        healer_pr_actions_require_approval=False,
        healer_pr_required_label="healer:pr-approved",
        healer_pr_auto_approve_clean=False,
        healer_pr_auto_merge_clean=False,
        healer_pr_merge_method="squash",
        healer_retry_budget=2,
        healer_backoff_initial_seconds=60,
        healer_backoff_max_seconds=3600,
        healer_circuit_breaker_window=5,
        healer_circuit_breaker_failure_rate=0.5,
        healer_circuit_breaker_cooldown_seconds=900,
        healer_verifier_policy="required",
        healer_codex_native_multi_agent_enabled=False,
        healer_codex_native_multi_agent_max_subagents=3,
        healer_swarm_enabled=False,
        healer_swarm_mode="failure_repair",
        healer_swarm_trigger_failure_classes=["tests_failed"],
        healer_swarm_backend_strategy="match_selected_backend",
        healer_issue_contract_mode="lenient",
        healer_parse_confidence_threshold=0.3,
        healer_max_diff_files=8,
        healer_max_diff_lines=400,
        healer_max_failed_tests_allowed=0,
        healer_overlap_scope_queue_enabled=True,
    )

    connector = _HealthyConnector()
    loop = AutonomousHealerLoop(
        settings=settings,
        store=store,
        connector=connector,
        tracker=MagicMock(),
        connectors_by_backend={"exec": connector},
    )

    assert loop.runners_by_backend["exec"] is not None
    assert captured_runner_kwargs == [
        {
            "timeout_seconds": 300,
            "test_gate_mode": "local_then_docker",
            "local_gate_policy": "auto",
            "completion_artifact_mode": "fallback_only",
            "language": "",
            "docker_image": "",
            "test_command": "",
            "install_command": "",
            "auto_clean_generated_artifacts": True,
            "default_runtime_profile": "web",
            "app_runtime_profiles": [
                {
                    "name": "web",
                    "start_command": "npm run dev",
                    "ready_url": "http://127.0.0.1:3000/health",
                    "working_directory": "e2e-apps/node-next",
                }
            ],
            "workspace_manager": loop.workspace_manager,
            "base_branch": "main",
        }
    ]


def test_loop_coerces_scalar_scan_label_to_single_default_label(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()

    captured_scanner_kwargs: list[dict[str, object]] = []

    class _FakeRunner:
        def __init__(self, connector, **kwargs):
            self.connector = connector

    class _FakeVerifier:
        def __init__(self, connector, timeout_seconds=300):
            self.connector = connector
            self.timeout_seconds = timeout_seconds

    class _FakeReviewer:
        def __init__(self, connector):
            self.connector = connector

    class _FakeSwarm:
        def __init__(self, *args, **kwargs):
            pass

    class _FakePreflight:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _FakeDispatcher:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _FakeScanner:
        def __init__(self, **kwargs):
            captured_scanner_kwargs.append(dict(kwargs))

    monkeypatch.setattr("flow_healer.healer_loop.HealerRunner", _FakeRunner)
    monkeypatch.setattr("flow_healer.healer_loop.HealerVerifier", _FakeVerifier)
    monkeypatch.setattr("flow_healer.healer_loop.HealerReviewer", _FakeReviewer)
    monkeypatch.setattr("flow_healer.healer_loop.HealerSwarm", _FakeSwarm)
    monkeypatch.setattr("flow_healer.healer_loop.HealerPreflight", _FakePreflight)
    monkeypatch.setattr("flow_healer.healer_loop.HealerDispatcher", _FakeDispatcher)
    monkeypatch.setattr("flow_healer.healer_loop.FlowHealerScanner", _FakeScanner)
    monkeypatch.setattr("flow_healer.healer_loop.build_connector_subagent_backend", lambda connector: connector)

    settings = SimpleNamespace(
        healer_repo_path=str(repo),
        healer_poll_interval_seconds=60,
        healer_max_concurrent_issues=1,
        healer_max_wall_clock_seconds_per_issue=300,
        healer_test_gate_mode="local_then_docker",
        healer_local_gate_policy="auto",
        healer_completion_artifact_mode="fallback_only",
        healer_language="",
        healer_docker_image="",
        healer_test_command="",
        healer_install_command="",
        healer_auto_clean_generated_artifacts=True,
        healer_app_default_runtime_profile="",
        healer_app_runtime_profiles={},
        healer_swarm_max_parallel_agents=2,
        healer_swarm_max_repair_cycles_per_attempt=1,
        healer_swarm_analysis_timeout_seconds=60,
        healer_swarm_recovery_timeout_seconds=120,
        healer_learning_enabled=False,
        healer_enable_review=False,
        healer_issue_required_labels=["healer:ready"],
        healer_pr_actions_require_approval=False,
        healer_pr_required_label="healer:pr-approved",
        healer_pr_auto_approve_clean=False,
        healer_pr_auto_merge_clean=False,
        healer_pr_merge_method="squash",
        healer_retry_budget=2,
        healer_backoff_initial_seconds=60,
        healer_backoff_max_seconds=3600,
        healer_circuit_breaker_window=5,
        healer_circuit_breaker_failure_rate=0.5,
        healer_circuit_breaker_cooldown_seconds=900,
        healer_verifier_policy="required",
        healer_codex_native_multi_agent_enabled=False,
        healer_codex_native_multi_agent_max_subagents=3,
        healer_swarm_enabled=False,
        healer_swarm_mode="failure_repair",
        healer_swarm_trigger_failure_classes=["tests_failed"],
        healer_swarm_backend_strategy="match_selected_backend",
        healer_issue_contract_mode="lenient",
        healer_parse_confidence_threshold=0.3,
        healer_max_diff_files=8,
        healer_max_diff_lines=400,
        healer_max_failed_tests_allowed=0,
        healer_overlap_scope_queue_enabled=True,
        healer_scan_default_labels="kind:scan",
    )

    connector = _HealthyConnector()
    AutonomousHealerLoop(
        settings=settings,
        store=store,
        connector=connector,
        tracker=MagicMock(),
        connectors_by_backend={"exec": connector},
    )

    assert captured_scanner_kwargs[0]["default_labels"] == ["kind:scan"]


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


def test_format_pr_description_includes_evidence_section_when_artifacts_present():
    body = AutonomousHealerLoop._format_pr_description(
        issue_id="155",
        verifier_summary="Verified and approved.",
        test_summary={
            "failed_tests": 0,
            "mode": "local_only",
            "artifact_bundle": {
                "status": "captured",
                "artifact_root": "/tmp/flow-healer-browser/155",
                "github_artifact_branch": "flow-healer-artifacts",
                "journey_transcript": [{"phase": "failure"}, {"phase": "resolution"}],
            },
            "artifact_links": [
                {
                    "label": "failure_screenshot",
                    "path": "/tmp/flow-healer-browser/155/failure/failure.png",
                    "href": "https://github.com/owner/repo/blob/flow-healer-artifacts/flow-healer/evidence/issue-155/attempt-1/failure.png",
                    "raw_href": "https://raw.githubusercontent.com/owner/repo/flow-healer-artifacts/flow-healer/evidence/issue-155/attempt-1/failure.png",
                },
                {
                    "label": "resolution_screenshot",
                    "path": "/tmp/flow-healer-browser/155/resolution/resolution.png",
                    "href": "https://github.com/owner/repo/blob/flow-healer-artifacts/flow-healer/evidence/issue-155/attempt-1/resolution.png",
                    "raw_href": "https://raw.githubusercontent.com/owner/repo/flow-healer-artifacts/flow-healer/evidence/issue-155/attempt-1/resolution.png",
                },
                {
                    "label": "failure_console_log",
                    "path": "/tmp/flow-healer-browser/155/failure/failure-console.log",
                    "href": "https://github.com/owner/repo/blob/flow-healer-artifacts/flow-healer/evidence/issue-155/attempt-1/failure-console.log",
                },
                {
                    "label": "journey_transcript",
                    "path": "/tmp/flow-healer-browser/155/journey-transcript.json",
                    "href": "https://github.com/owner/repo/blob/flow-healer-artifacts/flow-healer/evidence/issue-155/attempt-1/journey-transcript.json",
                },
            ],
        },
    )

    assert "### Evidence" in body
    assert "| Before | After |" in body
    assert "![Failure screenshot]" in body
    assert "![Resolution screenshot]" in body
    assert "Evidence bundle: `captured`" in body
    assert "Published branch: `flow-healer-artifacts`" in body
    assert "Operational links:" in body
    assert "<details>" in body
    assert "<summary>Journey transcript</summary>" in body


def test_publish_pr_artifacts_enriches_links_and_bundle(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    screenshot = artifact_root / "failure.png"
    screenshot.write_bytes(b"png")
    transcript_path = artifact_root / "journey-transcript.json"
    bundle = {
        "status": "captured",
        "artifact_root": str(artifact_root),
        "journey_transcript": [
            {"phase": "failure", "transcript": [{"step": "goto /", "status": "passed"}]},
        ],
    }
    loop.tracker.publish_artifact_files.return_value = [
        SimpleNamespace(
            name="failure.png",
            branch="flow-healer-artifacts",
            remote_path="flow-healer/evidence/issue-155/attempt-1/failure.png",
            html_url="https://github.com/owner/repo/blob/flow-healer-artifacts/flow-healer/evidence/issue-155/attempt-1/failure.png",
            download_url="https://raw.githubusercontent.com/owner/repo/flow-healer-artifacts/flow-healer/evidence/issue-155/attempt-1/failure.png",
            markdown_url="https://raw.githubusercontent.com/owner/repo/flow-healer-artifacts/flow-healer/evidence/issue-155/attempt-1/failure.png",
            content_type="image/png",
            sha="pngsha",
        ),
        SimpleNamespace(
            name="journey-transcript.json",
            branch="flow-healer-artifacts",
            remote_path="flow-healer/evidence/issue-155/attempt-1/journey-transcript.json",
            html_url="https://github.com/owner/repo/blob/flow-healer-artifacts/flow-healer/evidence/issue-155/attempt-1/journey-transcript.json",
            download_url="https://raw.githubusercontent.com/owner/repo/flow-healer-artifacts/flow-healer/evidence/issue-155/attempt-1/journey-transcript.json",
            markdown_url="https://raw.githubusercontent.com/owner/repo/flow-healer-artifacts/flow-healer/evidence/issue-155/attempt-1/journey-transcript.json",
            content_type="application/json",
            sha="jsonsha",
        ),
    ]

    summary = loop._publish_pr_artifacts(
        issue_id="155",
        attempt_id="attempt-1",
        base_branch="main",
        test_summary={
            "artifact_bundle": bundle,
            "artifact_links": [{"label": "failure_screenshot", "path": str(screenshot)}],
        },
    )

    loop.tracker.publish_artifact_files.assert_called_once()
    call = loop.tracker.publish_artifact_files.call_args
    assert call.kwargs["issue_id"] == "155"
    assert call.kwargs["branch"] == "flow-healer-artifacts"
    assert call.kwargs["retention_days"] == 30
    assert call.kwargs["max_file_bytes"] == 5 * 1024 * 1024
    assert call.kwargs["max_run_bytes"] == 25 * 1024 * 1024
    assert call.kwargs["max_branch_bytes"] == 250 * 1024 * 1024
    assert call.kwargs["metadata"]["browser_log_publish_mode"] == "always"
    assert call.kwargs["metadata"]["attempt_id"] == "attempt-1"
    assert transcript_path.exists()
    assert summary["artifact_bundle"]["github_artifact_branch"] == "flow-healer-artifacts"
    assert summary["artifact_bundle"]["github_artifact_root"] == "flow-healer/evidence/issue-155/attempt-1"
    links = summary["artifact_links"]
    screenshot_link = next(item for item in links if item["label"] == "failure_screenshot")
    transcript_link = next(item for item in links if item["label"] == "journey_transcript")
    assert screenshot_link["href"].startswith("https://github.com/owner/repo/blob/flow-healer-artifacts/")
    assert screenshot_link["raw_href"].startswith("https://raw.githubusercontent.com/owner/repo/")
    assert transcript_link["href"].endswith("/journey-transcript.json")


def test_record_harness_observability_tracks_refs_and_failure_counters(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    loop = _make_loop(store)
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    loop._record_harness_attempt_observability(
        issue_id="155",
        attempt_id="hat_observe",
        failure_class="artifact_publish_failed",
        test_summary={
            "browser_failure_family": "artifact_publish",
            "artifact_publish_status": "failed",
            "artifact_bundle": {
                "artifact_root": str(artifact_root),
                "status": "captured",
            },
            "runtime_summary": {
                "app_harness": {
                    "profile": "web",
                    "process": {
                        "pid": os.getpid(),
                        "profile": "web",
                        "command": ["npm", "run", "dev"],
                        "cwd": str(tmp_path),
                    },
                }
            },
        },
        workspace_status={},
    )
    loop._record_harness_attempt_observability(
        issue_id="155",
        attempt_id="hat_capture",
        failure_class="browser_artifact_capture_failed",
        test_summary={
            "browser_failure_family": "artifact_capture",
            "artifact_bundle": {
                "artifact_root": str(artifact_root),
                "status": "failed",
            },
        },
        workspace_status={},
    )

    assert store.get_state("healer_artifact_publish_failures") == "1"
    assert store.get_state("healer_browser_artifact_capture_failures") == "1"
    assert store.get_state("healer_app_runtime_profile_last_seen_at:web")
    assert store.get_state("healer_artifact_publish_last_failure_at")
    artifact_ref = store.get_state("healer_artifact_root_ref:155:hat_observe")
    runtime_ref = store.get_state("healer_app_runtime_ref:155:hat_observe")
    assert artifact_ref is not None and str(artifact_root) in artifact_ref
    assert runtime_ref is not None and '"profile": "web"' in runtime_ref


def test_run_runtime_profile_canary_records_success_and_publishes_artifacts(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    profile_root = tmp_path / "app"
    profile_root.mkdir()
    profile = SimpleNamespace(
        name="web",
        command=("npm", "run", "dev"),
        cwd=profile_root,
        readiness_url="http://127.0.0.1:3000",
        readiness_log_text=None,
        browser="chromium",
        headless=True,
        viewport=None,
        device="",
        startup_timeout_seconds=5.0,
        shutdown_timeout_seconds=1.0,
        poll_interval_seconds=0.1,
    )
    loop = _make_loop(
        store,
        healer_app_runtime_profiles={"web": profile},
        healer_harness_canary_interval_seconds=3600,
    )

    class _FakeSession:
        def __init__(self) -> None:
            self.stopped = 0

        def stop(self) -> int:
            self.stopped += 1
            return 0

    fake_session = _FakeSession()

    class _FakeAppHarness:
        def boot(self, runtime_profile):
            return (
                SimpleNamespace(
                    profile=runtime_profile,
                    pid=os.getpid(),
                    readiness_url=runtime_profile.readiness_url,
                    ready_via_url=True,
                    ready_via_log=False,
                    startup_seconds=0.2,
                    output_tail="ready",
                ),
                fake_session,
            )

    class _FakeBrowserHarness:
        def check_runtime_available(self):
            return True, ""

        def capture_journey(self, *, artifact_root, phase, **_kwargs):
            phase_root = Path(artifact_root) / phase
            phase_root.mkdir(parents=True, exist_ok=True)
            screenshot = phase_root / f"{phase}.png"
            console = phase_root / f"{phase}-console.log"
            network = phase_root / f"{phase}-network.jsonl"
            screenshot.write_bytes(b"png")
            console.write_text("console", encoding="utf-8")
            network.write_text("{}\n", encoding="utf-8")
            return SimpleNamespace(
                phase=phase,
                passed=True,
                expected_failure_observed=False,
                final_url="http://127.0.0.1:3000/",
                failure_step="",
                error="",
                screenshot_path=str(screenshot),
                video_path="",
                console_log_path=str(console),
                network_log_path=str(network),
                transcript=(),
            )

    monkeypatch.setattr(loop, "_new_canary_app_harness", lambda: _FakeAppHarness())
    monkeypatch.setattr(loop, "_new_canary_browser_harness", lambda: _FakeBrowserHarness())
    loop.tracker.publish_artifact_files.return_value = [
        SimpleNamespace(
            name="canary.png",
            branch="flow-healer-artifacts",
            remote_path="flow-healer/evidence/issue-canary-web/run-1/canary.png",
            html_url="https://example.test/artifacts/canary.png",
            download_url="https://example.test/raw/canary.png",
            markdown_url="https://example.test/raw/canary.png",
            content_type="image/png",
            sha="1",
        )
    ]

    result = loop._run_harness_canary_for_profile(profile=profile)

    assert result is True
    assert fake_session.stopped == 1
    assert store.get_state("healer_app_runtime_canary_last_success_at:web")
    assert store.get_state("healer_app_runtime_profile_last_seen_at:web")
    loop.tracker.publish_artifact_files.assert_called_once()


def test_reconcile_pr_outcomes_persists_ci_status_summary_for_open_pr(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="50446",
        repo="owner/repo",
        title="Issue 50446",
        body="Fix src/flow_healer/service.py",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="50446",
        state="pr_open",
        pr_number=246,
        pr_state="open",
    )
    store.create_healer_attempt(
        attempt_id="ha_50446_1",
        issue_id="50446",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="ha_50446_1",
        state="pr_open",
        actual_diff_set=["src/flow_healer/service.py"],
        test_summary={"promotion_state": "merge_blocked"},
        verifier_summary={},
    )

    loop = _make_loop(store, healer_enable_review=False)
    loop.tracker.get_pr_details.return_value = PullRequestDetails(
        number=246,
        state="open",
        html_url="https://github.com/owner/repo/pull/246",
        mergeable_state="clean",
        author="healer-service",
        head_ref="healer/issue-50446",
        head_sha="abc123",
        updated_at="2026-03-11T22:00:00Z",
    )
    loop.tracker.get_pr_ci_status_summary.return_value = {
        "head_sha": "abc123",
        "overall_state": "pending",
        "pending_contexts": ["CI"],
    }

    loop._reconcile_pr_outcomes(force_refresh=True)

    issue = store.get_healer_issue("50446")
    attempt = store.list_healer_attempts(issue_id="50446", limit=1)[0]

    assert issue is not None
    assert issue["ci_status_summary"]["overall_state"] == "pending"
    assert attempt["ci_status_summary"]["pending_contexts"] == ["CI"]


def test_requeue_ci_failed_pr_requeues_issue_with_feedback_context(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="50447",
        repo="owner/repo",
        title="Issue 50447",
        body="Fix CI failure",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.increment_healer_attempt("50447")
    store.set_healer_issue_state(
        issue_id="50447",
        state="pr_open",
        pr_number=247,
        pr_state="open",
        feedback_context="Existing PR feedback",
        ci_status_summary={
            "head_sha": "def456",
            "overall_state": "failure",
            "failure_buckets": ["lint", "deploy_blocked"],
            "failing_entries": [
                {
                    "source": "check_run",
                    "name": "lint",
                    "state": "failure",
                    "bucket": "lint",
                    "updated_at": "2026-03-11T22:05:00Z",
                }
            ],
            "pending_contexts": ["Preview"],
            "updated_at": "2026-03-11T22:05:00Z",
        },
    )

    loop = _make_loop(store, healer_retry_budget=3)

    requeued = loop._requeue_ci_failed_prs()

    issue = store.get_healer_issue("50447")
    assert requeued == 1
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["pr_number"] == 247
    assert issue["last_failure_class"] == "ci_failed"
    assert "Existing PR feedback" in str(issue["feedback_context"] or "")
    assert "[ci_failure_feedback]" in str(issue["feedback_context"] or "")
    assert "Failure buckets: lint" in str(issue["feedback_context"] or "")
    assert "lint [lint] via check_run" in str(issue["feedback_context"] or "")
    assert store.get_state("healer_ci_handled_signal:50447") != ""


def test_requeue_ci_failed_pr_skips_non_retriable_buckets(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="50448",
        repo="owner/repo",
        title="Issue 50448",
        body="Preview is red",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.increment_healer_attempt("50448")
    store.set_healer_issue_state(
        issue_id="50448",
        state="pr_open",
        pr_number=248,
        pr_state="open",
        ci_status_summary={
            "head_sha": "ghi789",
            "overall_state": "failure",
            "failure_buckets": ["deploy_blocked"],
            "failing_entries": [
                {
                    "source": "workflow_run",
                    "name": "Preview",
                    "state": "failure",
                    "bucket": "deploy_blocked",
                    "updated_at": "2026-03-11T22:06:00Z",
                }
            ],
            "updated_at": "2026-03-11T22:06:00Z",
        },
    )

    loop = _make_loop(store, healer_retry_budget=3)

    requeued = loop._requeue_ci_failed_prs()

    issue = store.get_healer_issue("50448")
    assert requeued == 0
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert issue["last_failure_class"] == ""
    assert store.get_state("healer_ci_handled_signal:50448") != ""


def test_requeue_ci_failed_pr_skips_transient_infra_failures(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="504481",
        repo="owner/repo",
        title="Issue 504481",
        body="Runner timed out",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.increment_healer_attempt("504481")
    store.set_healer_issue_state(
        issue_id="504481",
        state="pr_open",
        pr_number=348,
        pr_state="open",
        ci_status_summary={
            "head_sha": "transient123",
            "overall_state": "failure",
            "failure_buckets": ["setup"],
            "transient_failure_contexts": ["runner bootstrap timeout"],
            "transient_failure_entries": [
                {
                    "source": "check_run",
                    "name": "runner bootstrap timeout",
                    "state": "failure",
                    "bucket": "setup",
                    "failure_kind": "transient_infra",
                    "updated_at": "2026-03-11T22:06:30Z",
                }
            ],
            "deterministic_failure_entries": [],
            "failing_entries": [
                {
                    "source": "check_run",
                    "name": "runner bootstrap timeout",
                    "state": "failure",
                    "bucket": "setup",
                    "failure_kind": "transient_infra",
                    "updated_at": "2026-03-11T22:06:30Z",
                }
            ],
            "updated_at": "2026-03-11T22:06:30Z",
        },
    )

    loop = _make_loop(store, healer_retry_budget=3)

    requeued = loop._requeue_ci_failed_prs()

    issue = store.get_healer_issue("504481")
    assert requeued == 0
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert issue["last_failure_class"] == ""
    assert store.get_state("healer_ci_handled_signal:504481") != ""


def test_requeue_ci_failed_pr_stops_after_retry_budget(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="50449",
        repo="owner/repo",
        title="Issue 50449",
        body="Retry budget exhausted",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.increment_healer_attempt("50449")
    store.increment_healer_attempt("50449")
    store.set_healer_issue_state(
        issue_id="50449",
        state="pr_open",
        pr_number=249,
        pr_state="open",
        ci_status_summary={
            "head_sha": "jkl012",
            "overall_state": "failure",
            "failure_buckets": ["test"],
            "failing_entries": [
                {
                    "source": "check_run",
                    "name": "pytest",
                    "state": "failure",
                    "bucket": "test",
                    "updated_at": "2026-03-11T22:07:00Z",
                }
            ],
            "updated_at": "2026-03-11T22:07:00Z",
        },
    )

    loop = _make_loop(store, healer_retry_budget=2)

    requeued = loop._requeue_ci_failed_prs()

    issue = store.get_healer_issue("50449")
    assert requeued == 0
    assert issue is not None
    assert issue["state"] == "pr_open"
    assert issue["last_failure_class"] == "ci_retry_exhausted"
    assert "Remote CI failed for PR #249" in str(issue["last_failure_reason"] or "")
    assert store.get_state("healer_ci_handled_signal:50449") != ""
