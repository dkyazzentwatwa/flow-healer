import sys
import textwrap
from pathlib import Path

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
        assert attempts == [profile.readiness_url] * 4
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
