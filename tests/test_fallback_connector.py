from __future__ import annotations

from dataclasses import dataclass

from flow_healer.fallback_connector import FailoverConnector


@dataclass
class _FakeConnector:
    output: str
    available: bool = True
    calls: int = 0

    def ensure_started(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def get_or_create_thread(self, sender: str) -> str:
        return sender

    def reset_thread(self, sender: str) -> str:
        return sender

    def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
        del thread_id, prompt, timeout_seconds
        self.calls += 1
        return self.output

    def health_snapshot(self) -> dict[str, str | bool]:
        return {
            "available": self.available,
            "configured_command": "fake",
            "resolved_command": "fake",
            "availability_reason": "",
            "last_health_error": "",
        }


def test_failover_connector_uses_primary_when_successful() -> None:
    primary = _FakeConnector(output="ok")
    fallback = _FakeConnector(output="fallback ok")
    connector = FailoverConnector(
        primary_backend="cline",
        primary=primary,
        fallback_backend="exec",
        fallback=fallback,
    )

    output = connector.run_turn("thread", "prompt")

    assert output == "ok"
    assert primary.calls == 1
    assert fallback.calls == 0
    health = connector.health_snapshot()
    assert health["fallback_attempts"] == 0
    assert health["fallback_successes"] == 0


def test_failover_connector_falls_back_on_runtime_error() -> None:
    primary = _FakeConnector(output="ConnectorRuntimeError: primary boom")
    fallback = _FakeConnector(output="fallback ok")
    connector = FailoverConnector(
        primary_backend="kilo_cli",
        primary=primary,
        fallback_backend="exec",
        fallback=fallback,
    )

    output = connector.run_turn("thread", "prompt")

    assert output == "fallback ok"
    assert primary.calls == 1
    assert fallback.calls == 1
    health = connector.health_snapshot()
    assert health["fallback_attempts"] == 1
    assert health["fallback_successes"] == 1
    assert str(health["last_fallback_reason"]).startswith("ConnectorRuntimeError:")
