from pathlib import Path

from flow_healer.healer_reconciler import HealerReconciler
from flow_healer.healer_workspace import HealerWorkspaceManager
from flow_healer.store import SQLiteStore


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
