from __future__ import annotations

import inspect
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

from .app_harness import AppRuntimeProfile


_DEFAULT_VIEWPORT = {"width": 1280, "height": 800}
_POST_CLICK_SETTLE_MS = 75
REQUIRED_ARTIFACTS_BY_PHASE: dict[str, tuple[str, ...]] = {
    "repro": ("screenshot_path", "console_log_path"),
    "verify": ("screenshot_path", "console_log_path", "network_log_path"),
    "setup": ("screenshot_path",),
}


@dataclass(slots=True, frozen=True)
class BrowserStep:
    kind: str
    subject: str
    argument: str = ""


@dataclass(slots=True, frozen=True)
class BrowserJourneyResult:
    phase: str
    passed: bool
    expected_failure_observed: bool
    final_url: str
    failure_step: str = ""
    error: str = ""
    screenshot_path: str = ""
    video_path: str = ""
    console_log_path: str = ""
    network_log_path: str = ""
    transcript: tuple[dict[str, object], ...] = ()


@dataclass(slots=True, frozen=True)
class BrowserEvidenceCompleteness:
    phase: str
    required: tuple[str, ...]
    present: tuple[str, ...]
    missing: tuple[str, ...]
    complete: bool
    missing_class: str


class LocalBrowserHarness:
    def __init__(
        self,
        *,
        session_factory: Callable[[AppRuntimeProfile, str, Path, str], Any] | None = None,
    ) -> None:
        self._session_factory = session_factory

    def check_runtime_available(self) -> tuple[bool, str]:
        if importlib.util.find_spec("playwright.sync_api") is None:
            return False, "Playwright is not installed. Install the browser extra or dev dependencies."
        return True, ""

    def capture_journey(
        self,
        *,
        profile: AppRuntimeProfile,
        entry_url: str,
        repro_steps: tuple[str | BrowserStep, ...],
        artifact_root: Path,
        phase: str,
        expect_failure: bool,
        storage_state_path: str = "",
    ) -> BrowserJourneyResult:
        steps = _coerce_repro_steps(repro_steps)
        phase_root = Path(artifact_root) / phase
        phase_root.mkdir(parents=True, exist_ok=True)
        session = self._build_session(
            profile=profile,
            entry_url=entry_url,
            artifact_root=artifact_root,
            phase=phase,
            storage_state_path=storage_state_path,
        )
        transcript: list[dict[str, object]] = []
        passed = True
        expected_failure_observed = False
        failure_step = ""
        error = ""
        artifact_error = ""
        screenshot_path = str(phase_root / f"{phase}.png")
        video_path = str(phase_root / f"{phase}.webm")
        console_log_path = str(phase_root / f"{phase}-console.log")
        network_log_path = str(phase_root / f"{phase}-network.jsonl")

        try:
            for step in steps:
                step_label = _format_step(step)
                try:
                    self._run_step(session=session, step=step, entry_url=entry_url)
                except Exception as exc:
                    passed = False
                    failure_step = step_label
                    error = str(exc)
                    transcript.append(
                        {
                            "step": step_label,
                            "status": "failed",
                            "error": error,
                        }
                    )
                    expected_failure_observed = bool(expect_failure)
                    break
                transcript.append({"step": step_label, "status": "passed"})

            try:
                self._capture_artifacts(
                    session=session,
                    screenshot_path=screenshot_path,
                    video_path=video_path,
                    console_log_path=console_log_path,
                    network_log_path=network_log_path,
                )
            except Exception as exc:
                artifact_error = str(exc)
        finally:
            self._close_session(session)

        if artifact_error:
            error = "; ".join(part for part in (error, f"artifact_capture_failed: {artifact_error}") if part)

        final_url = _current_url(session) or _resolve_url(entry_url, "/")
        return BrowserJourneyResult(
            phase=phase,
            passed=passed,
            expected_failure_observed=expected_failure_observed,
            final_url=final_url,
            failure_step=failure_step,
            error=error,
            screenshot_path=screenshot_path,
            video_path=video_path,
            console_log_path=console_log_path,
            network_log_path=network_log_path,
            transcript=tuple(transcript),
        )

    def _build_session(
        self,
        *,
        profile: AppRuntimeProfile,
        entry_url: str,
        artifact_root: Path,
        phase: str,
        storage_state_path: str = "",
    ) -> Any:
        if self._session_factory is not None:
            if _session_factory_accepts_storage_state(self._session_factory):
                return self._session_factory(
                    profile,
                    entry_url,
                    artifact_root,
                    phase,
                    storage_state_path=storage_state_path,
                )
            return self._session_factory(profile, entry_url, artifact_root, phase)
        return _PlaywrightBrowserSession(
            profile=profile,
            entry_url=entry_url,
            artifact_root=artifact_root,
            phase=phase,
            storage_state_path=storage_state_path,
        )

    def _run_step(
        self,
        *,
        session: Any,
        step: BrowserStep,
        entry_url: str,
    ) -> None:
        kind = step.kind
        if kind == "goto":
            session.goto(_resolve_url(entry_url, step.subject))
            return
        if kind == "click":
            session.click(step.subject)
            return
        if kind == "fill":
            session.fill(step.subject, step.argument)
            return
        if kind == "press":
            session.press(step.subject)
            return
        if kind == "wait_text":
            session.wait_text(step.subject)
            return
        if kind == "expect_text":
            session.expect_text(step.subject)
            return
        if kind == "fetch":
            method, path = _split_fetch_subject(step.subject)
            payload = step.argument[len("json="):] if step.argument.startswith("json=") else step.argument
            session.fetch(method, path, payload)
            return
        raise ValueError(f"Unsupported browser repro step kind: {kind}")

    def _capture_artifacts(
        self,
        *,
        session: Any,
        screenshot_path: str,
        video_path: str,
        console_log_path: str,
        network_log_path: str,
    ) -> None:
        capture_fn = getattr(session, "capture_artifacts", None)
        if callable(capture_fn):
            capture_fn(
                screenshot_path=screenshot_path,
                video_path=video_path,
                console_log_path=console_log_path,
                network_log_path=network_log_path,
            )
            return
        _write_placeholder_artifact(
            Path(screenshot_path),
            "screenshot artifact placeholder for injected browser session\n",
        )
        _write_placeholder_artifact(
            Path(video_path),
            "video artifact placeholder for injected browser session\n",
        )
        _write_placeholder_artifact(
            Path(console_log_path),
            "console artifact placeholder for injected browser session\n",
        )
        _write_placeholder_artifact(
            Path(network_log_path),
            json.dumps({"events": []}, indent=2) + "\n",
        )

    def _close_session(self, session: Any) -> None:
        close_fn = getattr(session, "close", None)
        if callable(close_fn):
            close_fn()


class _PlaywrightBrowserSession:
    def __init__(
        self,
        *,
        profile: AppRuntimeProfile,
        entry_url: str,
        artifact_root: Path,
        phase: str,
        storage_state_path: str = "",
    ) -> None:
        from playwright.sync_api import sync_playwright

        self._entry_url = str(entry_url or "").strip()
        self._artifact_root = Path(artifact_root)
        self._phase = str(phase or "journey").strip() or "journey"
        self._console_entries: list[str] = []
        self._network_entries: list[dict[str, object]] = []
        self._video_output: Path | None = None

        self._playwright = sync_playwright().start()
        browser_name = str(profile.browser or "chromium").strip().lower()
        launcher = getattr(self._playwright, browser_name, None)
        if launcher is None:
            self._playwright.stop()
            raise ValueError(f"Unsupported Playwright browser '{browser_name}'.")
        self._browser = launcher.launch(headless=bool(profile.headless))
        context_kwargs: dict[str, Any] = {
            "record_video_dir": str((self._artifact_root / self._phase / "video").resolve()),
            "base_url": self._entry_url or None,
        }
        if storage_state_path:
            context_kwargs["storage_state"] = storage_state_path
        context_kwargs = {key: value for key, value in context_kwargs.items() if value is not None}
        device_name = str(profile.device or "").strip()
        if device_name:
            descriptor = self._playwright.devices.get(device_name)
            if descriptor is None:
                self._browser.close()
                self._playwright.stop()
                raise ValueError(f"Unknown Playwright device '{device_name}'.")
            context_kwargs.update(descriptor)
        elif _valid_viewport(profile.viewport):
            context_kwargs["viewport"] = dict(profile.viewport or {})
        else:
            context_kwargs["viewport"] = dict(_DEFAULT_VIEWPORT)

        self._context = self._browser.new_context(**context_kwargs)
        self._page = self._context.new_page()
        self._attach_page_observers(self._page)

    @property
    def current_url(self) -> str:
        return str(self._page.url or self._entry_url or "").strip()

    def goto(self, url: str) -> None:
        self._page.goto(url, wait_until="domcontentloaded")

    def click(self, selector_or_text: str) -> None:
        known_pages = tuple(getattr(self._context, "pages", []) or ())
        self._resolve_locator(selector_or_text).click()
        self._adopt_new_page_if_opened(known_pages=known_pages)
        self._settle_after_click()

    def fill(self, selector: str, value: str) -> None:
        self._resolve_locator(selector).fill(value)

    def press(self, key: str) -> None:
        self._page.keyboard.press(key)

    def wait_text(self, text: str) -> None:
        self._page.get_by_text(text).wait_for(state="visible")

    def expect_text(self, text: str) -> None:
        locator = self._page.get_by_text(text)
        locator.wait_for(state="visible")

    def fetch(self, method: str, path: str, payload: str = "") -> None:
        parsed_payload: object | None = None
        if payload:
            parsed_payload = json.loads(payload)
        result = self._page.evaluate(
            """async ({ url, method, payload }) => {
                const init = { method, headers: {} };
                if (payload !== null && payload !== undefined) {
                    init.headers["Content-Type"] = "application/json";
                    init.body = JSON.stringify(payload);
                }
                const response = await fetch(url, init);
                const text = await response.text();
                return { ok: response.ok, status: response.status, text };
            }""",
            {
                "url": _resolve_url(self._entry_url, path),
                "method": method.upper(),
                "payload": parsed_payload,
            },
        )
        if not bool(result.get("ok")):
            raise AssertionError(
                f"Fetch {method.upper()} {path} failed with status {result.get('status')}: {result.get('text')}"
            )

    def capture_artifacts(
        self,
        *,
        screenshot_path: str,
        video_path: str,
        console_log_path: str,
        network_log_path: str,
    ) -> None:
        screenshot_target = Path(screenshot_path)
        screenshot_target.parent.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=str(screenshot_target), full_page=True)

        console_target = Path(console_log_path)
        console_target.parent.mkdir(parents=True, exist_ok=True)
        console_target.write_text("".join(self._console_entries), encoding="utf-8")

        network_target = Path(network_log_path)
        network_target.parent.mkdir(parents=True, exist_ok=True)
        network_target.write_text(
            "\n".join(json.dumps(entry, sort_keys=True) for entry in self._network_entries) + ("\n" if self._network_entries else ""),
            encoding="utf-8",
        )

        self._video_output = Path(video_path)
        self._video_output.parent.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        video = getattr(self._page, "video", None)
        try:
            self._page.close()
            if self._video_output is not None:
                if video is not None:
                    try:
                        video.save_as(str(self._video_output))
                    except Exception:
                        self._video_output.unlink(missing_ok=True)
            self._context.close()
            self._browser.close()
        finally:
            self._playwright.stop()

    def _resolve_locator(self, selector_or_text: str) -> Any:
        query = str(selector_or_text or "").strip()
        if not query:
            raise ValueError("Browser step selector is empty.")
        if query.startswith("text="):
            return self._page.get_by_text(query[5:])
        if query.startswith("xpath="):
            return self._page.locator(query)
        if query.startswith("//"):
            return self._page.locator(f"xpath={query}")
        if query.startswith("css="):
            return self._page.locator(query[4:])
        return self._page.locator(query)

    def _attach_page_observers(self, page: Any) -> None:
        page.on("console", self._on_console)
        page.on("request", self._on_request)
        page.on("response", self._on_response)

    def _adopt_new_page_if_opened(self, *, known_pages: tuple[Any, ...]) -> None:
        current_pages = tuple(getattr(self._context, "pages", []) or ())
        new_pages = [page for page in current_pages if page not in known_pages]
        if not new_pages:
            return
        new_page = new_pages[-1]
        if new_page is self._page:
            return
        try:
            new_page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        self._page = new_page
        self._attach_page_observers(self._page)

    def _settle_after_click(self) -> None:
        try:
            self._page.wait_for_timeout(_POST_CLICK_SETTLE_MS)
        except Exception:
            return

    def _on_console(self, message: Any) -> None:
        self._console_entries.append(f"[{message.type}] {message.text}\n")

    def _on_request(self, request: Any) -> None:
        self._network_entries.append(
            {
                "event": "request",
                "method": request.method,
                "url": request.url,
            }
        )

    def _on_response(self, response: Any) -> None:
        self._network_entries.append(
            {
                "event": "response",
                "status": response.status,
                "url": response.url,
            }
        )


def parse_repro_steps(repro_steps: tuple[str, ...]) -> tuple[BrowserStep, ...]:
    parsed: list[BrowserStep] = []
    for raw_step in repro_steps:
        line = str(raw_step or "").strip()
        if not line:
            continue
        kind, _, remainder = line.partition(" ")
        normalized_kind = kind.strip().lower().replace("-", "_")
        remainder = remainder.strip()
        if normalized_kind == "fetch":
            subject, _, argument = remainder.partition(" json=")
            parsed.append(
                BrowserStep(
                    kind=normalized_kind,
                    subject=subject.strip(),
                    argument=(f"json={argument.strip()}" if argument.strip() else ""),
                )
            )
            continue
        if normalized_kind == "fill":
            subject, _, argument = remainder.partition("=")
            parsed.append(
                BrowserStep(
                    kind=normalized_kind,
                    subject=subject.strip(),
                    argument=argument.strip(),
                )
            )
            continue
        parsed.append(BrowserStep(kind=normalized_kind, subject=remainder, argument=""))
    return tuple(parsed)


def _coerce_repro_steps(repro_steps: tuple[str | BrowserStep, ...]) -> tuple[BrowserStep, ...]:
    if all(isinstance(step, BrowserStep) for step in repro_steps):
        return tuple(step for step in repro_steps if isinstance(step, BrowserStep))
    raw_steps = tuple(str(step) for step in repro_steps)
    return parse_repro_steps(raw_steps)


def _split_fetch_subject(subject: str) -> tuple[str, str]:
    method, _, path = str(subject or "").partition(" ")
    method = method.strip().upper()
    path = path.strip()
    if not method or not path:
        raise ValueError(f"Invalid fetch step: {subject}")
    return method, path


def _resolve_url(entry_url: str, path_or_url: str) -> str:
    base = str(entry_url or "").strip()
    raw = str(path_or_url or "").strip()
    if not raw:
        return base
    if raw.startswith(("http://", "https://")):
        return raw
    if not base:
        return raw
    base_for_join = base if base.endswith("/") else f"{base}/"
    return urljoin(base_for_join, raw.lstrip("/"))


def _session_factory_accepts_storage_state(factory: Callable[..., Any]) -> bool:
    try:
        parameters = inspect.signature(factory).parameters.values()
    except (TypeError, ValueError):
        return False

    for parameter in parameters:
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            return True
        if parameter.name == "storage_state_path":
            return True
    return False


def _format_step(step: BrowserStep) -> str:
    if step.kind == "fill":
        return f"{step.kind} {step.subject}={step.argument}"
    if step.kind == "fetch":
        suffix = f" {step.argument}" if step.argument else ""
        return f"{step.kind} {step.subject}{suffix}"
    return f"{step.kind} {step.subject}".strip()


def _write_placeholder_artifact(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _current_url(session: Any) -> str:
    return str(getattr(session, "current_url", "") or "").strip()


def _valid_viewport(viewport: Any) -> bool:
    if not isinstance(viewport, dict):
        return False
    width = viewport.get("width")
    height = viewport.get("height")
    return isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0


def assess_browser_evidence_completeness(result: BrowserJourneyResult) -> BrowserEvidenceCompleteness:
    phase = str(result.phase or "").strip().lower() or "journey"
    required = REQUIRED_ARTIFACTS_BY_PHASE.get(phase, ("screenshot_path",))
    present = tuple(name for name in required if _artifact_exists(getattr(result, name, "")))
    missing = tuple(name for name in required if name not in present)
    missing_class = "none"
    if missing:
        has_screenshot_gap = "screenshot_path" in missing
        has_other_gap = any(name != "screenshot_path" for name in missing)
        if has_screenshot_gap and has_other_gap:
            missing_class = "missing_all"
        elif has_screenshot_gap:
            missing_class = "missing_screenshot"
        else:
            missing_class = "missing_logs"
    return BrowserEvidenceCompleteness(
        phase=phase,
        required=required,
        present=present,
        missing=missing,
        complete=not missing,
        missing_class=missing_class,
    )


def classify_browser_failure(result: BrowserJourneyResult) -> str:
    if result.passed:
        return "passed"
    error = str(result.error or "").lower()
    auth_markers = ("login", "auth", "session", "401", "403", "unauthorized")
    if any(marker in error for marker in auth_markers):
        return "fixture_auth_drift"
    return "generic_browser_flake"


def _artifact_exists(path: str) -> bool:
    raw_path = str(path or "").strip()
    if not raw_path:
        return False
    candidate = Path(raw_path)
    try:
        return candidate.exists() and candidate.stat().st_size > 0
    except OSError:
        return False


__all__ = [
    "BrowserEvidenceCompleteness",
    "BrowserJourneyResult",
    "BrowserStep",
    "LocalBrowserHarness",
    "REQUIRED_ARTIFACTS_BY_PHASE",
    "assess_browser_evidence_completeness",
    "classify_browser_failure",
    "parse_repro_steps",
]
