from __future__ import annotations

import os
import subprocess
import threading


class CodexCliConnector:
    """Small standalone connector that shells out to `codex exec`."""

    def __init__(
        self,
        *,
        workspace: str,
        codex_command: str = "codex",
        timeout: float = 300.0,
        model: str = "",
    ) -> None:
        self.workspace = workspace
        self.codex_command = codex_command
        self.timeout = timeout
        self.model = model.strip()
        self._lock = threading.Lock()
        self._threads: set[str] = set()

    def ensure_started(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def get_or_create_thread(self, sender: str) -> str:
        with self._lock:
            self._threads.add(sender)
        return sender

    def reset_thread(self, sender: str) -> str:
        with self._lock:
            self._threads.discard(sender)
        return sender

    def run_turn(self, thread_id: str, prompt: str) -> str:
        cmd = [self.codex_command, "exec", "--skip-git-repo-check", "--yolo"]
        if self.model:
            cmd.extend(["-m", self.model])
        cmd.append(prompt)
        try:
            proc = subprocess.run(
                cmd,
                cwd=self.workspace,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=os.environ.copy(),
            )
        except FileNotFoundError:
            return f"Error: Codex CLI not found at '{self.codex_command}'."
        except subprocess.TimeoutExpired:
            return f"Error: Codex CLI timed out after {int(self.timeout)}s."
        if proc.returncode != 0:
            return (proc.stderr or proc.stdout or f"Error: codex exited {proc.returncode}.").strip()
        return (proc.stdout or "").strip()
