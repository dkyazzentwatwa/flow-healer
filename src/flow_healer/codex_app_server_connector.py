from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from .protocols import ConnectorTurnResult


class CodexAppServerConnector:
    """Connector that talks to `codex app-server` over local stdio JSON-RPC."""

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
        self._lock = threading.RLock()
        self._pending_lock = threading.Lock()
        self._resolved_command = ""
        self._available = False
        self._availability_reason = ""
        self._last_health_error = ""
        self._last_runtime_error_kind = ""
        self._last_runtime_stdout_tail = ""
        self._last_runtime_stderr_tail = ""
        self._proc: subprocess.Popen[str] | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._notifications: queue.Queue[dict[str, Any]] = queue.Queue()
        self._next_request_id = 0
        self._threads_by_sender: dict[str, str] = {}
        self._server_workspace = ""
        self._stderr_tail: deque[str] = deque(maxlen=20)
        self._stdout_noise_tail: deque[str] = deque(maxlen=20)
        self._resolve_command()

    def ensure_started(self) -> None:
        desired_workspace = self._workspace_path()
        with self._lock:
            proc = self._proc
            proc_running = proc is not None and proc.poll() is None
            workspace_changed = bool(self._server_workspace) and desired_workspace != self._server_workspace
            if proc_running and not workspace_changed:
                self._available = True
                self._availability_reason = ""
                return
            self._restart_server_locked(desired_workspace)

    def shutdown(self) -> None:
        with self._lock:
            self._stop_server_locked()
            self._threads_by_sender.clear()

    def get_or_create_thread(self, sender: str) -> str:
        self.ensure_started()
        with self._lock:
            if not self._available or self._proc is None or self._proc.poll() is not None:
                return sender
            thread_id = self._threads_by_sender.get(sender, "").strip()
            if thread_id:
                return thread_id
            try:
                thread_id = self._start_thread_locked()
            except Exception as exc:
                self._available = False
                self._availability_reason = f"codex app-server thread/start failed: {exc}"
                self._last_health_error = self._availability_reason[:500]
                return sender
            self._threads_by_sender[sender] = thread_id
            return thread_id

    def reset_thread(self, sender: str) -> str:
        self.ensure_started()
        with self._lock:
            if not self._available or self._proc is None or self._proc.poll() is not None:
                self._threads_by_sender.pop(sender, None)
                return sender
            self._threads_by_sender.pop(sender, None)
            try:
                thread_id = self._start_thread_locked()
            except Exception as exc:
                self._available = False
                self._availability_reason = f"codex app-server thread/start failed: {exc}"
                self._last_health_error = self._availability_reason[:500]
                return sender
            self._threads_by_sender[sender] = thread_id
            return thread_id

    def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
        return self.run_turn_detailed(thread_id, prompt, timeout_seconds=timeout_seconds).output_text

    def run_turn_detailed(
        self,
        thread_id: str,
        prompt: str,
        *,
        timeout_seconds: int | None = None,
    ) -> ConnectorTurnResult:
        self.ensure_started()
        effective_timeout = float(timeout_seconds) if timeout_seconds is not None else float(self.timeout)
        effective_timeout = max(30.0, effective_timeout)
        with self._lock:
            if not self._available or not self._resolved_command or self._proc is None or self._proc.poll() is not None:
                reason = self._availability_reason or "Codex app-server is not available."
                return ConnectorTurnResult(
                    output_text=f"ConnectorUnavailable: {reason}",
                    used_workspace_edit_mode=True,
                )
            self._drain_notifications_locked()
            try:
                response = self._rpc_request_locked(
                    "turn/start",
                    self._turn_start_params(thread_id=thread_id, prompt=prompt),
                    timeout=effective_timeout,
                )
                turn_id = str(((response.get("turn") or {}).get("id")) or "").strip()
                if not turn_id:
                    raise RuntimeError("Codex app-server did not return a turn id.")
                output = self._await_turn_completion_locked(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    timeout=effective_timeout,
                )
            except TimeoutError:
                timeout_msg = f"Codex app-server timed out after {int(effective_timeout)}s."
                self._last_health_error = timeout_msg
                self._set_runtime_error_details(
                    kind="timeout",
                    stdout_tail=" ".join(self._stdout_noise_tail).strip(),
                    stderr_tail=" ".join(self._stderr_tail).strip(),
                )
                self._stop_server_locked()
                self._available = False
                self._availability_reason = "Codex app-server timed out and was restarted."
                return ConnectorTurnResult(
                    output_text=f"ConnectorRuntimeError: {timeout_msg}",
                    used_workspace_edit_mode=True,
                )
            except Exception as exc:
                message = str(exc).strip() or "Codex app-server turn failed."
                self._last_health_error = message[:500]
                self._set_runtime_error_details(
                    kind="nonzero_exit",
                    stdout_tail=" ".join(self._stdout_noise_tail).strip(),
                    stderr_tail=" ".join(self._stderr_tail).strip(),
                )
                self._stop_server_locked()
                self._available = False
                self._availability_reason = "Codex app-server failed and was restarted."
                return ConnectorTurnResult(
                    output_text=f"ConnectorRuntimeError: {message}",
                    used_workspace_edit_mode=True,
                )
            self._clear_runtime_error_details()
            return output

    def health_snapshot(self) -> dict[str, str | bool]:
        with self._lock:
            return {
                "backend": "app_server",
                "configured_command": self.codex_command,
                "resolved_command": self._resolved_command,
                "available": self._available,
                "availability_reason": self._availability_reason,
                "last_health_error": self._last_health_error,
                "last_runtime_error_kind": self._last_runtime_error_kind,
                "last_runtime_stdout_tail": self._last_runtime_stdout_tail,
                "last_runtime_stderr_tail": self._last_runtime_stderr_tail,
            }

    def _restart_server_locked(self, desired_workspace: str) -> None:
        self._stop_server_locked()
        resolved_command = self._resolved_command
        if not resolved_command:
            self._available = False
            self._availability_reason = (
                f"Unable to resolve Codex command '{self.codex_command}'. "
                "Set service.connector_command to an absolute path."
            )
            self._last_health_error = self._availability_reason
            return
        try:
            proc = subprocess.Popen(
                [resolved_command, "app-server", "--listen", "stdio://"],
                cwd=desired_workspace or None,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._connector_env(),
                start_new_session=True,
                bufsize=1,
            )
        except FileNotFoundError:
            self._available = False
            self._availability_reason = f"Codex app-server not found at '{resolved_command}'."
            self._last_health_error = self._availability_reason
            return
        except Exception as exc:
            self._available = False
            self._availability_reason = f"codex app-server failed to start: {exc}"
            self._last_health_error = self._availability_reason
            return

        self._proc = proc
        self._threads_by_sender.clear()
        self._server_workspace = desired_workspace
        self._stderr_tail.clear()
        self._stdout_noise_tail.clear()
        self._stdout_thread = threading.Thread(target=self._stdout_reader, daemon=True, name="codex-app-server-stdout")
        self._stderr_thread = threading.Thread(target=self._stderr_reader, daemon=True, name="codex-app-server-stderr")
        self._stdout_thread.start()
        self._stderr_thread.start()
        try:
            self._rpc_request_locked(
                "initialize",
                {
                    "clientInfo": {"name": "flow-healer", "version": "0.1"},
                    "capabilities": {"experimentalApi": False},
                },
                timeout=15.0,
            )
        except Exception as exc:
            self._last_health_error = str(exc)[:500]
            self._available = False
            self._availability_reason = f"codex app-server initialize failed: {exc}"
            self._stop_server_locked()
            return
        self._available = True
        self._availability_reason = ""
        self._last_health_error = ""
        self._clear_runtime_error_details()

    def _start_thread_locked(self) -> str:
        response = self._rpc_request_locked(
            "thread/start",
            {
                "model": self.model or None,
                "cwd": self._server_workspace or None,
                "approvalPolicy": "never",
                "sandbox": "workspace-write",
                "serviceName": "flow-healer",
                "ephemeral": True,
                "experimentalRawEvents": False,
                "persistExtendedHistory": False,
            },
            timeout=15.0,
        )
        thread = response.get("thread") or {}
        thread_id = str(thread.get("id") or "").strip()
        if not thread_id:
            raise RuntimeError("Codex app-server did not return a thread id.")
        return thread_id

    def _turn_start_params(self, *, thread_id: str, prompt: str) -> dict[str, Any]:
        params: dict[str, Any] = {
            "threadId": thread_id,
            "input": [{"type": "text", "text": prompt, "text_elements": []}],
            "cwd": self._server_workspace or None,
        }
        if self.model:
            params["model"] = self.model
        if self.reasoning_effort:
            params["effort"] = self.reasoning_effort
        return params

    def _await_turn_completion_locked(
        self,
        *,
        thread_id: str,
        turn_id: str,
        timeout: float,
    ) -> ConnectorTurnResult:
        deadline = time.monotonic() + timeout
        delta_by_item: dict[str, list[str]] = {}
        text_by_item: dict[str, str] = {}
        phase_by_item: dict[str, str] = {}
        item_order: list[str] = []
        commentary_parts: list[str] = []
        raw_event_kinds: set[str] = set()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            try:
                message = self._notifications.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError() from exc
            if message.get("__eof__"):
                raise RuntimeError("Codex app-server exited unexpectedly.")
            method = str(message.get("method") or "").strip()
            if method:
                raw_event_kinds.add(method)
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            if method == "item/agentMessage/delta":
                if params.get("threadId") != thread_id or params.get("turnId") != turn_id:
                    continue
                item_id = str(params.get("itemId") or "").strip()
                if not item_id:
                    continue
                if item_id not in delta_by_item:
                    delta_by_item[item_id] = []
                    item_order.append(item_id)
                delta_by_item[item_id].append(str(params.get("delta") or ""))
                continue
            if method == "item/completed":
                if params.get("threadId") != thread_id or params.get("turnId") != turn_id:
                    continue
                item = params.get("item") if isinstance(params.get("item"), dict) else {}
                if item.get("type") != "agentMessage":
                    continue
                item_id = str(item.get("id") or "").strip()
                if not item_id:
                    continue
                if item_id not in item_order:
                    item_order.append(item_id)
                text_by_item[item_id] = str(item.get("text") or "")
                phase = str(item.get("phase") or "").strip()
                if phase:
                    phase_by_item[item_id] = phase
                if phase == "commentary":
                    commentary_text = str(item.get("text") or "").strip()
                    if commentary_text:
                        commentary_parts.append(commentary_text)
                continue
            if method == "turn/completed":
                if params.get("threadId") != thread_id:
                    continue
                turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
                if str(turn.get("id") or "").strip() != turn_id:
                    continue
                output_text, final_answer_present = _render_agent_output(
                    item_order=item_order,
                    text_by_item=text_by_item,
                    delta_by_item=delta_by_item,
                    phase_by_item=phase_by_item,
                )
                status = str(turn.get("status") or "").strip()
                if status == "completed":
                    return ConnectorTurnResult(
                        output_text=output_text.strip(),
                        final_answer_present=final_answer_present,
                        commentary_tail=_tail_text("\n".join(commentary_parts)),
                        used_workspace_edit_mode=True,
                        raw_event_kinds=tuple(sorted(raw_event_kinds)),
                    )
                error = turn.get("error") if isinstance(turn.get("error"), dict) else {}
                message_text = str(error.get("message") or f"Codex app-server turn ended with status '{status}'.")
                message_text = message_text.strip()
                if output_text:
                    message_text = f"{message_text} stdout tail: {_tail_text(output_text)}"
                raise RuntimeError(message_text)
            if method == "error":
                message_text = str(params.get("message") or "Codex app-server reported an error.").strip()
                raise RuntimeError(message_text)

    def _rpc_request_locked(self, method: str, params: Any, *, timeout: float) -> dict[str, Any]:
        if self._proc is None or self._proc.stdin is None or self._proc.poll() is not None:
            raise RuntimeError("Codex app-server is not running.")
        self._next_request_id += 1
        request_id = self._next_request_id
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = response_queue
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
            self._proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
            self._proc.stdin.flush()
            try:
                message = response_queue.get(timeout=timeout)
            except queue.Empty as exc:
                raise TimeoutError(f"Codex app-server timed out waiting for {method}.") from exc
            if message.get("__eof__"):
                raise RuntimeError("Codex app-server exited unexpectedly.")
            error = message.get("error") if isinstance(message.get("error"), dict) else None
            if error is not None:
                raise RuntimeError(_format_rpc_error(method=method, error=error))
            result = message.get("result")
            return result if isinstance(result, dict) else {}
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

    def _stop_server_locked(self) -> None:
        proc = self._proc
        self._proc = None
        self._server_workspace = ""
        self._threads_by_sender.clear()
        self._notify_eof_locked()
        if proc is not None:
            _terminate_process_group(proc.pid)

    def _notify_eof_locked(self) -> None:
        with self._pending_lock:
            pending_queues = list(self._pending.values())
            self._pending.clear()
        for pending in pending_queues:
            pending.put({"__eof__": True})
        self._notifications.put({"__eof__": True})

    def _stdout_reader(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for raw_line in iter(proc.stdout.readline, ""):
            line = raw_line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                with self._lock:
                    self._stdout_noise_tail.append(line)
                continue
            if not isinstance(message, dict):
                continue
            message_id = message.get("id")
            if isinstance(message_id, int):
                with self._pending_lock:
                    pending = self._pending.get(message_id)
                if pending is not None:
                    pending.put(message)
                    continue
            if "method" in message:
                self._notifications.put(message)
        with self._lock:
            self._notify_eof_locked()

    def _stderr_reader(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for raw_line in iter(proc.stderr.readline, ""):
            line = raw_line.strip()
            if not line:
                continue
            with self._lock:
                self._stderr_tail.append(line)

    def _workspace_path(self) -> str:
        try:
            candidate = Path(self.workspace).expanduser()
        except Exception:
            return ""
        if not candidate.exists():
            return ""
        return str(candidate)

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
                self._last_health_error = self._availability_reason

    def _connector_env(self) -> dict[str, str]:
        env = os.environ.copy()
        existing = env.get("PATH", "").strip()
        preferred = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        if existing:
            env["PATH"] = f"{preferred}:{existing}"
        else:
            env["PATH"] = preferred
        return env

    def _set_runtime_error_details(self, *, kind: str, stdout_tail: str, stderr_tail: str) -> None:
        self._last_runtime_error_kind = kind
        self._last_runtime_stdout_tail = _tail_text(stdout_tail)
        self._last_runtime_stderr_tail = _tail_text(stderr_tail)

    def _clear_runtime_error_details(self) -> None:
        self._last_runtime_error_kind = ""
        self._last_runtime_stdout_tail = ""
        self._last_runtime_stderr_tail = ""

    def _drain_notifications_locked(self) -> None:
        while True:
            try:
                self._notifications.get_nowait()
            except queue.Empty:
                return


def _render_agent_output(
    *,
    item_order: list[str],
    text_by_item: dict[str, str],
    delta_by_item: dict[str, list[str]],
    phase_by_item: dict[str, str],
) -> tuple[str, bool]:
    if not item_order:
        return "", False
    final_ids = [item_id for item_id in item_order if phase_by_item.get(item_id) == "final_answer"]
    candidate_ids = final_ids or [item_order[-1]]
    rendered: list[str] = []
    for item_id in candidate_ids:
        text = text_by_item.get(item_id)
        if text is None:
            text = "".join(delta_by_item.get(item_id) or [])
        text = (text or "").strip()
        if text:
            rendered.append(text)
    return "\n\n".join(rendered).strip(), bool(final_ids)


def _format_rpc_error(*, method: str, error: dict[str, Any]) -> str:
    message = str(error.get("message") or f"Codex app-server request failed for {method}.").strip()
    data = error.get("data")
    if data not in (None, ""):
        message = f"{message} data={data}"
    return message


def _tail_text(text: str, *, limit: int = 500) -> str:
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[-limit:]


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
