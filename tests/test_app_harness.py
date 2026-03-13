import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from flow_healer.app_harness import AppRuntimeProfile, LocalAppHarness


def _write_script(tmp_path: Path, name: str, source: str) -> Path:
    script_path = tmp_path / name
    script_path.write_text(textwrap.dedent(source), encoding="utf-8")
    return script_path


def test_boot_waits_for_log_readiness_and_returns_stoppable_session(tmp_path: Path) -> None:
    script_path = _write_script(
        tmp_path,
        "log_ready_app.py",
        """
        import signal
        import sys
        import time

        def _handle_term(signum, frame):
            print("shutting down", flush=True)
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, _handle_term)
        print("booting", flush=True)
        time.sleep(0.2)
        print("APP READY", flush=True)
        while True:
            time.sleep(0.1)
        """,
    )
    harness = LocalAppHarness()
    profile = AppRuntimeProfile(
        name="log-ready-app",
        command=(sys.executable, "-u", str(script_path)),
        cwd=tmp_path,
        readiness_log_text="APP READY",
        startup_timeout_seconds=2.0,
        poll_interval_seconds=0.05,
    )

    result, session = harness.boot(profile)
    try:
        assert result.profile == profile
        assert result.pid == session.process.pid
        assert result.ready_via_log is True
        assert result.ready_via_url is False
        assert "APP READY" in result.output_tail
        assert session.process.poll() is None
    finally:
        assert session.stop() == 0


def test_start_waits_for_url_readiness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script_path = _write_script(
        tmp_path,
        "url_ready_app.py",
        """
        import signal
        import time

        def _handle_term(signum, frame):
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, _handle_term)
        while True:
            time.sleep(0.1)
        """,
    )
    attempts: list[str] = []

    def fake_url_is_ready(url: str, *, timeout_seconds: float) -> bool:
        attempts.append(url)
        return len(attempts) >= 3

    monkeypatch.setattr("flow_healer.app_harness._url_is_ready", fake_url_is_ready)

    harness = LocalAppHarness()
    profile = AppRuntimeProfile(
        name="url-ready-app",
        command=(sys.executable, "-u", str(script_path)),
        cwd=tmp_path,
        readiness_url="http://127.0.0.1:43123/healthz",
        startup_timeout_seconds=2.0,
        poll_interval_seconds=0.05,
    )

    result, session = harness.start(profile)
    try:
        assert result.ready_via_url is True
        assert result.ready_via_log is False
        assert result.readiness_url == profile.readiness_url
        assert attempts == [profile.readiness_url] * 3
        assert session.process.poll() is None
    finally:
        assert session.stop() == 0


def test_start_requires_both_log_and_url_when_both_are_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = _write_script(
        tmp_path,
        "combined_ready_app.py",
        """
        import signal
        import time

        def _handle_term(signum, frame):
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, _handle_term)
        print("warming up", flush=True)
        time.sleep(0.1)
        print("LOG READY", flush=True)
        while True:
            time.sleep(0.1)
        """,
    )
    attempts: list[str] = []

    def fake_url_is_ready(url: str, *, timeout_seconds: float) -> bool:
        attempts.append(url)
        return len(attempts) >= 4

    monkeypatch.setattr("flow_healer.app_harness._url_is_ready", fake_url_is_ready)

    harness = LocalAppHarness()
    profile = AppRuntimeProfile(
        name="combined-ready-app",
        command=(sys.executable, "-u", str(script_path)),
        cwd=tmp_path,
        readiness_url="http://127.0.0.1:43124/healthz",
        readiness_log_text="LOG READY",
        startup_timeout_seconds=2.0,
        poll_interval_seconds=0.05,
    )

    result, session = harness.start(profile)
    try:
        assert result.ready_via_url is True
        assert result.ready_via_log is True
        assert result.readiness_url == profile.readiness_url
        assert "LOG READY" in result.output_tail
        assert len(attempts) >= 4
        assert set(attempts) == {profile.readiness_url}
    finally:
        assert session.stop() == 0


def test_start_raises_when_process_exits_before_becoming_ready(tmp_path: Path) -> None:
    script_path = _write_script(
        tmp_path,
        "failing_app.py",
        """
        print("boot failed", flush=True)
        raise SystemExit(3)
        """,
    )
    harness = LocalAppHarness()
    profile = AppRuntimeProfile(
        name="failing-app",
        command=(sys.executable, "-u", str(script_path)),
        cwd=tmp_path,
        readiness_log_text="APP READY",
        startup_timeout_seconds=1.0,
        poll_interval_seconds=0.05,
    )

    with pytest.raises(RuntimeError, match="exited before becoming ready"):
        harness.start(profile)


def test_app_runtime_profile_supports_browser_configuration_fields(tmp_path: Path) -> None:
    profile = AppRuntimeProfile(
        name="browser-app",
        command=(sys.executable, "-u", "app.py"),
        cwd=tmp_path,
        browser="chromium",
        headless=True,
        viewport={"width": 1280, "height": 800},
        device="Desktop Chrome",
    )

    assert profile.browser == "chromium"
    assert profile.headless is True
    assert profile.viewport == {"width": 1280, "height": 800}
    assert profile.device == "Desktop Chrome"


def test_app_runtime_profile_supports_fixture_driver_command(tmp_path: Path) -> None:
    profile = AppRuntimeProfile(
        name="browser-app",
        command=(sys.executable, "-u", "app.py"),
        cwd=tmp_path,
        fixture_driver_command=(sys.executable, "scripts/fixture_driver.py"),
    )

    assert profile.fixture_driver_command == (sys.executable, "scripts/fixture_driver.py")


def test_bootstrap_dependencies_runs_npm_ci_when_node_modules_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")
    (tmp_path / "package-lock.json").write_text('{"lockfileVersion":3}\n', encoding="utf-8")
    commands: list[tuple[str, ...]] = []

    def fake_run(command, **kwargs):
        commands.append(tuple(command))
        (tmp_path / "node_modules").mkdir()
        return SimpleNamespace(returncode=0, stdout="installed")

    monkeypatch.setattr("flow_healer.app_harness.subprocess.run", fake_run)

    harness = LocalAppHarness()
    profile = AppRuntimeProfile(
        name="node-app",
        command=("npm", "run", "dev"),
        cwd=tmp_path,
    )

    harness._maybe_bootstrap_dependencies(profile, env={})

    assert commands == [("npm", "ci")]


def test_bootstrap_dependencies_raises_on_install_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")

    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="install exploded")

    monkeypatch.setattr("flow_healer.app_harness.subprocess.run", fake_run)

    harness = LocalAppHarness()
    profile = AppRuntimeProfile(
        name="node-app",
        command=("npm", "run", "dev"),
        cwd=tmp_path,
    )

    with pytest.raises(RuntimeError, match="dependency bootstrap failed"):
        harness._maybe_bootstrap_dependencies(profile, env={})


def test_session_stop_signals_process_group_before_kill(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[str, int]] = []

    class _FakeStdout:
        closed = False

        def close(self) -> None:
            self.closed = True

    class _FakeProcess:
        def __init__(self) -> None:
            self.pid = 4242
            self.returncode = 0
            self.stdout = _FakeStdout()

        def poll(self):
            return None

        def terminate(self) -> None:
            calls.append(("terminate", self.pid))

        def wait(self, timeout=None):
            return 0

        def kill(self) -> None:
            calls.append(("kill", self.pid))

    monkeypatch.setattr("flow_healer.app_harness.os.getpgid", lambda pid: pid)
    monkeypatch.setattr("flow_healer.app_harness.os.killpg", lambda pgid, sig: calls.append(("killpg", sig)))

    from flow_healer.app_harness import AppHarnessSession

    class _FakeThread:
        def join(self, timeout=None) -> None:
            return None

    profile = AppRuntimeProfile(
        name="group-stop",
        command=(sys.executable, "-u", "noop.py"),
        cwd=tmp_path,
    )
    harness_session = AppHarnessSession(
        profile=profile,
        process=_FakeProcess(),  # type: ignore[arg-type]
        _output_lines=[],
        _reader_thread=_FakeThread(),  # type: ignore[arg-type]
    )

    result = harness_session.stop()

    assert result == 0
    assert calls
    assert calls[0][0] == "killpg"
    assert all(call[0] != "terminate" for call in calls)
