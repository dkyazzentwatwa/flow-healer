from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .healer_locks import canonicalize_lock_keys
from .store import SQLiteStore


@dataclass(slots=True, frozen=True)
class LockAcquireResult:
    acquired: bool
    keys: list[str]
    reason: str


class HealerDispatcher:
    def __init__(
        self,
        *,
        store: SQLiteStore,
        worker_id: str,
        lease_seconds: int,
        max_active_issues: int,
        overlap_scope_queue_enabled: bool = True,
    ) -> None:
        self.store = store
        self.worker_id = worker_id
        self.lease_seconds = max(30, int(lease_seconds))
        self.max_active_issues = max(1, int(max_active_issues))
        self.overlap_scope_queue_enabled = bool(overlap_scope_queue_enabled)

    def claim_next_issue(self) -> dict[str, Any] | None:
        return self.store.claim_next_healer_issue(
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
            max_active_issues=self.max_active_issues,
            enforce_scope_queue=self.overlap_scope_queue_enabled,
        )

    def acquire_prediction_locks(self, *, issue_id: str, lock_keys: list[str]) -> LockAcquireResult:
        keys = canonicalize_lock_keys(lock_keys)
        acquired, conflict_key, acquired_keys = self.store.acquire_healer_locks_batch(
            lock_keys=keys,
            issue_id=issue_id,
            lease_owner=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if not acquired:
            return LockAcquireResult(acquired=False, keys=[], reason=f"lock_conflict:{conflict_key}")
        return LockAcquireResult(acquired=True, keys=acquired_keys, reason="")

    def upgrade_locks(self, *, issue_id: str, lock_keys: list[str]) -> LockAcquireResult:
        existing = {entry.get("lock_key", "") for entry in self.store.list_healer_locks(issue_id=issue_id)}
        to_add = [key for key in canonicalize_lock_keys(lock_keys) if key not in existing]
        if not to_add:
            return LockAcquireResult(acquired=True, keys=[], reason="")
        return self.acquire_prediction_locks(issue_id=issue_id, lock_keys=to_add)

    def release_issue(self, *, issue_id: str) -> None:
        self.store.release_healer_locks(issue_id=issue_id)
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="queued",
            clear_lease=True,
        )
