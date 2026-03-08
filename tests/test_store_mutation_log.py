from __future__ import annotations

from flow_healer.store import SQLiteStore


def test_claim_healer_mutation_reclaims_stale_pending_row(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()

    assert store.claim_healer_mutation(
        mutation_key="issue:100:comment:1",
        lease_owner="worker-a",
        lease_seconds=1,
    ) == "claimed"
    assert (
        store.claim_healer_mutation(
            mutation_key="issue:100:comment:1",
            lease_owner="worker-b",
            lease_seconds=60,
        )
        == "inflight"
    )

    conn = store._connect()
    conn.execute(
        "UPDATE healer_mutation_log SET lease_expires_at = datetime('now', '-5 seconds') WHERE mutation_key = ?",
        ("issue:100:comment:1",),
    )
    conn.commit()

    assert (
        store.claim_healer_mutation(
            mutation_key="issue:100:comment:1",
            lease_owner="worker-b",
            lease_seconds=60,
        )
        == "claimed"
    )
    row = conn.execute(
        "SELECT lease_owner, retry_count FROM healer_mutation_log WHERE mutation_key = ?",
        ("issue:100:comment:1",),
    ).fetchone()
    assert row is not None
    assert row["lease_owner"] == "worker-b"
    assert int(row["retry_count"]) == 1


def test_release_healer_locks_for_owner_does_not_clear_newer_owner_lock(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()

    assert (
        store.acquire_healer_lock(
            lock_key="path:src/a.py",
            granularity="path",
            issue_id="200",
            lease_owner="worker-new",
            lease_seconds=60,
        )
        is True
    )

    released = store.release_healer_locks_for_owner(issue_id="200", lease_owner="worker-old")
    assert released == 0
    assert [entry["lease_owner"] for entry in store.list_healer_locks(issue_id="200")] == ["worker-new"]

    released = store.release_healer_locks_for_owner(issue_id="200", lease_owner="worker-new")
    assert released == 1
    assert store.list_healer_locks(issue_id="200") == []
