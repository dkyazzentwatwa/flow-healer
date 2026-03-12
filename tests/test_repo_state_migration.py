from __future__ import annotations

from pathlib import Path

from flow_healer.repo_state_migration import migrate_repo_state
from flow_healer.store import SQLiteStore


def _make_store(db_path: Path) -> SQLiteStore:
    store = SQLiteStore(db_path)
    store.bootstrap()
    return store


def test_migrate_repo_state_moves_live_issue_attempts_and_pause_flag(tmp_path) -> None:
    source_db = tmp_path / "source" / "state.db"
    target_db = tmp_path / "target" / "state.db"

    source = _make_store(source_db)
    source.set_state("healer_paused", "false")
    source.upsert_healer_issue(
        issue_id="926",
        repo="owner/repo",
        title="Phase 2 eval: Node smoke add contract",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=1,
    )
    source._connect().execute(
        "UPDATE healer_issues SET state = 'running', lease_owner = 'worker-1', lease_expires_at = '2026-03-12 08:00:00' "
        "WHERE issue_id = '926'"
    )
    source._connect().commit()
    source.create_healer_attempt(
        attempt_id="ha_926_1",
        issue_id="926",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    source.finish_healer_attempt(
        attempt_id="ha_926_1",
        state="failed",
        actual_diff_set=[],
        test_summary={"execution_root_source": "issue"},
        verifier_summary={},
        failure_class="no_workspace_change:narrative_only",
        failure_reason="narrative only",
    )
    source.close()

    target = _make_store(target_db)
    target.set_state("healer_paused", "true")
    target.close()

    summary = migrate_repo_state(source_db=source_db, target_db=target_db)

    migrated = _make_store(target_db)
    issues = migrated.list_healer_issues(limit=20)
    attempts = migrated.list_recent_healer_attempts(limit=20)

    assert summary["source_repo_name"] == "flow-healer"
    assert summary["target_repo_name"] == "flow-healer-self"
    assert summary["tables"]["healer_issues"]["upserted"] == 1
    assert summary["tables"]["healer_attempts"]["upserted"] == 1
    assert migrated.get_state("healer_paused") == "false"
    assert issues[0]["issue_id"] == "926"
    assert issues[0]["state"] == "queued"
    assert issues[0]["lease_owner"] == ""
    assert attempts[0]["attempt_id"] == "ha_926_1"
    migrated.close()


def test_migrate_repo_state_is_idempotent_for_same_source_signature(tmp_path) -> None:
    source_db = tmp_path / "source" / "state.db"
    target_db = tmp_path / "target" / "state.db"

    source = _make_store(source_db)
    source.upsert_healer_issue(
        issue_id="930",
        repo="owner/repo",
        title="Phase 2 eval: Python smoke math contract",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=1,
    )
    source.close()

    target = _make_store(target_db)
    target.close()

    first = migrate_repo_state(source_db=source_db, target_db=target_db)
    second = migrate_repo_state(source_db=source_db, target_db=target_db)

    migrated = _make_store(target_db)
    issues = migrated.list_healer_issues(limit=20)

    assert first["skipped"] is False
    assert second["skipped"] is True
    assert len(issues) == 1
    assert issues[0]["issue_id"] == "930"
    migrated.close()
