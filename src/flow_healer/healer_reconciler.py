from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from datetime import UTC, datetime, timedelta

from .app_harness import AppRuntimeProfile
from .healer_workspace import HealerWorkspaceManager
from .store import SQLiteStore
from .swarm_markers import SWARM_PROCESS_MARKER

logger = logging.getLogger("apple_flow.healer_reconciler")

_ARTIFACT_ROOT_REF_PREFIX = "healer_artifact_root_ref:"
_APP_RUNTIME_REF_PREFIX = "healer_app_runtime_ref:"
_BROWSER_SESSION_REF_PREFIX = "healer_browser_session_ref:"

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
    def __init__(
        self,
        *,
        store: SQLiteStore,
        workspace_manager: HealerWorkspaceManager,
        current_worker_id: str = "",
        swarm_orphan_subagent_ttl_seconds: int = 900,
        artifact_retention_days: int = 30,
        app_runtime_orphan_ttl_seconds: int = 900,
        runtime_profiles: dict[str, AppRuntimeProfile] | None = None,
        app_runtime_stale_days: int = 14,
    ) -> None:
        self.store = store
        self.workspace_manager = workspace_manager
        self.current_worker_id = str(current_worker_id or "").strip()
        self.swarm_orphan_subagent_ttl_seconds = max(60, int(swarm_orphan_subagent_ttl_seconds))
        self.artifact_retention_days = max(1, int(artifact_retention_days))
        self.app_runtime_orphan_ttl_seconds = max(60, int(app_runtime_orphan_ttl_seconds))
        self.runtime_profiles = dict(runtime_profiles or {})
        self.app_runtime_stale_days = max(1, int(app_runtime_stale_days))

    def reconcile(self) -> dict[str, int]:
        recovered_leases = self.store.requeue_expired_healer_issue_leases()
        recovered_stale_active_issues = self._recover_stale_active_issues()
        interrupted_inactive_attempts = self.store.interrupt_inactive_healer_attempts()
        interrupted_superseded_attempts = self.store.interrupt_superseded_healer_attempts()
        reaped_orphan_subagents = self._reap_orphan_swarm_subagents()
        reaped_orphan_app_runtimes = self._reap_orphan_app_runtime_process_groups()
        cleaned_inactive_workspaces = self._cleanup_inactive_issue_workspaces()
        cleaned_artifact_roots = self._cleanup_stale_artifact_roots()
        cleaned_browser_sessions = self._cleanup_stale_browser_sessions()
        stale_runtime_profiles = self._detect_stale_runtime_profiles()
        expired_locks = self.store.cleanup_expired_healer_locks()
        removed_orphans = self._sweep_orphan_workspaces()
        return {
            "recovered_stale_active_issues": recovered_stale_active_issues,
            "interrupted_inactive_attempts": interrupted_inactive_attempts,
            "interrupted_superseded_attempts": interrupted_superseded_attempts,
            "reaped_orphan_subagents": reaped_orphan_subagents,
            "reaped_orphan_app_runtimes": reaped_orphan_app_runtimes,
            "cleaned_inactive_workspaces": cleaned_inactive_workspaces,
            "cleaned_artifact_roots": cleaned_artifact_roots,
            "cleaned_browser_sessions": cleaned_browser_sessions,
            "stale_runtime_profiles_detected": len(stale_runtime_profiles),
            "recovered_leases": recovered_leases,
            "expired_locks": expired_locks,
            "removed_orphans": removed_orphans,
        }

    def resource_audit(self) -> dict[str, object]:
        workspaces = self.workspace_manager.list_workspaces() if self.workspace_manager.worktrees_root.exists() else []
        issues = self.store.list_healer_issues(limit=5000)
        locks = self.store.list_healer_locks()
        artifact_refs = self._artifact_root_refs()
        runtime_refs = self._app_runtime_refs()
        browser_session_refs = self._browser_session_refs()
        snapshots = _list_process_snapshots()

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

        existing_artifact_roots = 0
        stale_artifact_roots = 0
        for ref in artifact_refs:
            artifact_path = Path(str(ref.get("path") or "")).expanduser()
            if artifact_path.exists():
                existing_artifact_roots += 1
            if self._artifact_root_is_stale(ref):
                stale_artifact_roots += 1

        existing_browser_sessions = 0
        stale_browser_sessions = 0
        for ref in browser_session_refs:
            session_path = Path(str(ref.get("path") or "")).expanduser()
            if session_path.exists():
                existing_browser_sessions += 1
            if self._browser_session_is_stale(ref):
                stale_browser_sessions += 1

        live_runtime_groups = 0
        orphan_runtime_candidates = 0
        active_issue_ids = self._active_issue_ids()
        for ref in runtime_refs:
            snapshot = _match_runtime_snapshot(ref=ref, snapshots=snapshots)
            if snapshot is not None:
                live_runtime_groups += 1
            if snapshot is not None and self._app_runtime_is_orphan(ref=ref, snapshot=snapshot, active_issue_ids=active_issue_ids):
                orphan_runtime_candidates += 1

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
            "artifacts": {
                "tracked_roots": len(artifact_refs),
                "existing_roots": existing_artifact_roots,
                "stale_roots": stale_artifact_roots,
            },
            "app_runtimes": {
                "tracked": len(runtime_refs),
                "live_process_groups": live_runtime_groups,
                "orphan_candidates": orphan_runtime_candidates,
            },
            "browser_sessions": {
                "tracked": len(browser_session_refs),
                "existing_roots": existing_browser_sessions,
                "stale_roots": stale_browser_sessions,
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

    def _recover_stale_active_issues(self) -> int:
        if not self.current_worker_id:
            return 0
        active_rows = self.store.list_healer_issue_workspace_refs(
            states=["claimed", "running", "verify_pending"],
            limit=2000,
        )
        recovered = 0
        for row in active_rows:
            issue_id = str(row.get("issue_id") or "").strip()
            lease_owner = str(row.get("lease_owner") or "").strip()
            if not issue_id or not lease_owner or lease_owner == self.current_worker_id:
                continue
            workspace_raw = str(row.get("workspace_path") or "").strip()
            workspace_reason_suffix = ""
            if workspace_raw:
                workspace_path = Path(workspace_raw).expanduser().absolute()
                workspace_missing = not workspace_path.exists()
                workspace_invalid = workspace_path.exists() and not self.workspace_manager.is_valid_workspace(workspace_path)
                if workspace_missing or workspace_invalid:
                    workspace_reason_suffix = " Missing workspace will be rebuilt on retry."
            updated = self.store.set_healer_issue_state(
                issue_id=issue_id,
                state="queued",
                workspace_path="",
                branch_name="",
                clear_lease=True,
                last_failure_class="interrupted",
                last_failure_reason=(
                    f"Recovered stale active issue from previous worker session '{lease_owner}'."
                    f"{workspace_reason_suffix}"
                ),
                expected_lease_owner=lease_owner,
            )
            if not updated:
                continue
            self.store.release_healer_locks_for_owner(issue_id=issue_id, lease_owner=lease_owner)
            recovered += 1
            logger.warning(
                "Recovered stale active issue #%s from previous worker session %s",
                issue_id,
                lease_owner,
            )
        return recovered

    def _reap_orphan_swarm_subagents(self) -> int:
        snapshots = _list_process_snapshots()
        if not snapshots:
            return 0
        reaped = 0
        reaped_groups: set[int] = set()
        for snapshot in snapshots:
            if snapshot.ppid != 1:
                continue
            if snapshot.elapsed_seconds < self.swarm_orphan_subagent_ttl_seconds:
                continue
            command = snapshot.command.lower()
            if "codex exec" not in command:
                continue
            if SWARM_PROCESS_MARKER.lower() not in command:
                continue
            target_group = snapshot.pgid if snapshot.pgid > 0 else snapshot.pid
            if target_group <= 0 or target_group in reaped_groups:
                continue
            if not _terminate_process_group(target_group):
                continue
            reaped += 1
            reaped_groups.add(target_group)
            logger.warning(
                "Reaped orphan swarm subagent process group pgid=%s pid=%s elapsed=%ss",
                target_group,
                snapshot.pid,
                snapshot.elapsed_seconds,
            )
        return reaped

    def _reap_orphan_app_runtime_process_groups(self) -> int:
        runtime_refs = self._app_runtime_refs()
        if not runtime_refs:
            return 0
        snapshots = _list_process_snapshots()
        if not snapshots:
            return 0
        active_issue_ids = self._active_issue_ids()
        reaped = 0
        reaped_groups: set[int] = set()
        for ref in runtime_refs:
            snapshot = _match_runtime_snapshot(ref=ref, snapshots=snapshots)
            if snapshot is None:
                continue
            if not self._app_runtime_is_orphan(ref=ref, snapshot=snapshot, active_issue_ids=active_issue_ids):
                continue
            target_group = snapshot.pgid if snapshot.pgid > 0 else snapshot.pid
            if target_group <= 0 or target_group in reaped_groups:
                continue
            if not _terminate_process_group(target_group):
                continue
            state_key = str(ref.get("state_key") or "")
            if state_key:
                self.store.set_state(state_key, "")
            reaped += 1
            reaped_groups.add(target_group)
            logger.warning(
                "Reaped orphan app runtime process group pgid=%s pid=%s issue=%s",
                target_group,
                snapshot.pid,
                str(ref.get("issue_id") or ""),
            )
        return reaped

    def _cleanup_stale_artifact_roots(self) -> int:
        artifact_refs = self._artifact_root_refs()
        if not artifact_refs:
            return 0
        active_issue_ids = self._active_issue_ids()
        cleaned = 0
        for ref in artifact_refs:
            issue_id = str(ref.get("issue_id") or "").strip()
            if issue_id and issue_id in active_issue_ids:
                continue
            if not self._artifact_root_is_stale(ref):
                continue
            artifact_path = Path(str(ref.get("path") or "")).expanduser()
            if not artifact_path.exists():
                continue
            try:
                if artifact_path.is_dir():
                    shutil.rmtree(artifact_path)
                else:
                    artifact_path.unlink()
            except Exception as exc:
                logger.warning("Failed to remove stale artifact root %s: %s", artifact_path, exc)
                continue
            state_key = str(ref.get("state_key") or "")
            if state_key:
                self.store.set_state(state_key, "")
            cleaned += 1
        return cleaned

    def _cleanup_stale_browser_sessions(self) -> int:
        browser_session_refs = self._browser_session_refs()
        if not browser_session_refs:
            return 0
        active_issue_ids = self._active_issue_ids()
        cleaned = 0
        for ref in browser_session_refs:
            issue_id = str(ref.get("issue_id") or "").strip()
            if issue_id and issue_id in active_issue_ids:
                continue
            if not self._browser_session_is_stale(ref):
                continue
            session_path = Path(str(ref.get("path") or "")).expanduser()
            if not session_path.exists():
                continue
            try:
                if session_path.is_dir():
                    shutil.rmtree(session_path)
                else:
                    session_path.unlink()
            except Exception as exc:
                logger.warning("Failed to remove stale browser session root %s: %s", session_path, exc)
                continue
            state_key = str(ref.get("state_key") or "")
            if state_key:
                self.store.set_state(state_key, "")
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
            str(Path(row.get("workspace_path") or "").expanduser().absolute())
            for row in active_rows
            if (row.get("workspace_path") or "").strip() and self._workspace_ref_should_be_preserved(row)
        }
        removed = 0
        for workspace in self.workspace_manager.list_workspaces():
            if str(workspace.expanduser().absolute()) in active_paths:
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

    def _active_issue_ids(self) -> set[str]:
        rows = self.store.list_healer_issues(
            states=["queued", *_ACTIVE_WORKSPACE_STATES],
            limit=5000,
        )
        active_issue_ids: set[str] = set()
        for row in rows:
            issue_id = str(row.get("issue_id") or "").strip()
            if not issue_id:
                continue
            state = str(row.get("state") or "").strip()
            if state in _ACTIVE_WORKSPACE_STATES:
                active_issue_ids.add(issue_id)
                continue
            if state == "queued" and self._workspace_ref_has_active_lease(row):
                active_issue_ids.add(issue_id)
        return active_issue_ids

    def _artifact_root_refs(self) -> list[dict[str, object]]:
        refs: list[dict[str, object]] = []
        for key, raw_value in self.store.list_states(prefix=_ARTIFACT_ROOT_REF_PREFIX, limit=5000).items():
            payload = _parse_json_state(raw_value)
            path = str(payload.get("path") or "").strip()
            if not path:
                continue
            payload["state_key"] = key
            refs.append(payload)
        return refs

    def _app_runtime_refs(self) -> list[dict[str, object]]:
        refs: list[dict[str, object]] = []
        for key, raw_value in self.store.list_states(prefix=_APP_RUNTIME_REF_PREFIX, limit=5000).items():
            payload = _parse_json_state(raw_value)
            pid = _coerce_int(payload.get("pid"))
            pgid = _coerce_int(payload.get("pgid"))
            if pid <= 0 and pgid <= 0:
                continue
            payload["state_key"] = key
            refs.append(payload)
        return refs

    def _browser_session_refs(self) -> list[dict[str, object]]:
        refs: list[dict[str, object]] = []
        for key, raw_value in self.store.list_states(prefix=_BROWSER_SESSION_REF_PREFIX, limit=5000).items():
            payload = _parse_json_state(raw_value)
            path = str(payload.get("path") or "").strip()
            if not path:
                continue
            payload["state_key"] = key
            refs.append(payload)
        return refs

    def _artifact_root_is_stale(self, ref: dict[str, object]) -> bool:
        retention_until = str(ref.get("retention_until") or "").strip()
        if retention_until:
            return _is_expired_timestamp(retention_until)
        artifact_path = Path(str(ref.get("path") or "")).expanduser()
        if not artifact_path.exists():
            return False
        try:
            modified_at = datetime.fromtimestamp(artifact_path.stat().st_mtime, tz=UTC)
        except OSError:
            return False
        cutoff = datetime.now(tz=UTC) - timedelta(days=self.artifact_retention_days)
        return modified_at <= cutoff

    def _browser_session_is_stale(self, ref: dict[str, object]) -> bool:
        retention_until = str(ref.get("retention_until") or "").strip()
        if retention_until:
            return _is_expired_timestamp(retention_until)
        browser_session_path = Path(str(ref.get("path") or "")).expanduser()
        if not browser_session_path.exists():
            return False
        try:
            modified_at = datetime.fromtimestamp(browser_session_path.stat().st_mtime, tz=UTC)
        except OSError:
            return False
        cutoff = datetime.now(tz=UTC) - timedelta(days=self.artifact_retention_days)
        return modified_at <= cutoff

    def _app_runtime_is_orphan(
        self,
        *,
        ref: dict[str, object],
        snapshot: "_ProcessSnapshot",
        active_issue_ids: set[str],
    ) -> bool:
        issue_id = str(ref.get("issue_id") or "").strip()
        if issue_id and issue_id in active_issue_ids:
            return False
        if snapshot.elapsed_seconds < self.app_runtime_orphan_ttl_seconds:
            return False
        normalized_command = snapshot.command.lower()
        return snapshot.ppid == 1 or "flow-healer app-runtime" in normalized_command

    def _detect_stale_runtime_profiles(self) -> list[str]:
        if not self.runtime_profiles:
            self.store.set_states(
                {
                    "healer_stale_runtime_profiles": "[]",
                    "healer_stale_runtime_profiles_detected": "0",
                }
            )
            return []
        cutoff = datetime.now(tz=UTC) - timedelta(days=self.app_runtime_stale_days)
        last_seen_states = self.store.list_states(prefix="healer_app_runtime_profile_last_seen_at:", limit=500)
        canary_states = self.store.list_states(prefix="healer_app_runtime_canary_last_success_at:", limit=500)
        stale_profiles: list[str] = []
        for profile_name, profile in sorted(self.runtime_profiles.items()):
            profile_path, profile_command = _runtime_profile_path_and_command(
                profile,
                repo_path=self.workspace_manager.repo_path,
            )
            if profile_path is None or not profile_command or not profile_path.exists():
                stale_profiles.append(profile_name)
                continue
            last_seen_at = _parse_state_timestamp(last_seen_states.get(f"healer_app_runtime_profile_last_seen_at:{profile_name}"))
            last_canary_at = _parse_state_timestamp(
                canary_states.get(f"healer_app_runtime_canary_last_success_at:{profile_name}")
            )
            last_activity = max(
                (item for item in (last_seen_at, last_canary_at) if item is not None),
                default=None,
            )
            if last_activity is None or last_activity <= cutoff:
                stale_profiles.append(profile_name)
        self.store.set_states(
            {
                "healer_stale_runtime_profiles": json.dumps(stale_profiles),
                "healer_stale_runtime_profiles_detected": str(len(stale_profiles)),
            }
        )
        return stale_profiles


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


def _parse_state_timestamp(raw: object) -> datetime | None:
    normalized = str(raw or "").strip()
    if not normalized:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _parse_json_state(raw: object) -> dict[str, object]:
    if not str(raw or "").strip():
        return {}
    try:
        payload = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _runtime_profile_path_and_command(profile: object, *, repo_path: Path) -> tuple[Path | None, tuple[str, ...]]:
    if isinstance(profile, AppRuntimeProfile):
        resolved_path = Path(profile.cwd).expanduser()
        if not resolved_path.is_absolute():
            resolved_path = (repo_path / resolved_path).resolve()
        return resolved_path, tuple(profile.command)
    if isinstance(profile, dict):
        raw_cwd = str(profile.get("cwd") or profile.get("working_directory") or "").strip()
        raw_command = profile.get("command") or profile.get("start_command") or ()
        if isinstance(raw_command, str):
            command = tuple(part for part in raw_command.split() if part)
        elif isinstance(raw_command, (list, tuple)):
            command = tuple(str(part).strip() for part in raw_command if str(part).strip())
        else:
            command = ()
        if not raw_cwd:
            return None, command
        resolved_path = Path(raw_cwd).expanduser()
        if not resolved_path.is_absolute():
            resolved_path = (repo_path / resolved_path).resolve()
        return resolved_path, command
    return None, ()


def _coerce_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _match_runtime_snapshot(*, ref: dict[str, object], snapshots: list["_ProcessSnapshot"]) -> "_ProcessSnapshot | None":
    pid = _coerce_int(ref.get("pid"))
    pgid = _coerce_int(ref.get("pgid"))
    for snapshot in snapshots:
        if pid > 0 and snapshot.pid == pid:
            return snapshot
        if pgid > 0 and snapshot.pgid == pgid:
            return snapshot
    return None


@dataclass(slots=True, frozen=True)
class _ProcessSnapshot:
    pid: int
    ppid: int
    pgid: int
    elapsed_seconds: int
    command: str


def _list_process_snapshots() -> list[_ProcessSnapshot]:
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,pgid=,etimes=,command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    snapshots: list[_ProcessSnapshot] = []
    for line in (proc.stdout or "").splitlines():
        parts = line.strip().split(maxsplit=4)
        if len(parts) != 5:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
            pgid = int(parts[2])
            elapsed_seconds = int(parts[3])
        except ValueError:
            continue
        snapshots.append(
            _ProcessSnapshot(
                pid=pid,
                ppid=ppid,
                pgid=pgid,
                elapsed_seconds=elapsed_seconds,
                command=parts[4],
            )
        )
    return snapshots


def _terminate_process_group(pgid: int) -> bool:
    if pgid <= 0:
        return False
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    time.sleep(0.1)
    if _process_group_exists(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
    return True


def _process_group_exists(pgid: int) -> bool:
    if pgid <= 0:
        return False
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
