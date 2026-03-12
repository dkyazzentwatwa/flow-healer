from __future__ import annotations

import os
import subprocess
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, Thread
from urllib import error, request


@dataclass(slots=True, frozen=True)
class AppRuntimeProfile:
    name: str
    command: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str] | None = None
    install_command: tuple[str, ...] = ()
    install_marker_path: str = ""
    fixture_driver_command: tuple[str, ...] = ()
    readiness_url: str | None = None
    readiness_log_text: str | None = None
    browser: str = ""
    headless: bool = True
    viewport: Mapping[str, int] | None = None
    device: str = ""
    startup_timeout_seconds: float = 30.0
    shutdown_timeout_seconds: float = 10.0
    poll_interval_seconds: float = 0.1


@dataclass(slots=True, frozen=True)
class AppHarnessBootResult:
    profile: AppRuntimeProfile
    pid: int
    readiness_url: str | None
    ready_via_url: bool
    ready_via_log: bool
    startup_seconds: float
    output_tail: str


@dataclass(slots=True)
class AppHarnessSession:
    profile: AppRuntimeProfile
    process: subprocess.Popen[str]
    _output_lines: deque[str]
    _reader_thread: Thread
    _stop_lock: Lock = field(default_factory=Lock)
    _stopped: bool = False

    def output_tail(self) -> str:
        return "\n".join(self._output_lines)

    def stop(self) -> int:
        with self._stop_lock:
            if not self._stopped and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=self.profile.shutdown_timeout_seconds)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1)
            self._stopped = True

        if self.process.stdout is not None and not self.process.stdout.closed:
            self.process.stdout.close()
        self._reader_thread.join(timeout=0.5)
        return int(self.process.returncode or 0)


class LocalAppHarness:
    def boot(self, profile: AppRuntimeProfile) -> tuple[AppHarnessBootResult, AppHarnessSession]:
        return self.start(profile)

    def start(self, profile: AppRuntimeProfile) -> tuple[AppHarnessBootResult, AppHarnessSession]:
        env = os.environ.copy()
        if profile.env:
            env.update(profile.env)
        self._maybe_bootstrap_dependencies(profile, env=env)

        process = subprocess.Popen(
            profile.command,
            cwd=profile.cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        assert process.stdout is not None

        output_lines: deque[str] = deque(maxlen=200)
        reader_thread = Thread(
            target=_capture_output,
            args=(process.stdout, output_lines),
            daemon=True,
            name=f"app-harness-{profile.name}",
        )
        reader_thread.start()
        session = AppHarnessSession(
            profile=profile,
            process=process,
            _output_lines=output_lines,
            _reader_thread=reader_thread,
        )

        try:
            result = self._wait_until_ready(session)
        except Exception:
            session.stop()
            raise
        return result, session

    def _maybe_bootstrap_dependencies(self, profile: AppRuntimeProfile, *, env: Mapping[str, str]) -> None:
        install_command = tuple(profile.install_command) or _infer_install_command(profile)
        if not install_command:
            return
        install_marker = _resolve_install_marker(profile)
        if install_marker is not None and install_marker.exists():
            return

        result = subprocess.run(
            install_command,
            cwd=profile.cwd,
            env=dict(env),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            output_tail = "\n".join((result.stdout or "").splitlines()[-40:])
            raise RuntimeError(
                f"{profile.name} dependency bootstrap failed "
                f"(exit code {result.returncode}). Output tail:\n{output_tail}"
            )

    def _wait_until_ready(self, session: AppHarnessSession) -> AppHarnessBootResult:
        profile = session.profile
        require_log = bool(profile.readiness_log_text)
        require_url = bool(profile.readiness_url)
        ready_via_log = False
        ready_via_url = False
        started_at = time.monotonic()

        while True:
            output_tail = session.output_tail()
            if require_log and profile.readiness_log_text and profile.readiness_log_text in output_tail:
                ready_via_log = True
            if require_url and profile.readiness_url and _url_is_ready(
                profile.readiness_url,
                timeout_seconds=max(profile.poll_interval_seconds, 0.2),
            ):
                ready_via_url = True

            if (not require_log or ready_via_log) and (not require_url or ready_via_url):
                return AppHarnessBootResult(
                    profile=profile,
                    pid=session.process.pid,
                    readiness_url=profile.readiness_url,
                    ready_via_url=ready_via_url,
                    ready_via_log=ready_via_log,
                    startup_seconds=time.monotonic() - started_at,
                    output_tail=output_tail,
                )

            exit_code = session.process.poll()
            if exit_code is not None:
                raise RuntimeError(
                    f"{profile.name} exited before becoming ready "
                    f"(exit code {exit_code}). Output tail:\n{output_tail}"
                )

            if time.monotonic() - started_at >= profile.startup_timeout_seconds:
                raise TimeoutError(
                    f"{profile.name} did not become ready within "
                    f"{profile.startup_timeout_seconds:.1f}s. Output tail:\n{output_tail}"
                )

            time.sleep(profile.poll_interval_seconds)


def _capture_output(stream, output_lines: deque[str]) -> None:
    for line in iter(stream.readline, ""):
        output_lines.append(line.rstrip("\n"))


def _resolve_install_marker(profile: AppRuntimeProfile) -> Path | None:
    marker_path = str(profile.install_marker_path or "").strip()
    if marker_path:
        return profile.cwd / marker_path
    if (profile.cwd / "package.json").exists():
        return profile.cwd / "node_modules"
    return None


def _infer_install_command(profile: AppRuntimeProfile) -> tuple[str, ...]:
    package_json = profile.cwd / "package.json"
    if not package_json.exists():
        return ()

    command_head = profile.command[0] if profile.command else ""
    if command_head != "npm":
        return ()
    if (profile.cwd / "package-lock.json").exists():
        return ("npm", "ci")
    return ("npm", "install")


def _url_is_ready(url: str, *, timeout_seconds: float) -> bool:
    try:
        with request.urlopen(url, timeout=timeout_seconds) as response:
            return int(response.status) < 500
    except (error.HTTPError, error.URLError, TimeoutError):
        return False


__all__ = [
    "AppHarnessBootResult",
    "AppHarnessSession",
    "AppRuntimeProfile",
    "LocalAppHarness",
]
