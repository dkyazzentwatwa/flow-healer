from __future__ import annotations

import threading
from typing import Any

from .protocols import ConnectorProtocol


_FALLBACK_TRIGGER_PREFIXES = ("ConnectorUnavailable:", "ConnectorRuntimeError:")


class FailoverConnector:
    """Primary connector wrapper that falls back to a secondary connector."""

    def __init__(
        self,
        *,
        primary_backend: str,
        primary: ConnectorProtocol,
        fallback_backend: str,
        fallback: ConnectorProtocol,
    ) -> None:
        self.primary_backend = str(primary_backend or "primary")
        self.fallback_backend = str(fallback_backend or "fallback")
        self.primary = primary
        self.fallback = fallback
        self._lock = threading.Lock()
        self._fallback_attempts = 0
        self._fallback_successes = 0
        self._last_fallback_reason = ""

    def ensure_started(self) -> None:
        try:
            self.primary.ensure_started()
        except Exception as exc:
            with self._lock:
                self._last_fallback_reason = f"primary ensure_started failed: {exc}"
        try:
            self.fallback.ensure_started()
        except Exception:
            return

    def shutdown(self) -> None:
        errors: list[str] = []
        for connector in (self.primary, self.fallback):
            try:
                connector.shutdown()
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError("; ".join(errors))

    def get_or_create_thread(self, sender: str) -> str:
        thread_id = sender
        try:
            thread_id = self.primary.get_or_create_thread(sender)
        except Exception:
            thread_id = sender
        try:
            self.fallback.get_or_create_thread(sender)
        except Exception:
            pass
        return thread_id

    def reset_thread(self, sender: str) -> str:
        thread_id = sender
        try:
            thread_id = self.primary.reset_thread(sender)
        except Exception:
            thread_id = sender
        try:
            self.fallback.reset_thread(sender)
        except Exception:
            pass
        return thread_id

    def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
        primary_output = self.primary.run_turn(thread_id, prompt, timeout_seconds=timeout_seconds)
        if not _is_fallback_trigger(primary_output):
            return primary_output

        with self._lock:
            self._fallback_attempts += 1
            self._last_fallback_reason = str(primary_output or "")[:500]
        fallback_output = self.fallback.run_turn(thread_id, prompt, timeout_seconds=timeout_seconds)
        if not _is_fallback_trigger(fallback_output):
            with self._lock:
                self._fallback_successes += 1
            return fallback_output
        return fallback_output

    def health_snapshot(self) -> dict[str, Any]:
        primary_health = _safe_health_snapshot(self.primary)
        fallback_health = _safe_health_snapshot(self.fallback)
        with self._lock:
            attempts = self._fallback_attempts
            successes = self._fallback_successes
            reason = self._last_fallback_reason
        primary_available = bool(primary_health.get("available"))
        fallback_available = bool(fallback_health.get("available"))
        return {
            "available": primary_available or fallback_available,
            "configured_command": str(primary_health.get("configured_command") or ""),
            "resolved_command": str(primary_health.get("resolved_command") or ""),
            "availability_reason": str(primary_health.get("availability_reason") or ""),
            "last_health_error": str(primary_health.get("last_health_error") or ""),
            "fallback_backend": self.fallback_backend,
            "fallback_available": fallback_available,
            "fallback_attempts": attempts,
            "fallback_successes": successes,
            "last_fallback_reason": reason,
        }


def _is_fallback_trigger(output: str) -> bool:
    text = str(output or "")
    return text.startswith(_FALLBACK_TRIGGER_PREFIXES)


def _safe_health_snapshot(connector: ConnectorProtocol) -> dict[str, Any]:
    if hasattr(connector, "health_snapshot"):
        try:
            health = connector.health_snapshot()  # type: ignore[attr-defined]
            return health if isinstance(health, dict) else {}
        except Exception:
            return {}
    return {}
