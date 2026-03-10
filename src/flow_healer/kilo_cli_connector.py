from __future__ import annotations

import shutil
import subprocess
import threading
import time


class KiloCliConnector:
    """Stateless connector that shells out to `kilo run --auto` for each turn."""

    def __init__(
        self,
        *,
        workspace: str,
        kilo_cli_command: str = "kilo",
        timeout: float = 300.0,
        model: str = "",
    ) -> None:
        self.workspace = workspace
        self.kilo_cli_command = (kilo_cli_command or "kilo").strip() or "kilo"
        self.timeout = timeout
        self.model = (model or "").strip()
        self._lock = threading.Lock()
        self._threads: set[str] = set()
        self._resolved_command = ""
        self._available = False
        self._availability_reason = ""
        self._last_health_error = ""
        self._last_health_check_at = 0.0
        self._resolve_command()

    def ensure_started(self) -> None:
        now = time.monotonic()
        with self._lock:
            if self._available and now - self._last_health_check_at < 30:
                return
        self._resolve_command()
        with self._lock:
            resolved = self._resolved_command
        if not resolved:
            return
        try:
            proc = subprocess.run(
                [resolved, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception as exc:
            with self._lock:
                self._available = False
                self._availability_reason = f"kilo health check failed: {exc}"
                self._last_health_error = self._availability_reason[:500]
                self._last_health_check_at = now
            return
        with self._lock:
            self._last_health_check_at = now
            if proc.returncode == 0:
                self._available = True
                self._availability_reason = ""
                self._last_health_error = ""
            else:
                output = (proc.stderr or proc.stdout or f"kilo exited {proc.returncode}").strip()
                self._available = False
                self._availability_reason = output[:300]
                self._last_health_error = output[:300]

    def shutdown(self) -> None:
        with self._lock:
            self._threads.clear()

    def get_or_create_thread(self, sender: str) -> str:
        with self._lock:
            self._threads.add(sender)
        return sender

    def reset_thread(self, sender: str) -> str:
        with self._lock:
            self._threads.discard(sender)
        return sender

    def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
        del thread_id
        self.ensure_started()
        with self._lock:
            available = self._available
            resolved = self._resolved_command
            reason = self._availability_reason
        if not available or not resolved:
            return f"ConnectorUnavailable: {reason or 'Kilo CLI command is not available.'}"

        cmd = [resolved, "run", "--auto"]
        if self.model:
            cmd.extend(["--model", self.model])
        effective_timeout = float(timeout_seconds) if timeout_seconds is not None else float(self.timeout)
        effective_timeout = max(30.0, effective_timeout)
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                check=False,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                cwd=self.workspace or None,
            )
        except FileNotFoundError:
            with self._lock:
                self._available = False
                self._availability_reason = f"Kilo CLI not found at '{resolved}'."
                self._last_health_error = self._availability_reason[:500]
            return f"ConnectorUnavailable: Kilo CLI not found at '{resolved}'."
        except subprocess.TimeoutExpired:
            return f"ConnectorRuntimeError: Kilo CLI timed out after {int(effective_timeout)}s."
        except Exception as exc:
            return f"ConnectorRuntimeError: Kilo CLI execution failed: {exc}"

        if proc.returncode != 0:
            output = (proc.stderr or proc.stdout or f"Kilo CLI exited with code {proc.returncode}").strip()
            with self._lock:
                self._last_health_error = output[:500]
            return f"ConnectorRuntimeError: {output[:800]}"
        return (proc.stdout or "").strip()

    def health_snapshot(self) -> dict[str, str | bool]:
        with self._lock:
            return {
                "available": self._available,
                "configured_command": self.kilo_cli_command,
                "resolved_command": self._resolved_command,
                "availability_reason": self._availability_reason,
                "last_health_error": self._last_health_error,
            }

    def _resolve_command(self) -> None:
        resolved = ""
        configured = self.kilo_cli_command
        if "/" in configured:
            maybe = configured if shutil.which(configured) else ""
            resolved = maybe or ""
        else:
            resolved = shutil.which(configured) or ""
        with self._lock:
            if resolved:
                self._resolved_command = resolved
                self._available = True
                self._availability_reason = ""
            else:
                self._resolved_command = ""
                self._available = False
                self._availability_reason = (
                    f"Unable to resolve Kilo command '{self.kilo_cli_command}'. "
                    "Set service.kilo_cli_command to an absolute path."
                )
