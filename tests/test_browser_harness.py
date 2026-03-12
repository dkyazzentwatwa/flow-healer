from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from flow_healer.app_harness import AppRuntimeProfile
from flow_healer.browser_harness import BrowserStep, LocalBrowserHarness, _PlaywrightBrowserSession, parse_repro_steps


def test_parse_repro_steps_supports_core_browser_actions() -> None:
    steps = parse_repro_steps(
        (
            "goto /",
            "expect_text Available todo routes",
            'fetch POST /api/todos json={"title":"Ship browser proof"}',
        )
    )

    assert steps == (
        BrowserStep(kind="goto", subject="/", argument=""),
        BrowserStep(kind="expect_text", subject="Available todo routes", argument=""),
        BrowserStep(
            kind="fetch",
            subject="POST /api/todos",
            argument='json={"title":"Ship browser proof"}',
        ),
    )


def test_check_runtime_available_reports_missing_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = LocalBrowserHarness()

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None if name == "playwright.sync_api" else object())

    available, reason = harness.check_runtime_available()

    assert available is False
    assert "playwright" in reason.lower()


class _FakeBrowserSession:
    def __init__(self, *, fail_expect_text: bool = False):
        self.fail_expect_text = fail_expect_text
        self.current_url = ""
        self.visited: list[str] = []
        self.fetch_calls: list[tuple[str, str, str]] = []

    def goto(self, url: str) -> None:
        self.current_url = url
        self.visited.append(url)

    def expect_text(self, text: str) -> None:
        if self.fail_expect_text:
            raise AssertionError(text)

    def fetch(self, method: str, path: str, payload: str = "") -> None:
        self.fetch_calls.append((method, path, payload))

    def close(self) -> None:
        return None


def test_capture_journey_records_expected_failure_and_artifacts(tmp_path: Path) -> None:
    harness = LocalBrowserHarness(session_factory=lambda profile, entry_url, artifact_root, phase: _FakeBrowserSession(fail_expect_text=True))
    profile = AppRuntimeProfile(
        name="web",
        command=("npm", "run", "dev"),
        cwd=tmp_path,
        browser="chromium",
    )

    result = harness.capture_journey(
        profile=profile,
        entry_url="http://127.0.0.1:3000",
        repro_steps=("goto /", "expect_text Broken widget"),
        artifact_root=tmp_path / "artifacts",
        phase="failure",
        expect_failure=True,
    )

    assert result.passed is False
    assert result.expected_failure_observed is True
    assert result.failure_step == "expect_text Broken widget"
    assert Path(result.screenshot_path).exists()
    assert Path(result.video_path).exists()
    assert Path(result.console_log_path).exists()
    assert Path(result.network_log_path).exists()


def test_capture_journey_runs_fetch_steps_and_passes_resolution_flow(tmp_path: Path) -> None:
    session = _FakeBrowserSession()
    harness = LocalBrowserHarness(session_factory=lambda profile, entry_url, artifact_root, phase: session)
    profile = AppRuntimeProfile(
        name="web",
        command=("npm", "run", "dev"),
        cwd=tmp_path,
        browser="chromium",
    )

    result = harness.capture_journey(
        profile=profile,
        entry_url="http://127.0.0.1:3000",
        repro_steps=(
            "goto /",
            'fetch POST /api/todos json={"title":"Ship browser proof"}',
            "expect_text Available todo routes",
        ),
        artifact_root=tmp_path / "artifacts",
        phase="resolution",
        expect_failure=False,
    )

    assert result.passed is True
    assert result.expected_failure_observed is False
    assert session.fetch_calls == [("POST", "/api/todos", '{"title":"Ship browser proof"}')]
    assert result.final_url == "http://127.0.0.1:3000/"


def test_capture_journey_accepts_preparsed_browser_steps(tmp_path: Path) -> None:
    session = _FakeBrowserSession()
    harness = LocalBrowserHarness(session_factory=lambda profile, entry_url, artifact_root, phase: session)
    profile = AppRuntimeProfile(
        name="web",
        command=("npm", "run", "dev"),
        cwd=tmp_path,
        browser="chromium",
    )

    result = harness.capture_journey(
        profile=profile,
        entry_url="http://127.0.0.1:3000",
        repro_steps=(
            BrowserStep(kind="goto", subject="/"),
            BrowserStep(kind="expect_text", subject="Available todo routes"),
        ),
        artifact_root=tmp_path / "artifacts",
        phase="resolution",
        expect_failure=False,
    )

    assert result.passed is True
    assert session.visited == ["http://127.0.0.1:3000/"]


def test_playwright_session_close_saves_video_before_shutdown(tmp_path: Path) -> None:
    events: list[str] = []

    class _FakeVideo:
        def save_as(self, path: str) -> None:
            events.append(f"video:{Path(path).name}")
            Path(path).write_text("video", encoding="utf-8")

    class _FakePage:
        def __init__(self) -> None:
            self.video = _FakeVideo()

        def close(self) -> None:
            events.append("page")

    class _FakeClosable:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            events.append(self.name)

    class _FakePlaywright:
        def stop(self) -> None:
            events.append("playwright")

    session = _PlaywrightBrowserSession.__new__(_PlaywrightBrowserSession)
    session._page = _FakePage()
    session._context = _FakeClosable("context")
    session._browser = _FakeClosable("browser")
    session._playwright = _FakePlaywright()
    session._video_output = tmp_path / "captured.webm"

    session.close()

    assert events == ["page", "video:captured.webm", "context", "browser", "playwright"]
    assert session._video_output.exists()


def test_playwright_session_close_tolerates_missing_video_capture(tmp_path: Path) -> None:
    events: list[str] = []

    class _FakePage:
        def __init__(self) -> None:
            self.video = None

        def close(self) -> None:
            events.append("page")

    class _FakeClosable:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            events.append(self.name)

    class _FakePlaywright:
        def stop(self) -> None:
            events.append("playwright")

    session = _PlaywrightBrowserSession.__new__(_PlaywrightBrowserSession)
    session._page = _FakePage()
    session._context = _FakeClosable("context")
    session._browser = _FakeClosable("browser")
    session._playwright = _FakePlaywright()
    session._video_output = tmp_path / "missing.webm"

    session.close()

    assert events == ["page", "context", "browser", "playwright"]
    assert not session._video_output.exists()
