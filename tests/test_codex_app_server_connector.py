from __future__ import annotations

import json
import signal
import subprocess
from queue import Queue

from flow_healer.codex_app_server_connector import CodexAppServerConnector


class _QueueStream:
    def __init__(self) -> None:
        self._queue: Queue[str | None] = Queue()

    def feed(self, line: str | None) -> None:
        self._queue.put(line)

    def readline(self) -> str:
        item = self._queue.get()
        if item is None:
            return ""
        return item


class _FakeStdin:
    def __init__(self, on_message) -> None:
        self._buffer = ""
        self._on_message = on_message

    def write(self, data: str) -> int:
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if line:
                self._on_message(json.loads(line))
        return len(data)

    def flush(self) -> None:
        return None


class _FakeAppServerProcess:
    def __init__(self, *, pid: int, handler) -> None:
        self.pid = pid
        self.returncode: int | None = None
        self.stdout = _QueueStream()
        self.stderr = _QueueStream()
        self.requests: list[dict[str, object]] = []
        self._handler = handler
        self.stdin = _FakeStdin(self._handle_request)

    def _handle_request(self, request: dict[str, object]) -> None:
        self.requests.append(request)
        self._handler(self, request)

    def emit(self, message: dict[str, object]) -> None:
        self.stdout.feed(json.dumps(message) + "\n")

    def close(self, returncode: int = 0) -> None:
        if self.returncode is not None:
            return
        self.returncode = returncode
        self.stdout.feed(None)
        self.stderr.feed(None)

    def poll(self) -> int | None:
        return self.returncode


def _install_fake_processes(monkeypatch, processes: list[_FakeAppServerProcess]) -> list[tuple[int, signal.Signals]]:
    registry = {proc.pid: proc for proc in processes}
    popen_calls: list[_FakeAppServerProcess] = []
    killed: list[tuple[int, signal.Signals]] = []

    def fake_popen(*args, **kwargs):
        proc = processes[len(popen_calls)]
        popen_calls.append(proc)
        return proc

    def fake_killpg(pid: int, sig: signal.Signals) -> None:
        killed.append((pid, sig))
        proc = registry.get(pid)
        if proc is not None and sig == signal.SIGTERM:
            proc.close(-sig.value)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("flow_healer.codex_app_server_connector.os.killpg", fake_killpg)
    monkeypatch.setattr("flow_healer.codex_app_server_connector.time.sleep", lambda _seconds: None)
    return killed


def _mock_codex_available(monkeypatch) -> None:
    monkeypatch.setattr(
        "flow_healer.codex_app_server_connector.shutil.which",
        lambda command: "/usr/local/bin/codex" if command == "codex" else None,
    )


def test_get_or_create_thread_reuses_existing_backend_thread(monkeypatch, tmp_path) -> None:
    _mock_codex_available(monkeypatch)

    def handler(proc: _FakeAppServerProcess, request: dict[str, object]) -> None:
        request_id = request["id"]
        method = request["method"]
        if method == "initialize":
            proc.emit({"jsonrpc": "2.0", "id": request_id, "result": {"userAgent": "test"}})
        elif method == "thread/start":
            thread_index = sum(1 for item in proc.requests if item["method"] == "thread/start")
            proc.emit({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": f"thread-{thread_index}"}}})

    process = _FakeAppServerProcess(pid=101, handler=handler)
    _install_fake_processes(monkeypatch, [process])
    connector = CodexAppServerConnector(workspace=str(tmp_path))

    first = connector.get_or_create_thread("healer:1")
    second = connector.get_or_create_thread("healer:1")

    assert first == "thread-1"
    assert second == "thread-1"
    assert [request["method"] for request in process.requests].count("thread/start") == 1
    connector.shutdown()


def test_reset_thread_returns_fresh_backend_thread(monkeypatch, tmp_path) -> None:
    _mock_codex_available(monkeypatch)

    def handler(proc: _FakeAppServerProcess, request: dict[str, object]) -> None:
        request_id = request["id"]
        method = request["method"]
        if method == "initialize":
            proc.emit({"jsonrpc": "2.0", "id": request_id, "result": {"userAgent": "test"}})
        elif method == "thread/start":
            thread_index = sum(1 for item in proc.requests if item["method"] == "thread/start")
            proc.emit({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": f"thread-{thread_index}"}}})

    process = _FakeAppServerProcess(pid=102, handler=handler)
    _install_fake_processes(monkeypatch, [process])
    connector = CodexAppServerConnector(workspace=str(tmp_path))

    original = connector.get_or_create_thread("healer:2")
    refreshed = connector.reset_thread("healer:2")

    assert original == "thread-1"
    assert refreshed == "thread-2"
    connector.shutdown()


def test_run_turn_returns_final_answer_item(monkeypatch, tmp_path) -> None:
    _mock_codex_available(monkeypatch)

    def handler(proc: _FakeAppServerProcess, request: dict[str, object]) -> None:
        request_id = request["id"]
        method = request["method"]
        if method == "initialize":
            proc.emit({"jsonrpc": "2.0", "id": request_id, "result": {"userAgent": "test"}})
            return
        if method == "thread/start":
            proc.emit({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": "thread-1"}}})
            return
        if method == "turn/start":
            turn_id = "turn-1"
            proc.emit({"jsonrpc": "2.0", "id": request_id, "result": {"turn": {"id": turn_id}}})
            proc.emit(
                {
                    "jsonrpc": "2.0",
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": turn_id,
                        "item": {
                            "type": "agentMessage",
                            "id": "item-commentary",
                            "text": "Looking around the repo now.",
                            "phase": "commentary",
                        },
                    },
                }
            )
            proc.emit(
                {
                    "jsonrpc": "2.0",
                    "method": "item/agentMessage/delta",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": turn_id,
                        "itemId": "item-final",
                        "delta": "```diff\n+patched\n```",
                    },
                }
            )
            proc.emit(
                {
                    "jsonrpc": "2.0",
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": turn_id,
                        "item": {
                            "type": "agentMessage",
                            "id": "item-final",
                            "text": "```diff\n+patched\n```",
                            "phase": "final_answer",
                        },
                    },
                }
            )
            proc.emit(
                {
                    "jsonrpc": "2.0",
                    "method": "turn/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turn": {"id": turn_id, "status": "completed", "error": None},
                    },
                }
            )

    process = _FakeAppServerProcess(pid=103, handler=handler)
    _install_fake_processes(monkeypatch, [process])
    connector = CodexAppServerConnector(workspace=str(tmp_path))
    thread_id = connector.get_or_create_thread("healer:3")

    output = connector.run_turn(thread_id, "fix it")

    assert output == "```diff\n+patched\n```"
    connector.shutdown()


def test_run_turn_detailed_reports_commentary_and_final_answer(monkeypatch, tmp_path) -> None:
    _mock_codex_available(monkeypatch)

    def handler(proc: _FakeAppServerProcess, request: dict[str, object]) -> None:
        request_id = request["id"]
        method = request["method"]
        if method == "initialize":
            proc.emit({"jsonrpc": "2.0", "id": request_id, "result": {"userAgent": "test"}})
            return
        if method == "thread/start":
            proc.emit({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": "thread-1"}}})
            return
        if method == "turn/start":
            turn_id = "turn-2"
            proc.emit({"jsonrpc": "2.0", "id": request_id, "result": {"turn": {"id": turn_id}}})
            proc.emit(
                {
                    "jsonrpc": "2.0",
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": turn_id,
                        "item": {
                            "type": "agentMessage",
                            "id": "item-commentary",
                            "text": "I inspected the target file and found the likely fix path.",
                            "phase": "commentary",
                        },
                    },
                }
            )
            proc.emit(
                {
                    "jsonrpc": "2.0",
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": turn_id,
                        "item": {
                            "type": "agentMessage",
                            "id": "item-final",
                            "text": "Updated the file in place and ran tests.",
                            "phase": "final_answer",
                        },
                    },
                }
            )
            proc.emit(
                {
                    "jsonrpc": "2.0",
                    "method": "turn/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turn": {"id": turn_id, "status": "completed", "error": None},
                    },
                }
            )

    process = _FakeAppServerProcess(pid=104, handler=handler)
    _install_fake_processes(monkeypatch, [process])
    connector = CodexAppServerConnector(workspace=str(tmp_path))
    thread_id = connector.get_or_create_thread("healer:4")

    result = connector.run_turn_detailed(thread_id, "fix it")

    assert result.output_text == "Updated the file in place and ran tests."
    assert result.final_answer_present is True
    assert "likely fix path" in result.commentary_tail
    assert "item/completed" in result.raw_event_kinds
    connector.shutdown()


def test_workspace_change_restarts_app_server(monkeypatch, tmp_path) -> None:
    _mock_codex_available(monkeypatch)

    workspace_a = tmp_path / "repo-a"
    workspace_b = tmp_path / "repo-b"
    workspace_a.mkdir()
    workspace_b.mkdir()

    def handler(proc: _FakeAppServerProcess, request: dict[str, object]) -> None:
        if request["method"] == "initialize":
            proc.emit({"jsonrpc": "2.0", "id": request["id"], "result": {"userAgent": "test"}})

    process_a = _FakeAppServerProcess(pid=201, handler=handler)
    process_b = _FakeAppServerProcess(pid=202, handler=handler)
    killed = _install_fake_processes(monkeypatch, [process_a, process_b])
    connector = CodexAppServerConnector(workspace=str(workspace_a))

    connector.ensure_started()
    connector.workspace = str(workspace_b)
    connector.ensure_started()

    assert (201, signal.SIGTERM) in killed
    assert connector.health_snapshot()["available"] is True
    connector.shutdown()
