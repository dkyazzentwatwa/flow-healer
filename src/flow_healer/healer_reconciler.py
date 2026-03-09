from __future__ import annotations

import logging
import shutil
from pathlib import Path
from datetime import UTC, datetime

from .healer_workspace import HealerWorkspaceManager
from .store import SQLiteStore

logger = logging.getLogger("apple_flow.healer_reconciler")

_INACTIVE_CLEANUP_STATES = [
    "queued",
    "failed",
    "resolved",
    "archived",
    "blocked",
    "pr_pending_approval",
    "pr_open",
]
_ACTIVE_WORKSPACE_STATES = [
    "claimed",
    "running",
    "verify_pending",
    "pr_pending_approval",
    "pr_open",
    "blocked",
]


class HealerReconciler:
    def __init__(self, *, store: SQLiteStore, workspace_manager: HealerWorkspaceManager) -> None:
        self.store = store
        self.workspace_manager = workspace_manager

    def reconcile(self) -> dict[str, int]:
        recovered_leases = self.store.requeue_expired_healer_issue_leases()
        interrupted_inactive_attempts = self.store.interrupt_inactive_healer_attempts()
        interrupted_superseded_attempts = self.store.interrupt_superseded_healer_attempts()
        cleaned_inactive_workspaces = self._cleanup_inactive_issue_workspaces()
        expired_locks = self.store.cleanup_expired_healer_locks()
        removed_orphans = self._sweep_orphan_workspaces()
        return {
            "interrupted_inactive_attempts": interrupted_inactive_attempts,
            "interrupted_superseded_attempts": interrupted_superseded_attempts,
            "cleaned_inactive_workspaces": cleaned_inactive_workspaces,
            "recovered_leases": recovered_leases,
            "expired_locks": expired_locks,
            "removed_orphans": removed_orphans,
        }

    def resource_audit(self) -> dict[str, object]:
        workspaces = self.workspace_manager.list_workspaces() if self.workspace_manager.worktrees_root.exists() else []
        issues = self.store.list_healer_issues(limit=5000)
        locks = self.store.list_healer_locks()

        active_leases = 0
        expired_leases = 0
        for issue in issues:
            lease_owner = str(issue.get("lease_owner") or "").strip()
            lease_expires_at = str(issue.get("lease_expires_at") or "").strip()
            if not lease_owner and not lease_expires_at:
                continue
            if lease_expires_at and _is_expired_timestamp(lease_expires_at):
                expired_leases += 1
            else:
                active_leases += 1

        lock_counts_by_issue: dict[str, int] = {}
        for lock in locks:
            issue_id = str(lock.get("issue_id") or "").strip()
            if not issue_id:
                continue
            lock_counts_by_issue[issue_id] = lock_counts_by_issue.get(issue_id, 0) + 1

        return {
            "generated_at": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "worktrees": {
                "root": str(self.workspace_manager.worktrees_root),
                "count": len(workspaces),
            },
            "leases": {
                "active": active_leases,
                "expired": expired_leases,
                "total": active_leases + expired_leases,
            },
            "locks": {
                "active": len(locks),
                "by_issue": lock_counts_by_issue,
            },
            "docker": {
                "available": shutil.which("docker") is not None,
                "mode": "placeholder",
                "prune_enabled": False,
                "summary": "read_only_no_prune",
            },
        }

    def _cleanup_inactive_issue_workspaces(self) -> int:
        inactive_rows = self.store.list_healer_issue_workspace_refs(
            states=_INACTIVE_CLEANUP_STATES,
            limit=2000,
        )
        cleaned = 0
        for row in inactive_rows:
            workspace_raw = str(row.get("workspace_path") or "").strip()
            if not workspace_raw:
                continue
            issue_id = str(row.get("issue_id") or "")
            state = str(row.get("state") or "queued")
            if self._workspace_ref_has_active_lease(row):
                continue
            try:
                self.workspace_manager.remove_workspace(workspace_path=Path(workspace_raw))
            except Exception as exc:
                logger.warning("Failed to clean inactive workspace for issue #%s: %s", issue_id, exc)
                continue
            self.store.set_healer_issue_state(
                issue_id=issue_id,
                state=state,
                workspace_path="",
                branch_name="",
            )
            cleaned += 1
        return cleaned

    def _sweep_orphan_workspaces(self) -> int:
        if not self.workspace_manager.worktrees_root.exists():
            # Avoid a large issue-table scan on idle ticks when no healer worktrees exist.
            return 0
        active_rows = self.store.list_healer_issue_workspace_refs(
            states=["queued", *_ACTIVE_WORKSPACE_STATES],
            limit=2000,
        )
        active_paths = {
            str(Path(row.get("workspace_path") or "").resolve())
            for row in active_rows
            if (row.get("workspace_path") or "").strip() and self._workspace_ref_should_be_preserved(row)
        }
        removed = 0
        for workspace in self.workspace_manager.list_workspaces():
            if str(workspace.resolve()) in active_paths:
                continue
            try:
                self.workspace_manager.remove_workspace(workspace_path=workspace)
                removed += 1
            except Exception as exc:
                logger.warning("Failed to remove orphan workspace %s: %s", workspace, exc)
        return removed

    @staticmethod
    def _workspace_ref_should_be_preserved(row: dict[str, object]) -> bool:
        state = str(row.get("state") or "").strip()
        if state in _ACTIVE_WORKSPACE_STATES:
            return True
        # Queued workspaces are only preserved when they still have an active lease.
        return state == "queued" and HealerReconciler._workspace_ref_has_active_lease(row)

    @staticmethod
    def _workspace_ref_has_active_lease(row: dict[str, object]) -> bool:
        lease_owner = str(row.get("lease_owner") or "").strip()
        lease_expires_at = str(row.get("lease_expires_at") or "").strip()
        if not lease_owner and not lease_expires_at:
            return False
        if not lease_expires_at:
            return bool(lease_owner)
        return not _is_expired_timestamp(lease_expires_at)


def _is_expired_timestamp(raw: str) -> bool:
    normalized = str(raw or "").strip()
    if not normalized:
        return False
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = datetime.strptime(normalized, fmt).replace(tzinfo=UTC)
            return parsed <= datetime.now(tz=UTC)
        except ValueError:
            continue
    return False
