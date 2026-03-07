import signal
import subprocess

from flow_healer.codex_cli_connector import CodexCliConnector


class _FakeProcess:
    def __init__(self, *, pid: int = 4321, returncode: int = 0, stdout: str = "ok", stderr: str = "") -> None:
        self.pid = pid
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        return self._stdout, self._stderr


def test_run_turn_cleans_process_group_after_success(monkeypatch, tmp_path) -> None:
    connector = CodexCliConnector(workspace=str(tmp_path))
    connector._available = True
    connector._resolved_command = "codex"
    connector.ensure_started = lambda: None  # type: ignore[method-assign]
    proc = _FakeProcess()
    killed: list[tuple[int, signal.Signals]] = []

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: proc)
    monkeypatch.setattr("flow_healer.codex_cli_connector.os.killpg", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr("flow_healer.codex_cli_connector.time.sleep", lambda _seconds: None)

    output = connector.run_turn("thread-1", "fix it")

    assert output == "ok"
    assert killed == [(4321, signal.SIGTERM), (4321, signal.SIGKILL)]


def test_run_turn_passes_model_and_reasoning_effort(monkeypatch, tmp_path) -> None:
    connector = CodexCliConnector(
        workspace=str(tmp_path),
        model="gpt-5.4",
        reasoning_effort="medium",
    )
    connector._available = True
    connector._resolved_command = "codex"
    connector.ensure_started = lambda: None  # type: ignore[method-assign]
    proc = _FakeProcess()
    seen_cmd: list[str] = []

    def fake_popen(cmd, *args, **kwargs):
        seen_cmd.extend(cmd)
        return proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("flow_healer.codex_cli_connector.os.killpg", lambda pid, sig: None)
    monkeypatch.setattr("flow_healer.codex_cli_connector.time.sleep", lambda _seconds: None)

    connector.run_turn("thread-1", "fix it")

    assert seen_cmd[1:7] == [
        "exec",
        "--skip-git-repo-check",
        "--yolo",
        "-m",
        "gpt-5.4",
        "-c",
    ]
    assert seen_cmd[0].endswith("codex")
    assert 'model_reasoning_effort="medium"' in seen_cmd


def test_shutdown_terminates_active_process_groups(monkeypatch, tmp_path) -> None:
    connector = CodexCliConnector(workspace=str(tmp_path))
    killed: list[tuple[int, signal.Signals]] = []

    monkeypatch.setattr("flow_healer.codex_cli_connector.os.killpg", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr("flow_healer.codex_cli_connector.time.sleep", lambda _seconds: None)

    connector._active_pids.update({100, 200})
    connector.shutdown()

    assert connector._active_pids == set()
    assert sorted(killed) == sorted(
        [
        (100, signal.SIGTERM),
        (100, signal.SIGKILL),
        (200, signal.SIGTERM),
        (200, signal.SIGKILL),
        ]
    )


def test_run_turn_reports_unavailable_connector(tmp_path) -> None:
    connector = CodexCliConnector(workspace=str(tmp_path), codex_command="/definitely/missing/codex")

    output = connector.run_turn("thread-1", "fix it")

    assert output.startswith("ConnectorUnavailable:")


def test_health_snapshot_reports_resolved_command(tmp_path) -> None:
    connector = CodexCliConnector(workspace=str(tmp_path), codex_command="codex")
    snapshot = connector.health_snapshot()

    assert "configured_command" in snapshot
    assert "resolved_command" in snapshot
    assert "available" in snapshot
