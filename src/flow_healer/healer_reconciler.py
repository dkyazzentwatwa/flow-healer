from __future__ import annotations

import logging
from pathlib import Path

from .healer_workspace import HealerWorkspaceManager
from .store import SQLiteStore

logger = logging.getLogger("apple_flow.healer_reconciler")


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

    def _cleanup_inactive_issue_workspaces(self) -> int:
        inactive_rows = self.store.list_healer_issue_workspace_refs(
            states=["queued", "failed", "resolved", "archived", "blocked", "pr_pending_approval", "pr_open"],
            limit=2000,
        )
        cleaned = 0
        for row in inactive_rows:
            workspace_raw = str(row.get("workspace_path") or "").strip()
            if not workspace_raw:
                continue
            issue_id = str(row.get("issue_id") or "")
            state = str(row.get("state") or "queued")
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
            states=["queued", "claimed", "running", "verify_pending", "pr_pending_approval", "pr_open", "blocked"],
            limit=2000,
        )
        active_paths = {
            str(Path(row.get("workspace_path") or "").resolve())
            for row in active_rows
            if (row.get("workspace_path") or "").strip()
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
