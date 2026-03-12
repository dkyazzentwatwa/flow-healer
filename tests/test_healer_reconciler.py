from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path

from flow_healer.app_harness import AppRuntimeProfile
from flow_healer import healer_reconciler as reconciler_module
from flow_healer.healer_reconciler import HealerReconciler
from flow_healer.healer_workspace import HealerWorkspaceManager
from flow_healer.store import SQLiteStore
from flow_healer.swarm_markers import SWARM_PROCESS_MARKER


def test_reconcile_cleans_inactive_issue_workspaces(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    reconciler = HealerReconciler(store=store, workspace_manager=workspace_manager)

    stale_workspace = workspace_manager.worktrees_root / "issue-1-stale"
    stale_workspace.mkdir(parents=True)
    store.upsert_healer_issue(
        issue_id="1",
        repo="owner/repo",
        title="Issue 1",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="1",
        state="failed",
        workspace_path=str(stale_workspace),
        branch_name="healer/issue-1-stale",
    )

    summary = reconciler.reconcile()
    issue = store.get_healer_issue("1")

    assert summary["cleaned_inactive_workspaces"] == 1
    assert issue is not None
    assert issue["workspace_path"] == ""
    assert issue["branch_name"] == ""
    assert not stale_workspace.exists()


def test_reconcile_interrupts_running_attempt_for_inactive_issue(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    reconciler = HealerReconciler(store=store, workspace_manager=workspace_manager)

    store.upsert_healer_issue(
        issue_id="2",
        repo="owner/repo",
        title="Issue 2",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="2", state="queued")
    store.create_healer_attempt(
        attempt_id="ha_stale",
        issue_id="2",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )

    summary = reconciler.reconcile()
    attempts = store.list_healer_attempts(issue_id="2")

    assert summary["interrupted_inactive_attempts"] == 1
    assert attempts[0]["state"] == "interrupted"
    assert attempts[0]["failure_class"] == "interrupted"


def test_reconcile_interrupts_superseded_running_attempt(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    reconciler = HealerReconciler(store=store, workspace_manager=workspace_manager)

    store.upsert_healer_issue(
        issue_id="3",
        repo="owner/repo",
        title="Issue 3",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="3", state="running")
    with store._lock:
        conn = store._connect()
        conn.execute(
            "UPDATE healer_issues SET lease_owner = ?, lease_expires_at = ? WHERE issue_id = ?",
            (
                "worker-a",
                (datetime.now(tz=UTC) + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
                "3",
            ),
        )
        conn.commit()
    store.create_healer_attempt(
        attempt_id="ha_old",
        issue_id="3",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.increment_healer_attempt("3")
    store.increment_healer_attempt("3")
    store.create_healer_attempt(
        attempt_id="ha_current",
        issue_id="3",
        attempt_no=2,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )

    summary = reconciler.reconcile()
    attempts = {attempt["attempt_id"]: attempt for attempt in store.list_healer_attempts(issue_id="3", limit=5)}

    assert summary["interrupted_superseded_attempts"] == 1
    assert attempts["ha_old"]["state"] == "interrupted"
    assert attempts["ha_current"]["state"] == "running"


def test_reconcile_recovers_stale_active_issue_from_previous_worker_session(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    stale_workspace = workspace_manager.worktrees_root / "issue-7-stale"
    stale_workspace.mkdir(parents=True)
    reconciler = HealerReconciler(
        store=store,
        workspace_manager=workspace_manager,
        current_worker_id="healer_new",
    )

    store.upsert_healer_issue(
        issue_id="7",
        repo="owner/repo",
        title="Issue 7",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="7",
        state="running",
        workspace_path=str(stale_workspace),
        branch_name="healer/issue-7-stale",
    )
    with store._lock:
        conn = store._connect()
        conn.execute(
            "UPDATE healer_issues SET lease_owner = ?, lease_expires_at = ? WHERE issue_id = ?",
            (
                "healer_old",
                (datetime.now(tz=UTC) + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
                "7",
            ),
        )
        conn.commit()
    store.create_healer_attempt(
        attempt_id="ha_stale_worker",
        issue_id="7",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    store.acquire_healer_lock(
        lock_key="repo:*",
        granularity="repo",
        issue_id="7",
        lease_owner="healer_old",
        lease_seconds=300,
    )

    summary = reconciler.reconcile()
    issue = store.get_healer_issue("7")
    attempts = store.list_healer_attempts(issue_id="7")

    assert summary["recovered_stale_active_issues"] == 1
    assert summary["interrupted_inactive_attempts"] == 1
    assert issue is not None
    assert issue["state"] == "queued"
    assert issue["lease_owner"] in {"", None}
    assert issue["workspace_path"] == ""
    assert attempts[0]["state"] == "interrupted"
    assert store.list_healer_locks(issue_id="7") == []
    assert not stale_workspace.exists()


def test_reconcile_requeues_active_issue_without_any_lease(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    reconciler = HealerReconciler(
        store=store,
        workspace_manager=workspace_manager,
        current_worker_id="healer_new",
    )

    store.upsert_healer_issue(
        issue_id="17",
        repo="owner/repo",
        title="Issue 17",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="17", state="claimed")

    summary = reconciler.reconcile()
    issue = store.get_healer_issue("17")

    assert summary["recovered_leases"] == 1
    assert issue is not None
    assert issue["state"] == "queued"


def test_sweep_orphan_workspaces_skips_store_scan_when_root_missing(tmp_path, monkeypatch) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    reconciler = HealerReconciler(store=store, workspace_manager=workspace_manager)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("workspace refs should not be queried when worktrees root is missing")

    monkeypatch.setattr(store, "list_healer_issue_workspace_refs", fail_if_called)

    assert reconciler._sweep_orphan_workspaces() == 0


def test_reconcile_preserves_queued_workspace_with_active_lease(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    reconciler = HealerReconciler(store=store, workspace_manager=workspace_manager)

    queued_workspace = workspace_manager.worktrees_root / "issue-5-queued"
    queued_workspace.mkdir(parents=True)
    store.upsert_healer_issue(
        issue_id="5",
        repo="owner/repo",
        title="Issue 5",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="5",
        state="queued",
        workspace_path=str(queued_workspace),
        branch_name="healer/issue-5-queued",
    )
    with store._lock:
        conn = store._connect()
        conn.execute(
            "UPDATE healer_issues SET lease_owner = ?, lease_expires_at = ? WHERE issue_id = ?",
            (
                "worker-a",
                (datetime.now(tz=UTC) + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
                "5",
            ),
        )
        conn.commit()

    summary = reconciler.reconcile()
    issue = store.get_healer_issue("5")

    assert summary["cleaned_inactive_workspaces"] == 0
    assert summary["removed_orphans"] == 0
    assert queued_workspace.exists()
    assert issue is not None
    assert issue["workspace_path"] == str(queued_workspace)


def test_reconcile_cleans_queued_workspace_with_expired_lease(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    reconciler = HealerReconciler(store=store, workspace_manager=workspace_manager)

    queued_workspace = workspace_manager.worktrees_root / "issue-6-queued"
    queued_workspace.mkdir(parents=True)
    store.upsert_healer_issue(
        issue_id="6",
        repo="owner/repo",
        title="Issue 6",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="6",
        state="queued",
        workspace_path=str(queued_workspace),
        branch_name="healer/issue-6-queued",
    )
    with store._lock:
        conn = store._connect()
        conn.execute(
            "UPDATE healer_issues SET lease_owner = ?, lease_expires_at = ? WHERE issue_id = ?",
            (
                "worker-a",
                (datetime.now(tz=UTC) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
                "6",
            ),
        )
        conn.commit()

    summary = reconciler.reconcile()
    issue = store.get_healer_issue("6")

    assert summary["cleaned_inactive_workspaces"] == 1
    assert not queued_workspace.exists()
    assert issue is not None
    assert issue["workspace_path"] == ""


def test_reconcile_reaps_orphan_swarm_subagent_process_groups(tmp_path, monkeypatch) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    reconciler = HealerReconciler(
        store=store,
        workspace_manager=workspace_manager,
        swarm_orphan_subagent_ttl_seconds=900,
    )

    monkeypatch.setattr(
        reconciler_module,
        "_list_process_snapshots",
        lambda: [
            reconciler_module._ProcessSnapshot(
                pid=101,
                ppid=1,
                pgid=101,
                elapsed_seconds=1200,
                command=f"node /opt/homebrew/bin/codex exec ... {SWARM_PROCESS_MARKER} ... subagent for Flow Healer",
            ),
            reconciler_module._ProcessSnapshot(
                pid=111,
                ppid=1,
                pgid=111,
                elapsed_seconds=1300,
                command="node /opt/homebrew/bin/codex exec ... subagent for Flow Healer",
            ),
            reconciler_module._ProcessSnapshot(
                pid=202,
                ppid=1,
                pgid=202,
                elapsed_seconds=300,
                command=f"node /opt/homebrew/bin/codex exec ... {SWARM_PROCESS_MARKER} ... subagent for Flow Healer",
            ),
            reconciler_module._ProcessSnapshot(
                pid=303,
                ppid=777,
                pgid=303,
                elapsed_seconds=1500,
                command=f"node /opt/homebrew/bin/codex exec ... {SWARM_PROCESS_MARKER} ... subagent for Flow Healer",
            ),
        ],
    )
    killed_groups: list[int] = []
    monkeypatch.setattr(
        reconciler_module,
        "_terminate_process_group",
        lambda pgid: killed_groups.append(pgid) or True,
    )

    summary = reconciler.reconcile()

    assert summary["reaped_orphan_subagents"] == 1
    assert killed_groups == [101]


def test_reconcile_cleans_stale_local_artifact_roots_but_preserves_active_issue_refs(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    reconciler = HealerReconciler(
        store=store,
        workspace_manager=workspace_manager,
        artifact_retention_days=30,
    )

    stale_root = tmp_path / "artifacts" / "issue-41"
    stale_root.mkdir(parents=True)
    active_root = tmp_path / "artifacts" / "issue-42"
    active_root.mkdir(parents=True)
    old_mtime = (datetime.now(tz=UTC) - timedelta(days=45)).timestamp()
    os.utime(stale_root, (old_mtime, old_mtime))
    os.utime(active_root, (old_mtime, old_mtime))

    store.upsert_healer_issue(
        issue_id="41",
        repo="owner/repo",
        title="Issue 41",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="41", state="failed")
    store.set_state(
        "healer_artifact_root_ref:41:failure",
        json.dumps({"issue_id": "41", "path": str(stale_root)}),
    )

    store.upsert_healer_issue(
        issue_id="42",
        repo="owner/repo",
        title="Issue 42",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="42", state="running")
    with store._lock:
        conn = store._connect()
        conn.execute(
            "UPDATE healer_issues SET lease_owner = ?, lease_expires_at = ? WHERE issue_id = ?",
            (
                "worker-42",
                (datetime.now(tz=UTC) + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
                "42",
            ),
        )
        conn.commit()
    store.set_state(
        "healer_artifact_root_ref:42:failure",
        json.dumps({"issue_id": "42", "path": str(active_root)}),
    )

    summary = reconciler.reconcile()

    assert summary["cleaned_artifact_roots"] == 1
    assert not stale_root.exists()
    assert active_root.exists()


def test_reconcile_reaps_orphan_app_runtime_process_groups_from_runtime_refs(tmp_path, monkeypatch) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    reconciler = HealerReconciler(
        store=store,
        workspace_manager=workspace_manager,
        app_runtime_orphan_ttl_seconds=900,
    )

    store.upsert_healer_issue(
        issue_id="51",
        repo="owner/repo",
        title="Issue 51",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="51", state="failed")
    store.set_state(
        "healer_app_runtime_ref:51:web",
        json.dumps({"issue_id": "51", "pid": 501, "pgid": 501, "profile": "node-next-web"}),
    )

    monkeypatch.setattr(
        reconciler_module,
        "_list_process_snapshots",
        lambda: [
            reconciler_module._ProcessSnapshot(
                pid=501,
                ppid=1,
                pgid=501,
                elapsed_seconds=1200,
                command="npm run dev // flow-healer app-runtime profile=node-next-web issue=51",
            )
        ],
    )
    killed_groups: list[int] = []
    monkeypatch.setattr(
        reconciler_module,
        "_terminate_process_group",
        lambda pgid: killed_groups.append(pgid) or True,
    )

    summary = reconciler.reconcile()

    assert summary["reaped_orphan_app_runtimes"] == 1
    assert killed_groups == [501]


def test_reconcile_cleans_stale_browser_session_refs(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    reconciler = HealerReconciler(
        store=store,
        workspace_manager=workspace_manager,
        artifact_retention_days=30,
    )

    stale_phase_root = tmp_path / "artifacts" / "browser" / "issue-61" / "failure"
    stale_phase_root.mkdir(parents=True)
    store.upsert_healer_issue(
        issue_id="61",
        repo="owner/repo",
        title="Issue 61",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(issue_id="61", state="failed")
    store.set_state(
        "healer_browser_session_ref:61:attempt-1",
        json.dumps(
            {
                "issue_id": "61",
                "attempt_id": "attempt-1",
                "path": str(stale_phase_root),
                "retention_until": (datetime.now(tz=UTC) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
            }
        ),
    )

    summary = reconciler.reconcile()

    assert summary["cleaned_browser_sessions"] == 1
    assert not stale_phase_root.exists()
    assert store.get_state("healer_browser_session_ref:61:attempt-1") == ""


def test_reconcile_detects_stale_runtime_profiles(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    fresh_profile_root = repo_path / "fresh"
    fresh_profile_root.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    stale_seen_at = (datetime.now(tz=UTC) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    fresh_seen_at = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
    store.set_states(
        {
            "healer_app_runtime_profile_last_seen_at:web": stale_seen_at,
            "healer_app_runtime_profile_last_seen_at:fresh": fresh_seen_at,
        }
    )
    reconciler = HealerReconciler(
        store=store,
        workspace_manager=workspace_manager,
        runtime_profiles={
            "web": AppRuntimeProfile(
                name="web",
                command=("npm", "run", "dev"),
                cwd=repo_path / "missing-web",
                readiness_url="http://127.0.0.1:3000",
            ),
            "fresh": AppRuntimeProfile(
                name="fresh",
                command=("npm", "run", "dev"),
                cwd=fresh_profile_root,
                readiness_url="http://127.0.0.1:3001",
            ),
        },
        app_runtime_stale_days=14,
    )

    summary = reconciler.reconcile()

    assert summary["stale_runtime_profiles_detected"] == 1
    assert json.loads(store.get_state("healer_stale_runtime_profiles") or "[]") == ["web"]
    assert store.get_state("healer_stale_runtime_profiles_detected") == "1"


def test_reconcile_detects_stale_runtime_profiles_for_dict_backed_config(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    fresh_profile_root = repo_path / "web"
    fresh_profile_root.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    fresh_seen_at = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
    store.set_state("healer_app_runtime_profile_last_seen_at:web", fresh_seen_at)
    reconciler = HealerReconciler(
        store=store,
        workspace_manager=workspace_manager,
        runtime_profiles={
            "web": {
                "name": "web",
                "working_directory": "web",
                "start_command": "npm run dev",
                "readiness_url": "http://127.0.0.1:3000",
            }
        },
        app_runtime_stale_days=14,
    )

    summary = reconciler.reconcile()

    assert summary["stale_runtime_profiles_detected"] == 0
    assert json.loads(store.get_state("healer_stale_runtime_profiles") or "[]") == []
