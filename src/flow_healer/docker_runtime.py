from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path


_APP_NAMES = {
    "docker_desktop": "Docker",
    "orbstack": "OrbStack",
}


def record_docker_activity(*, reason: str) -> None:
    path = _activity_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{int(time.time())}|{str(reason or '').strip()}\n", encoding="utf-8")
    except OSError:
        return


def last_docker_activity_at() -> int:
    path = _activity_file_path()
    if not path.exists():
        return 0
    raw = path.read_text(encoding="utf-8").strip().split("|", 1)[0]
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def ensure_docker_runtime_running(*, reason: str) -> str:
    record_docker_activity(reason=reason)
    if docker_daemon_available():
        return selected_docker_runtime()
    runtime = selected_docker_runtime()
    if runtime == "none":
        return runtime
    try:
        if runtime == "colima":
            _run_runtime_command(["colima", "start"])
        elif runtime in {"docker_desktop", "orbstack"}:
            _open_app(_APP_NAMES[runtime])
    except (FileNotFoundError, OSError, subprocess.CalledProcessError):
        return runtime
    _wait_for_docker_ready(timeout_seconds=_docker_start_timeout_seconds())
    record_docker_activity(reason=reason)
    return runtime


def maybe_shutdown_idle_docker_runtime() -> bool:
    if not docker_idle_shutdown_enabled():
        return False
    if _seconds_since_last_activity() < docker_idle_shutdown_seconds():
        return False
    if not docker_daemon_available():
        return False
    if _has_non_flow_healer_containers():
        return False
    runtime = selected_docker_runtime()
    if runtime == "colima":
        _run_runtime_command(["colima", "stop"])
        return True
    if runtime in {"docker_desktop", "orbstack"}:
        _quit_app(_APP_NAMES[runtime])
        return True
    return False


def docker_daemon_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "info"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (FileNotFoundError, OSError):
        return False
    return proc.returncode == 0


def selected_docker_runtime() -> str:
    configured = str(os.getenv("FLOW_HEALER_DOCKER_RUNTIME", "auto")).strip().lower()
    if configured in {"docker_desktop", "colima", "orbstack", "none"}:
        return configured
    if shutil.which("colima") is not None:
        return "colima"
    if _app_installed("OrbStack"):
        return "orbstack"
    return "docker_desktop"


def docker_idle_shutdown_enabled() -> bool:
    raw = str(os.getenv("FLOW_HEALER_DOCKER_IDLE_SHUTDOWN", "1")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def docker_idle_shutdown_seconds() -> int:
    raw = str(os.getenv("FLOW_HEALER_DOCKER_IDLE_SECONDS", "900")).strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return 900


def _seconds_since_last_activity() -> int:
    last = last_docker_activity_at()
    if last <= 0:
        return 0
    return max(0, int(time.time()) - last)


def _docker_start_timeout_seconds() -> int:
    raw = str(os.getenv("FLOW_HEALER_DOCKER_START_TIMEOUT_SECONDS", "180")).strip()
    try:
        return max(30, int(raw))
    except ValueError:
        return 180


def _activity_file_path() -> Path:
    override = str(os.getenv("FLOW_HEALER_DOCKER_ACTIVITY_FILE") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path("~/.flow-healer/docker-runtime-activity.txt").expanduser().resolve()


def _wait_for_docker_ready(*, timeout_seconds: int) -> None:
    deadline = time.monotonic() + max(1, timeout_seconds)
    while time.monotonic() < deadline:
        if docker_daemon_available():
            return
        time.sleep(1.0)
    raise RuntimeError("docker runtime did not become ready before timeout")


def _run_runtime_command(command: list[str]) -> None:
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=max(60, _docker_start_timeout_seconds()),
    )


def _open_app(name: str) -> None:
    subprocess.run(
        ["open", "-a", name],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _quit_app(name: str) -> None:
    subprocess.run(
        ["osascript", "-e", f'tell application "{name}" to quit'],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _app_installed(name: str) -> bool:
    try:
        proc = subprocess.run(
            ["open", "-Ra", name],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, OSError):
        return False
    return proc.returncode == 0


def _has_non_flow_healer_containers() -> bool:
    proc = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if proc.returncode != 0:
        return True
    names = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    if not names:
        return False
    allowed_prefixes = ("supabase_", "flow-healer-")
    return any(not name.startswith(allowed_prefixes) for name in names)
