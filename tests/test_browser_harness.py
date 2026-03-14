from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from flow_healer.app_harness import AppRuntimeProfile
from flow_healer.browser_harness import (
    BrowserJourneyResult,
    BrowserStep,
    LocalBrowserHarness,
    _PlaywrightBrowserSession,
    _browser_boot_failure_summary,
    assess_browser_evidence_completeness,
    classify_browser_failure,
    parse_repro_steps,
)


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


def test_parse_repro_steps_supports_state_tolerant_browser_actions() -> None:
    steps = parse_repro_steps(
        (
            "expect_any_text Winner: X || Start game",
            "expect_text_absent Current turn: X",
            "expect_url /game",
        )
    )

    assert steps == (
        BrowserStep(kind="expect_any_text", subject="Winner: X || Start game", argument=""),
        BrowserStep(kind="expect_text_absent", subject="Current turn: X", argument=""),
        BrowserStep(kind="expect_url", subject="/game", argument=""),
    )


def test_check_runtime_available_reports_missing_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = LocalBrowserHarness()

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None if name == "playwright.sync_api" else object())

    available, reason = harness.check_runtime_available()

    assert available is False
    assert "playwright" in reason.lower()


class _FakeBrowserSession:
    def __init__(
        self,
        *,
        fail_expect_text: bool = False,
        visible_texts: set[str] | None = None,
        current_url: str = "",
    ):
        self.fail_expect_text = fail_expect_text
        self.current_url = current_url
        self.visited: list[str] = []
        self.fetch_calls: list[tuple[str, str, str]] = []
        self.visible_texts = visible_texts
        self.clicked: list[str] = []

    def goto(self, url: str) -> None:
        self.current_url = url
        self.visited.append(url)

    def click(self, selector: str) -> None:
        self.clicked.append(selector)

    def expect_text(self, text: str) -> None:
        if self.fail_expect_text:
            raise AssertionError(text)
        if self.visible_texts is not None and text not in self.visible_texts:
            raise AssertionError(text)

    def expect_any_text(self, texts: tuple[str, ...]) -> None:
        if self.fail_expect_text:
            raise AssertionError(" || ".join(texts))
        if self.visible_texts is None:
            return
        if not any(text in self.visible_texts for text in texts):
            raise AssertionError(" || ".join(texts))

    def expect_text_absent(self, text: str) -> None:
        if self.visible_texts is not None and text in self.visible_texts:
            raise AssertionError(text)

    def expect_url(self, url: str) -> None:
        if self.current_url != url:
            raise AssertionError(f"{self.current_url} != {url}")

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


def test_capture_journey_runs_state_tolerant_assertions(tmp_path: Path) -> None:
    session = _FakeBrowserSession(
        visible_texts={"Start game", "Board ready"},
        current_url="http://127.0.0.1:3000/game",
    )
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
            "goto /game",
            "expect_any_text Winner: X || Start game",
            "expect_text_absent Current turn: X",
            "expect_url http://127.0.0.1:3000/game",
        ),
        artifact_root=tmp_path / "artifacts",
        phase="resolution",
        expect_failure=False,
    )

    assert result.passed is True
    assert result.final_url == "http://127.0.0.1:3000/game"


def test_capture_journey_handles_completed_state_then_restart_to_fresh_state(tmp_path: Path) -> None:
    class _RestartSession(_FakeBrowserSession):
        def __init__(self) -> None:
            super().__init__(
                visible_texts={"Winner: X", "Play again"},
                current_url="http://127.0.0.1:3000/game",
            )

        def click(self, selector: str) -> None:
            super().click(selector)
            if selector == "button.restart":
                self.visible_texts = {"Start game", "Board ready"}

    session = _RestartSession()
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
            "goto /game",
            "expect_any_text Winner: X || Start game",
            "click button.restart",
            "expect_text Start game",
            "expect_text_absent Winner: X",
            "expect_url http://127.0.0.1:3000/game",
        ),
        artifact_root=tmp_path / "artifacts",
        phase="resolution",
        expect_failure=False,
    )

    assert result.passed is True
    assert session.clicked == ["button.restart"]
    assert Path(result.screenshot_path).exists()
    assert Path(result.console_log_path).exists()
    assert Path(result.network_log_path).exists()


def test_capture_journey_supports_fresh_deterministic_playthrough_without_restart(tmp_path: Path) -> None:
    class _DeterministicBoardSession(_FakeBrowserSession):
        def __init__(self) -> None:
            super().__init__(
                visible_texts={"Start game", "Current turn: X", "Tic Tac Toe Browser Signal T3"},
                current_url="http://127.0.0.1:3000/tictactoe",
            )
            self._moves: list[str] = []

        def click(self, selector: str) -> None:
            super().click(selector)
            self._moves.append(selector)
            if len(self._moves) < 5:
                self.visible_texts = {"Current turn: X", "Tic Tac Toe Browser Signal T3"}
                return
            self.visible_texts = {"Winner: X", "Restart", "Tic Tac Toe Browser Signal T3"}

    session = _DeterministicBoardSession()
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
            "goto /tictactoe",
            "expect_url http://127.0.0.1:3000/tictactoe",
            "expect_text Tic Tac Toe Browser Signal T3",
            "expect_any_text Start game || Current turn: X",
            'click [aria-label="Cell 1"]',
            'click [aria-label="Cell 2"]',
            'click [aria-label="Cell 4"]',
            'click [aria-label="Cell 5"]',
            'click [aria-label="Cell 7"]',
            "expect_text Winner: X",
        ),
        artifact_root=tmp_path / "artifacts",
        phase="resolution",
        expect_failure=False,
    )

    assert result.passed is True
    assert session.clicked == [
        '[aria-label="Cell 1"]',
        '[aria-label="Cell 2"]',
        '[aria-label="Cell 4"]',
        '[aria-label="Cell 5"]',
        '[aria-label="Cell 7"]',
    ]


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


def test_capture_journey_passes_storage_state_to_session_factory(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    session = _FakeBrowserSession()

    def _session_factory(profile, entry_url, artifact_root, phase, storage_state_path=None):
        captured["storage_state_path"] = storage_state_path
        return session

    harness = LocalBrowserHarness(session_factory=_session_factory)
    profile = AppRuntimeProfile(
        name="web",
        command=("npm", "run", "dev"),
        cwd=tmp_path,
        browser="chromium",
    )
    storage_state_path = tmp_path / "auth-state.json"

    result = harness.capture_journey(
        profile=profile,
        entry_url="http://127.0.0.1:3000",
        repro_steps=("goto /", "expect_text Available todo routes"),
        artifact_root=tmp_path / "artifacts",
        phase="resolution",
        expect_failure=False,
        storage_state_path=str(storage_state_path),
    )

    assert result.passed is True
    assert captured["storage_state_path"] == str(storage_state_path)


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


def test_playwright_session_click_settles_after_interaction() -> None:
    class _FakeLocator:
        def __init__(self) -> None:
            self.clicked = 0

        def click(self) -> None:
            self.clicked += 1

    class _FakePage:
        def __init__(self) -> None:
            self.locator_calls: list[str] = []
            self.wait_timeout_calls: list[int] = []
            self.events: list[str] = []
            self.locator_obj = _FakeLocator()

        def on(self, event: str, _handler) -> None:
            self.events.append(event)

        def locator(self, selector: str):
            self.locator_calls.append(selector)
            return self.locator_obj

        def wait_for_timeout(self, value: int) -> None:
            self.wait_timeout_calls.append(value)

    class _FakeContext:
        def __init__(self, page) -> None:
            self.pages = [page]

    page = _FakePage()
    context = _FakeContext(page)

    session = _PlaywrightBrowserSession.__new__(_PlaywrightBrowserSession)
    session._context = context
    session._page = page
    session._console_entries = []
    session._network_entries = []

    session.click("css=.cell")

    assert page.locator_calls == [".cell"]
    assert page.locator_obj.clicked == 1
    assert page.wait_timeout_calls


def test_playwright_session_click_adopts_new_popup_page() -> None:
    class _FakeLocator:
        def __init__(self, click_impl) -> None:
            self._click_impl = click_impl

        def click(self) -> None:
            self._click_impl()

    class _FakePage:
        def __init__(self, *, name: str) -> None:
            self.name = name
            self.events: list[str] = []
            self.wait_timeout_calls: list[int] = []
            self.load_state_calls: list[tuple[str, int]] = []
            self._locator_factory = None

        def on(self, event: str, _handler) -> None:
            self.events.append(event)

        def locator(self, _selector: str):
            assert self._locator_factory is not None
            return self._locator_factory()

        def wait_for_load_state(self, state: str, timeout: int = 0) -> None:
            self.load_state_calls.append((state, timeout))

        def wait_for_timeout(self, value: int) -> None:
            self.wait_timeout_calls.append(value)

    class _FakeContext:
        def __init__(self, page) -> None:
            self.pages = [page]

    origin = _FakePage(name="origin")
    popup = _FakePage(name="popup")
    context = _FakeContext(origin)

    def _open_popup() -> None:
        context.pages.append(popup)

    origin._locator_factory = lambda: _FakeLocator(_open_popup)
    popup._locator_factory = lambda: _FakeLocator(lambda: None)

    session = _PlaywrightBrowserSession.__new__(_PlaywrightBrowserSession)
    session._context = context
    session._page = origin
    session._console_entries = []
    session._network_entries = []

    session.click("css=.open")

    assert session._page is popup
    assert popup.load_state_calls
    assert "console" in popup.events
    assert popup.wait_timeout_calls


def test_browser_boot_failure_summary_flags_same_origin_script_404s() -> None:
    summary = _browser_boot_failure_summary(
        entry_url="http://127.0.0.1:3000/tictactoe-t4",
        console_entries=(
            "[error] Failed to load resource: the server responded with a status of 404 (Not Found)\n",
        ),
        network_entries=(
            {
                "event": "response",
                "status": 404,
                "url": "http://127.0.0.1:3000/_next/static/chunks/main-app.js?v=1",
                "resource_type": "script",
            },
            {
                "event": "response",
                "status": 404,
                "url": "http://127.0.0.1:3000/favicon.ico",
                "resource_type": "other",
            },
        ),
    )

    assert summary["hydration_ready"] is False
    assert summary["same_origin_asset_failures"] == (
        {
            "resource_type": "script",
            "status": 404,
            "url": "http://127.0.0.1:3000/_next/static/chunks/main-app.js?v=1",
        },
    )
    assert summary["console_errors"] == (
        "Failed to load resource: the server responded with a status of 404 (Not Found)",
    )


def test_playwright_session_goto_reloads_once_after_client_boot_failures() -> None:
    class _FakePage:
        def __init__(self) -> None:
            self.goto_calls: list[tuple[str, str]] = []
            self.reload_calls: list[str] = []
            self.wait_timeout_calls: list[int] = []
            self.wait_for_load_state_calls: list[tuple[str, int]] = []
            self.url = "http://127.0.0.1:3000/tictactoe-t4"

        def goto(self, url: str, wait_until: str = "") -> None:
            self.goto_calls.append((url, wait_until))

        def reload(self, wait_until: str = "") -> None:
            self.reload_calls.append(wait_until)

        def wait_for_load_state(self, state: str, timeout: int = 0) -> None:
            self.wait_for_load_state_calls.append((state, timeout))

        def wait_for_timeout(self, value: int) -> None:
            self.wait_timeout_calls.append(value)

    session = _PlaywrightBrowserSession.__new__(_PlaywrightBrowserSession)
    session._page = _FakePage()
    session._entry_url = "http://127.0.0.1:3000/tictactoe-t4"
    session._console_entries = [
        "[error] Failed to load resource: the server responded with a status of 404 (Not Found)\n"
    ]
    session._network_entries = [
        {
            "event": "response",
            "status": 404,
            "url": "http://127.0.0.1:3000/_next/static/chunks/main-app.js?v=1",
            "resource_type": "script",
        }
    ]

    session.goto("http://127.0.0.1:3000/tictactoe-t4")

    assert session._page.goto_calls == [("http://127.0.0.1:3000/tictactoe-t4", "domcontentloaded")]
    assert session._page.reload_calls == ["domcontentloaded"]
    assert session._page.wait_for_load_state_calls == [("networkidle", 2000)]
    assert session._page.wait_timeout_calls
    assert session._last_boot_failure_summary["hydration_ready"] is True


def test_playwright_session_boot_check_reassesses_after_reload_settle() -> None:
    class _FakePage:
        def __init__(self, session) -> None:
            self.session = session
            self.url = "http://127.0.0.1:3000/rps-r1"

        def goto(self, url: str, wait_until: str = "") -> None:
            return None

        def reload(self, wait_until: str = "") -> None:
            self.session._network_entries = [
                {
                    "event": "response",
                    "status": 200,
                    "url": "http://127.0.0.1:3000/_next/static/chunks/main-app.js?v=2",
                    "resource_type": "script",
                },
                {
                    "event": "response",
                    "status": 200,
                    "url": "http://127.0.0.1:3000/_next/static/chunks/app-pages-internals.js",
                    "resource_type": "script",
                },
            ]
            self.session._console_entries = []

        def wait_for_load_state(self, state: str, timeout: int = 0) -> None:
            return None

        def wait_for_timeout(self, value: int) -> None:
            return None

    session = _PlaywrightBrowserSession.__new__(_PlaywrightBrowserSession)
    session._entry_url = "http://127.0.0.1:3000/rps-r1"
    session._console_entries = [
        "[error] Failed to load resource: the server responded with a status of 404 (Not Found)\n"
    ]
    session._network_entries = [
        {
            "event": "response",
            "status": 404,
            "url": "http://127.0.0.1:3000/_next/static/chunks/main-app.js?v=1",
            "resource_type": "script",
        }
    ]
    session._page = _FakePage(session)

    summary = session._ensure_client_boot_ready("http://127.0.0.1:3000/rps-r1")

    assert summary["hydration_ready"] is True
    assert summary["same_origin_asset_failures"] == ()


def test_assess_completeness_repro_phase_requires_screenshot_and_console(tmp_path: Path) -> None:
    screenshot = tmp_path / "repro.png"
    console = tmp_path / "repro-console.log"
    screenshot.write_text("png", encoding="utf-8")
    console.write_text("console", encoding="utf-8")
    result = BrowserJourneyResult(
        phase="repro",
        passed=False,
        expected_failure_observed=True,
        final_url="http://127.0.0.1:3000",
        screenshot_path=str(screenshot),
        console_log_path=str(console),
        hydration_ready=False,
        same_origin_asset_failures=(
            {
                "resource_type": "script",
                "status": 404,
                "url": "http://127.0.0.1:3000/_next/static/chunks/main-app.js?v=1",
            },
        ),
    )

    completeness = assess_browser_evidence_completeness(result)

    assert completeness.required == ("screenshot_path", "console_log_path")
    assert completeness.present == ("screenshot_path", "console_log_path")
    assert completeness.missing == ()
    assert completeness.complete is True
    assert completeness.missing_class == "none"
    assert result.hydration_ready is False


def test_capture_journey_records_browser_boot_diagnostics_from_session(tmp_path: Path) -> None:
    class _DiagnosticSession(_FakeBrowserSession):
        def diagnostics(self) -> dict[str, object]:
            return {
                "hydration_ready": False,
                "same_origin_asset_failures": (
                    {
                        "resource_type": "script",
                        "status": 404,
                        "url": "http://127.0.0.1:3000/_next/static/chunks/main-app.js?v=1",
                    },
                ),
                "console_errors": ("chunk load failed",),
            }

    session = _DiagnosticSession()
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
        repro_steps=("goto /", "expect_text Available todo routes"),
        artifact_root=tmp_path / "artifacts",
        phase="resolution",
        expect_failure=False,
    )

    assert result.hydration_ready is False
    assert result.console_errors == ("chunk load failed",)
    assert result.same_origin_asset_failures == (
        {
            "resource_type": "script",
            "status": 404,
            "url": "http://127.0.0.1:3000/_next/static/chunks/main-app.js?v=1",
        },
    )



def test_assess_completeness_verify_phase_requires_network_log(tmp_path: Path) -> None:
    screenshot = tmp_path / "verify.png"
    console = tmp_path / "verify-console.log"
    screenshot.write_text("png", encoding="utf-8")
    console.write_text("console", encoding="utf-8")
    result = BrowserJourneyResult(
        phase="verify",
        passed=True,
        expected_failure_observed=False,
        final_url="http://127.0.0.1:3000",
        screenshot_path=str(screenshot),
        console_log_path=str(console),
    )

    completeness = assess_browser_evidence_completeness(result)

    assert completeness.required == ("screenshot_path", "console_log_path", "network_log_path")
    assert completeness.missing == ("network_log_path",)
    assert completeness.complete is False


def test_assess_completeness_missing_screenshot_sets_class(tmp_path: Path) -> None:
    console = tmp_path / "repro-console.log"
    console.write_text("console", encoding="utf-8")
    result = BrowserJourneyResult(
        phase="repro",
        passed=False,
        expected_failure_observed=True,
        final_url="http://127.0.0.1:3000",
        screenshot_path=str(tmp_path / "missing.png"),
        console_log_path=str(console),
    )

    completeness = assess_browser_evidence_completeness(result)

    assert completeness.complete is False
    assert completeness.missing == ("screenshot_path",)
    assert completeness.missing_class == "missing_screenshot"


def test_classify_browser_failure_returns_fixture_auth_drift_on_auth_error() -> None:
    result = BrowserJourneyResult(
        phase="verify",
        passed=False,
        expected_failure_observed=False,
        final_url="http://127.0.0.1:3000",
        error="401 unauthorized after login redirect",
    )

    assert classify_browser_failure(result) == "fixture_auth_drift"


def test_classify_browser_failure_returns_generic_flake_on_non_auth_error() -> None:
    result = BrowserJourneyResult(
        phase="verify",
        passed=False,
        expected_failure_observed=False,
        final_url="http://127.0.0.1:3000",
        error="timeout waiting for selector",
    )

    assert classify_browser_failure(result) == "generic_browser_flake"


def test_browser_evidence_completeness_round_trips_all_active_profiles(tmp_path: Path) -> None:
    for profile_name in ("node-next-web", "ruby-rails-web", "java-spring-web"):
        phase_root = tmp_path / profile_name
        screenshot = phase_root / "verify.png"
        console = phase_root / "verify-console.log"
        network = phase_root / "verify-network.jsonl"
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        screenshot.write_text("png", encoding="utf-8")
        console.write_text("console", encoding="utf-8")
        network.write_text("{\"event\":\"response\"}\n", encoding="utf-8")
        result = BrowserJourneyResult(
            phase="verify",
            passed=True,
            expected_failure_observed=False,
            final_url="http://127.0.0.1:3000",
            screenshot_path=str(screenshot),
            console_log_path=str(console),
            network_log_path=str(network),
        )

        completeness = assess_browser_evidence_completeness(result)

        assert completeness.complete is True, profile_name
        assert completeness.missing_class == "none", profile_name
