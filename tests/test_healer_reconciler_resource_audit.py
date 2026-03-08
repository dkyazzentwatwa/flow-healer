from flow_healer.healer_reconciler import HealerReconciler
from flow_healer.healer_workspace import HealerWorkspaceManager
from flow_healer.store import SQLiteStore


def test_resource_audit_reports_worktrees_leases_locks_and_docker_placeholder(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    reconciler = HealerReconciler(store=store, workspace_manager=workspace_manager)

    store.upsert_healer_issue(
        issue_id="1",
        repo="owner/repo",
        title="Issue 1",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    claimed = store.claim_next_healer_issue(worker_id="worker-1", lease_seconds=120, max_active_issues=1)
    assert claimed is not None
    store.acquire_healer_lock(
        issue_id="1",
        lock_key="repo:*",
        granularity="repo",
        lease_owner="worker-1",
        lease_seconds=120,
    )
    (workspace_manager.worktrees_root / "issue-1").mkdir(parents=True)

    audit = reconciler.resource_audit()

    assert audit["worktrees"]["count"] == 1
    assert audit["leases"]["total"] == 1
    assert audit["locks"]["active"] == 1
    assert audit["locks"]["by_issue"]["1"] == 1
    assert audit["docker"]["mode"] == "placeholder"
    assert audit["docker"]["prune_enabled"] is False

