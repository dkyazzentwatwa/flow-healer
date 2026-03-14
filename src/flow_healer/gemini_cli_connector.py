from __future__ import annotations

import os
import signal
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


class GeminiCliConnector:
    """Standalone connector that shells out to `gemini -p`."""

    def __init__(
        self,
        *,
        workspace: str,
        gemini_command: str = "gemini",
        timeout: float = 600.0,
        model: str = "",
    ) -> None:
        self.workspace = workspace
        self.gemini_command = (gemini_command or "gemini").strip() or "gemini"
        self.timeout = timeout
        self.model = model.strip()
        self._lock = threading.Lock()
        self._threads: set[str] = set()
        self._active_pids: set[int] = set()
        self._resolved_command = ""
        self._available = False
        self._availability_reason = ""
        self._last_health_check_at = 0.0
        self._last_health_error = ""
        self._last_runtime_error_kind = ""
        self._last_runtime_stdout_tail = ""
        self._last_runtime_stderr_tail = ""
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
        if now - last_check_at < 60:
            return
        try:
            # Use --version as a health check
            proc = subprocess.run(
                [resolved, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
                env=self._connector_env(),
            )
        except Exception as exc:
            with self._lock:
                self._available = False
                self._availability_reason = f"gemini health check failed: {exc}"
                self._last_health_error = self._availability_reason
                self._last_health_check_at = now
                self._clear_runtime_error_details()
            return
        with self._lock:
            self._last_health_check_at = now
            if proc.returncode == 0:
                self._available = True
                self._availability_reason = ""
                self._last_health_error = ""
                self._clear_runtime_error_details()
            else:
                output = (proc.stderr or proc.stdout or f"gemini exited {proc.returncode}").strip()
                self._available = False
                self._availability_reason = output[:300]
                self._last_health_error = output[:300]
                self._clear_runtime_error_details()

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

    def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
        self.ensure_started()
        with self._lock:
            available = self._available
            resolved = self._resolved_command
            reason = self._availability_reason
        if not available or not resolved:
            return f"ConnectorUnavailable: {reason or 'Gemini CLI command is not available.'}"

        # Build the command: gemini -p "prompt" -y -m model
        cmd = [resolved, "--prompt", prompt, "--yolo"]
        if self.model:
            cmd.extend(["--model", self.model])
        
        effective_timeout = float(timeout_seconds) if timeout_seconds is not None else float(self.timeout)
        effective_timeout = max(30.0, effective_timeout)
        proc: subprocess.Popen[str] | None = None
        cwd_value: str | None = None
        try:
            candidate = Path(self.workspace).expanduser()
            if candidate.exists():
                cwd_value = str(candidate)
        except Exception:
            cwd_value = None

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd_value,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._connector_env(),
                start_new_session=True,
            )
            with self._lock:
                self._active_pids.add(proc.pid)
            stdout, stderr = proc.communicate(timeout=effective_timeout)
        except FileNotFoundError:
            with self._lock:
                self._available = False
                self._availability_reason = f"Gemini CLI not found at '{resolved}'."
                self._clear_runtime_error_details()
            return f"ConnectorUnavailable: Gemini CLI not found at '{resolved}'."
        except subprocess.TimeoutExpired:
            stdout = _normalize_process_output(getattr(proc, "stdout", None))
            stderr = _normalize_process_output(getattr(proc, "stderr", None))
            if proc is not None:
                _terminate_process_group(proc.pid)
            stdout_tail = _tail_text(stdout)
            stderr_tail = _tail_text(stderr)
            timeout_msg = "ConnectorRuntimeError: " + _format_runtime_error(
                stdout=stdout,
                stderr=stderr,
                timeout_seconds=int(effective_timeout),
            )
            with self._lock:
                self._last_health_error = timeout_msg[:500]
                self._set_runtime_error_details(
                    kind="timeout",
                    stdout_tail=stdout_tail,
                    stderr_tail=stderr_tail,
                )
            return timeout_msg
        finally:
            if proc is not None:
                with self._lock:
                    self._active_pids.discard(proc.pid)
                _terminate_process_group(proc.pid)
        
        if proc.returncode != 0:
            stdout_tail = _tail_text(stdout)
            stderr_tail = _tail_text(stderr)
            output = _format_runtime_error(
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode,
            )
            with self._lock:
                self._last_health_error = output[:300]
                self._set_runtime_error_details(
                    kind="nonzero_exit",
                    stdout_tail=stdout_tail,
                    stderr_tail=stderr_tail,
                )
            return f"ConnectorRuntimeError: {output}"
        
        with self._lock:
            self._clear_runtime_error_details()
        return (stdout or "").strip()

    def health_snapshot(self) -> dict[str, str | bool]:
        with self._lock:
            return {
                "configured_command": self.gemini_command,
                "resolved_command": self._resolved_command,
                "available": self._available,
                "availability_reason": self._availability_reason,
                "last_health_error": self._last_health_error,
                "last_runtime_error_kind": self._last_runtime_error_kind,
                "last_runtime_stdout_tail": self._last_runtime_stdout_tail,
                "last_runtime_stderr_tail": self._last_runtime_stderr_tail,
            }

    def _resolve_command(self) -> None:
        candidates: list[str] = []
        configured = self.gemini_command
        if os.path.isabs(configured):
            candidates.append(configured)
        else:
            candidates.extend(
                [
                    configured,
                    "/opt/homebrew/bin/gemini",
                    "/usr/local/bin/gemini",
                    "/usr/bin/gemini",
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
                    f"Unable to resolve Gemini command '{self.gemini_command}'. "
                    "Set service.gemini_cli_command to an absolute path."
                )

    def _connector_env(self) -> dict[str, str]:
        env = os.environ.copy()
        # Ensure homebrew and standard paths are present
        existing = env.get("PATH", "").strip()
        preferred = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        if existing:
            env["PATH"] = f"{preferred}:{existing}"
        else:
            env["PATH"] = preferred
        return env

    def _set_runtime_error_details(self, *, kind: str, stdout_tail: str, stderr_tail: str) -> None:
        self._last_runtime_error_kind = kind
        self._last_runtime_stdout_tail = stdout_tail[:500]
        self._last_runtime_stderr_tail = stderr_tail[:500]

    def _clear_runtime_error_details(self) -> None:
        self._last_runtime_error_kind = ""
        self._last_runtime_stdout_tail = ""
        self._last_runtime_stderr_tail = ""


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


def _normalize_process_output(stream: Any) -> str:
    if stream is None:
        return ""
    if hasattr(stream, "read"):
        try:
            data = stream.read()
        except Exception:
            return ""
    else:
        data = stream
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _format_runtime_error(
    *,
    stdout: str,
    stderr: str,
    exit_code: int | None = None,
    timeout_seconds: int | None = None,
) -> str:
    details: list[str] = []
    if timeout_seconds is not None:
        details.append(f"Gemini CLI timed out after {timeout_seconds}s.")
    elif exit_code is not None:
        details.append(f"Gemini CLI exited with code {exit_code}.")

    stderr_tail = _tail_text(stderr)
    stdout_tail = _tail_text(stdout)
    if stderr_tail:
        details.append(f"stderr tail: {stderr_tail}")
    if stdout_tail:
        details.append(f"stdout tail: {stdout_tail}")
    if len(details) == 1:
        details.append("No stdout/stderr output captured.")
    return " ".join(details).strip()


def _tail_text(text: str, *, limit: int = 500) -> str:
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[-limit:]
