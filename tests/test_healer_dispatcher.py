"""Tests for HealerDispatcher — claim/lock logic."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flow_healer.healer_dispatcher import HealerDispatcher, LockAcquireResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeStore:
    """Minimal fake store for dispatcher tests."""

    def __init__(self, queued_issue: dict | None = None) -> None:
        self._queued_issue = queued_issue
        self.claimed_kwargs: list[dict] = []
        self.lock_batches: list[tuple] = []  # (lock_keys, issue_id, acquired_keys)
        self.released: list[str] = []
        self.state_changes: list[tuple[str, str]] = []
        self._locks: list[dict] = []
        # Simulate lock conflict by marking specific keys as held by another issue
        self._conflict_key: str | None = None

    def claim_next_healer_issue(self, *, worker_id, lease_seconds, max_active_issues, enforce_scope_queue=True):
        self.claimed_kwargs.append(dict(worker_id=worker_id, lease_seconds=lease_seconds))
        return dict(self._queued_issue) if self._queued_issue else None

    def acquire_healer_locks_batch(self, *, lock_keys, issue_id, lease_owner, lease_seconds):
        if self._conflict_key and self._conflict_key in lock_keys:
            return False, self._conflict_key, []
        acquired = list(lock_keys)
        self._locks.extend({"lock_key": k, "issue_id": issue_id} for k in acquired)
        self.lock_batches.append((lock_keys, issue_id, acquired))
        return True, None, acquired

    def list_healer_locks(self, *, issue_id=None):
        if issue_id is None:
            return list(self._locks)
        return [e for e in self._locks if e.get("issue_id") == issue_id]

    def release_healer_locks(self, *, issue_id):
        self._locks = [e for e in self._locks if e.get("issue_id") != issue_id]
        self.released.append(issue_id)

    def set_healer_issue_state(self, *, issue_id, state, **_kwargs):
        self.state_changes.append((issue_id, state))
        return True


def _make_dispatcher(store, *, max_active_issues=3) -> HealerDispatcher:
    return HealerDispatcher(
        store=store,
        worker_id="worker-1",
        lease_seconds=60,
        max_active_issues=max_active_issues,
    )


# ---------------------------------------------------------------------------
# Tests: claim_next_issue
# ---------------------------------------------------------------------------

def test_claim_next_issue_returns_none_when_no_issues():
    store = _FakeStore(queued_issue=None)
    dispatcher = _make_dispatcher(store)
    result = dispatcher.claim_next_issue()
    assert result is None
    assert len(store.claimed_kwargs) == 1
    assert store.claimed_kwargs[0]["worker_id"] == "worker-1"


def test_claim_next_issue_returns_issue_when_available():
    issue = {"issue_id": "42", "state": "queued", "title": "Fix bug"}
    store = _FakeStore(queued_issue=issue)
    dispatcher = _make_dispatcher(store)
    result = dispatcher.claim_next_issue()
    assert result is not None
    assert result["issue_id"] == "42"
    assert result["title"] == "Fix bug"


# ---------------------------------------------------------------------------
# Tests: acquire_prediction_locks
# ---------------------------------------------------------------------------

def test_acquire_prediction_locks_success():
    store = _FakeStore()
    dispatcher = _make_dispatcher(store)
    result = dispatcher.acquire_prediction_locks(
        issue_id="42", lock_keys=["src/auth.py", "tests/test_auth.py"]
    )
    assert isinstance(result, LockAcquireResult)
    assert result.acquired is True
    assert result.reason == ""
    assert set(result.keys) == {"src/auth.py", "tests/test_auth.py"}


def test_acquire_prediction_locks_conflict():
    store = _FakeStore()
    store._conflict_key = "src/auth.py"
    dispatcher = _make_dispatcher(store)
    result = dispatcher.acquire_prediction_locks(
        issue_id="42", lock_keys=["src/auth.py", "tests/test_auth.py"]
    )
    assert result.acquired is False
    assert "src/auth.py" in result.reason
    assert result.keys == []


# ---------------------------------------------------------------------------
# Tests: upgrade_locks
# ---------------------------------------------------------------------------

def test_upgrade_locks_skips_already_held_keys():
    store = _FakeStore()
    dispatcher = _make_dispatcher(store)
    # Pre-acquire "src/auth.py"
    dispatcher.acquire_prediction_locks(issue_id="42", lock_keys=["src/auth.py"])
    initial_batch_count = len(store.lock_batches)

    # Upgrade: add "tests/test_auth.py", but "src/auth.py" is already held
    result = dispatcher.upgrade_locks(issue_id="42", lock_keys=["src/auth.py", "tests/test_auth.py"])
    assert result.acquired is True
    # Only the new key was acquired in the second batch
    if len(store.lock_batches) > initial_batch_count:
        second_batch_keys = store.lock_batches[-1][0]
        assert "src/auth.py" not in second_batch_keys, "Already-held key should be skipped"
        assert "tests/test_auth.py" in second_batch_keys


def test_upgrade_locks_all_already_held_returns_success_without_store_call():
    store = _FakeStore()
    dispatcher = _make_dispatcher(store)
    # Pre-acquire both keys
    dispatcher.acquire_prediction_locks(issue_id="42", lock_keys=["src/auth.py"])
    batch_count_before = len(store.lock_batches)

    # Upgrade with a key already held — should not call acquire again
    result = dispatcher.upgrade_locks(issue_id="42", lock_keys=["src/auth.py"])
    assert result.acquired is True
    assert len(store.lock_batches) == batch_count_before, "No new batch when all keys already held"


# ---------------------------------------------------------------------------
# Tests: release_issue
# ---------------------------------------------------------------------------

def test_release_issue_calls_store_methods():
    store = _FakeStore()
    dispatcher = _make_dispatcher(store)
    dispatcher.release_issue(issue_id="42")
    assert "42" in store.released
    assert ("42", "queued") in store.state_changes
