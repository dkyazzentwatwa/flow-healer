from flow_healer.healer_locks import (
    canonicalize_lock_keys,
    diff_paths_to_lock_keys,
    lock_keys_conflict,
    predict_lock_set,
)
from flow_healer.store import SQLiteStore


def test_predict_lock_set_from_issue_text_paths():
    prediction = predict_lock_set(issue_text="fails in src/apple_flow/store.py and tests/test_store.py")
    assert prediction.keys
    assert prediction.source in {"path_level", "directory_escalation"}
    assert all(key.startswith(("path:", "dir:", "module:", "repo:")) for key in prediction.keys)


def test_predict_lock_set_falls_back_to_repo_lock():
    prediction = predict_lock_set(issue_text="no explicit file paths mentioned")
    assert prediction.keys == ["repo:*"]
    assert prediction.source == "coarse_repo_lock"


def test_predict_lock_set_detects_root_file_mentions():
    prediction = predict_lock_set(issue_text="Create a roadmap.md for future work")
    assert prediction.keys == ["path:roadmap.md"]
    assert prediction.source == "path_level"


def test_predict_lock_set_detects_path_prefixed_feedback():
    prediction = predict_lock_set(issue_text="Keep the change scoped to path:config.example.yaml")
    assert prediction.keys == ["path:config.example.yaml"]
    assert prediction.source == "path_level"


def test_diff_paths_to_lock_keys_escalates_for_large_sets():
    keys = diff_paths_to_lock_keys([f"src/pkg/file_{i}.py" for i in range(20)])
    assert keys
    assert all(key.startswith("dir:") for key in keys)


def test_canonicalize_lock_keys_dedupes_and_sorts():
    keys = canonicalize_lock_keys(["PATH:src/a.py", "path:src/a.py", "repo:*", ""])
    assert keys == ["path:src/a.py", "repo:*"]


def test_lock_keys_conflict_detects_nested_scopes():
    assert lock_keys_conflict("repo:*", "path:src/a.py") is True
    assert lock_keys_conflict("dir:src/pkg", "path:src/pkg/file.py") is True
    assert lock_keys_conflict("dir:src/pkg", "path:src/other.py") is False


def test_store_rejects_overlapping_lock_scopes(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()

    assert (
        store.acquire_healer_lock(
            lock_key="dir:src/flow_healer",
            granularity="dir",
            issue_id="10",
            lease_owner="worker-a",
            lease_seconds=60,
        )
        is True
    )
    assert (
        store.acquire_healer_lock(
            lock_key="path:src/flow_healer/healer_locks.py",
            granularity="path",
            issue_id="11",
            lease_owner="worker-b",
            lease_seconds=60,
        )
        is False
    )


def test_store_batch_acquires_multiple_non_conflicting_locks(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()

    acquired, conflict_key, keys = store.acquire_healer_locks_batch(
        lock_keys=["path:src/a.py", "path:src/b.py"],
        issue_id="20",
        lease_owner="worker-a",
        lease_seconds=60,
    )

    assert acquired is True
    assert conflict_key == ""
    assert keys == ["path:src/a.py", "path:src/b.py"]
    rows = store.list_healer_locks(issue_id="20")
    assert [row["lock_key"] for row in rows] == ["path:src/a.py", "path:src/b.py"]


def test_store_batch_rejects_conflict_without_partial_insert(tmp_path):
    store = SQLiteStore(tmp_path / "relay.db")
    store.bootstrap()
    assert store.acquire_healer_lock(
        lock_key="dir:src/flow_healer",
        granularity="dir",
        issue_id="30",
        lease_owner="worker-a",
        lease_seconds=60,
    )

    acquired, conflict_key, keys = store.acquire_healer_locks_batch(
        lock_keys=["path:src/example.py", "path:src/flow_healer/healer_locks.py"],
        issue_id="31",
        lease_owner="worker-b",
        lease_seconds=60,
    )

    assert acquired is False
    assert conflict_key == "path:src/flow_healer/healer_locks.py"
    assert keys == []
    assert store.list_healer_locks(issue_id="31") == []
