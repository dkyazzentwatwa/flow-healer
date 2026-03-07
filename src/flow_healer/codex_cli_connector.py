from __future__ import annotations

import os
import signal
import shutil
import subprocess
import threading
import time


class CodexCliConnector:
    """Small standalone connector that shells out to `codex exec`."""

    def __init__(
        self,
        *,
        workspace: str,
        codex_command: str = "codex",
        timeout: float = 300.0,
        model: str = "",
        reasoning_effort: str = "",
    ) -> None:
        self.workspace = workspace
        self.codex_command = (codex_command or "codex").strip() or "codex"
        self.timeout = timeout
        self.model = model.strip()
        self.reasoning_effort = reasoning_effort.strip().lower()
        self._lock = threading.Lock()
        self._threads: set[str] = set()
        self._active_pids: set[int] = set()
        self._resolved_command = ""
        self._available = False
        self._availability_reason = ""
        self._last_health_check_at = 0.0
        self._last_health_error = ""
        self._resolve_command()

    def ensure_started(self) -> None:
        with self._lock:
            available = self._available
            resolved = self._resolved_command
            last_check_at = self._last_health_check_at

        if not available:
            self._resolve_command()
            with self._lock:
                available = self._available
                resolved = self._resolved_command
            if not available:
                return

        # Keep a lightweight liveness check with short caching.
        now = time.monotonic()
        if now - last_check_at < 30:
            return
        try:
            proc = subprocess.run(
                [resolved, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
                env=self._connector_env(),
            )
        except Exception as exc:
            with self._lock:
                self._available = False
                self._availability_reason = f"codex health check failed: {exc}"
                self._last_health_error = self._availability_reason
                self._last_health_check_at = now
            return
        with self._lock:
            self._last_health_check_at = now
            if proc.returncode == 0:
                self._available = True
                self._availability_reason = ""
                self._last_health_error = ""
            else:
                output = (proc.stderr or proc.stdout or f"codex exited {proc.returncode}").strip()
                self._available = False
                self._availability_reason = output[:300]
                self._last_health_error = output[:300]

    def shutdown(self) -> None:
        with self._lock:
            active_pids = list(self._active_pids)
            self._active_pids.clear()
            self._threads.clear()
        for pid in active_pids:
            _terminate_process_group(pid)

    def get_or_create_thread(self, sender: str) -> str:
        with self._lock:
            self._threads.add(sender)
        return sender

    def reset_thread(self, sender: str) -> str:
        with self._lock:
            self._threads.discard(sender)
        return sender

    def run_turn(self, thread_id: str, prompt: str) -> str:
        self.ensure_started()
        with self._lock:
            available = self._available
            resolved = self._resolved_command
            reason = self._availability_reason
        if not available or not resolved:
            return f"ConnectorUnavailable: {reason or 'Codex CLI command is not available.'}"

        cmd = [resolved, "exec", "--skip-git-repo-check", "--yolo"]
        if self.model:
            cmd.extend(["-m", self.model])
        if self.reasoning_effort:
            cmd.extend(["-c", f'model_reasoning_effort="{self.reasoning_effort}"'])
        cmd.append(prompt)
        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._connector_env(),
                start_new_session=True,
            )
            with self._lock:
                self._active_pids.add(proc.pid)
            stdout, stderr = proc.communicate(timeout=self.timeout)
        except FileNotFoundError:
            with self._lock:
                self._available = False
                self._availability_reason = f"Codex CLI not found at '{resolved}'."
            return f"ConnectorUnavailable: Codex CLI not found at '{resolved}'."
        except subprocess.TimeoutExpired:
            if proc is not None:
                _terminate_process_group(proc.pid)
            timeout_msg = f"ConnectorRuntimeError: Codex CLI timed out after {int(self.timeout)}s."
            with self._lock:
                self._last_health_error = timeout_msg
            return timeout_msg
        finally:
            if proc is not None:
                with self._lock:
                    self._active_pids.discard(proc.pid)
                _terminate_process_group(proc.pid)
        if proc.returncode != 0:
            output = (stderr or stdout or f"codex exited {proc.returncode}.").strip()
            with self._lock:
                self._last_health_error = output[:300]
            return f"ConnectorRuntimeError: {output}"
        return (stdout or "").strip()

    def health_snapshot(self) -> dict[str, str | bool]:
        with self._lock:
            return {
                "configured_command": self.codex_command,
                "resolved_command": self._resolved_command,
                "available": self._available,
                "availability_reason": self._availability_reason,
                "last_health_error": self._last_health_error,
            }

    def _resolve_command(self) -> None:
        candidates: list[str] = []
        configured = self.codex_command
        if os.path.isabs(configured):
            candidates.append(configured)
        else:
            candidates.extend(
                [
                    configured,
                    "/opt/homebrew/bin/codex",
                    "/usr/local/bin/codex",
                    "/usr/bin/codex",
                ]
            )

        resolved = ""
        for candidate in candidates:
            if os.path.isabs(candidate):
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    resolved = candidate
                    break
                continue
            maybe = shutil.which(candidate)
            if maybe:
                resolved = maybe
                break

        with self._lock:
            if resolved:
                self._resolved_command = resolved
                self._available = True
                self._availability_reason = ""
            else:
                self._resolved_command = ""
                self._available = False
                self._availability_reason = (
                    f"Unable to resolve Codex command '{self.codex_command}'. "
                    "Set service.connector_command to an absolute path."
                )

    def _connector_env(self) -> dict[str, str]:
        env = os.environ.copy()
        existing = env.get("PATH", "").strip()
        preferred = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        if existing:
            env["PATH"] = f"{preferred}:{existing}"
        else:
            env["PATH"] = preferred
        return env


def _terminate_process_group(pid: int) -> None:
    if pid <= 0:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            return
        except PermissionError:
            return
        time.sleep(0.1)
