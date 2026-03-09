from __future__ import annotations

import subprocess
from pathlib import Path

from flow_healer.docker_runtime import (
    docker_idle_shutdown_seconds,
    ensure_docker_runtime_running,
    maybe_shutdown_idle_docker_runtime,
    record_docker_activity,
    selected_docker_runtime,
)


def test_selected_docker_runtime_prefers_colima_when_available(monkeypatch) -> None:
    monkeypatch.delenv("FLOW_HEALER_DOCKER_RUNTIME", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "/opt/homebrew/bin/colima" if name == "colima" else None)
    monkeypatch.setattr("flow_healer.docker_runtime._app_installed", lambda name: False)

    assert selected_docker_runtime() == "colima"


def test_ensure_docker_runtime_running_starts_colima_when_docker_unavailable(monkeypatch) -> None:
    calls: list[list[str]] = []
    states = iter([False, True])
    activity_file = Path("/tmp/test-docker-runtime-activity.txt")
    monkeypatch.setenv("FLOW_HEALER_DOCKER_RUNTIME", "colima")
    monkeypatch.setenv("FLOW_HEALER_DOCKER_ACTIVITY_FILE", str(activity_file))
    monkeypatch.setattr("flow_healer.docker_runtime.docker_daemon_available", lambda: next(states))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kwargs: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
    )

    runtime = ensure_docker_runtime_running(reason="sql_validation")

    assert runtime == "colima"
    assert ["colima", "start"] in calls


def test_maybe_shutdown_idle_docker_runtime_stops_colima_when_only_managed_containers(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv("FLOW_HEALER_DOCKER_RUNTIME", "colima")
    monkeypatch.setenv("FLOW_HEALER_DOCKER_IDLE_SECONDS", "60")
    monkeypatch.setattr("flow_healer.docker_runtime.docker_daemon_available", lambda: True)
    monkeypatch.setattr("flow_healer.docker_runtime.last_docker_activity_at", lambda: 1)
    monkeypatch.setattr("flow_healer.docker_runtime.time.time", lambda: 1000)

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "--format"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="supabase_db_demo123\nflow-healer-demo-test-gate-abc\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert maybe_shutdown_idle_docker_runtime() is True
    assert ["colima", "stop"] in calls


def test_maybe_shutdown_idle_docker_runtime_skips_when_non_managed_containers_exist(monkeypatch) -> None:
    monkeypatch.setenv("FLOW_HEALER_DOCKER_RUNTIME", "colima")
    monkeypatch.setenv("FLOW_HEALER_DOCKER_IDLE_SECONDS", "60")
    monkeypatch.setattr("flow_healer.docker_runtime.docker_daemon_available", lambda: True)
    monkeypatch.setattr("flow_healer.docker_runtime.last_docker_activity_at", lambda: 1)
    monkeypatch.setattr("flow_healer.docker_runtime.time.time", lambda: 1000)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(
            cmd,
            0,
            stdout="postgres_for_other_project\n" if cmd[:3] == ["docker", "ps", "--format"] else "",
            stderr="",
        ),
    )

    assert maybe_shutdown_idle_docker_runtime() is False


def test_record_docker_activity_writes_timestamp_file(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "activity.txt"
    monkeypatch.setenv("FLOW_HEALER_DOCKER_ACTIVITY_FILE", str(target))
    monkeypatch.setattr("flow_healer.docker_runtime.time.time", lambda: 12345)

    record_docker_activity(reason="docker_test_gate")

    assert target.read_text(encoding="utf-8").startswith("12345|docker_test_gate")


def test_docker_idle_shutdown_seconds_has_floor(monkeypatch) -> None:
    monkeypatch.setenv("FLOW_HEALER_DOCKER_IDLE_SECONDS", "5")

    assert docker_idle_shutdown_seconds() == 60
