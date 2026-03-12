import json

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


def test_resource_audit_reports_artifact_roots_and_app_runtime_refs(tmp_path, monkeypatch) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    workspace_manager = HealerWorkspaceManager(repo_path=repo_path)
    reconciler = HealerReconciler(store=store, workspace_manager=workspace_manager)

    artifact_root = tmp_path / "artifacts" / "issue-9"
    artifact_root.mkdir(parents=True)
    store.set_state(
        "healer_artifact_root_ref:9:failure",
        json.dumps({"issue_id": "9", "path": str(artifact_root)}),
    )
    store.set_state(
        "healer_app_runtime_ref:9:web",
        json.dumps({"issue_id": "9", "pid": 901, "pgid": 901, "profile": "node-next-web"}),
    )
    browser_phase_root = tmp_path / "artifacts" / "browser" / "issue-9" / "failure"
    browser_phase_root.mkdir(parents=True)
    store.set_state(
        "healer_browser_session_ref:9:attempt-1",
        json.dumps(
            {
                "issue_id": "9",
                "attempt_id": "attempt-1",
                "path": str(browser_phase_root),
            }
        ),
    )

    monkeypatch.setattr(
        "flow_healer.healer_reconciler._list_process_snapshots",
        lambda: [],
    )

    audit = reconciler.resource_audit()

    assert audit["artifacts"]["tracked_roots"] == 1
    assert audit["artifacts"]["existing_roots"] == 1
    assert audit["app_runtimes"]["tracked"] == 1
    assert audit["app_runtimes"]["live_process_groups"] == 0
    assert audit["browser_sessions"]["tracked"] == 1
    assert audit["browser_sessions"]["existing_roots"] == 1
