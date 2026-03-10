from __future__ import annotations

from pathlib import Path

from flow_healer.healer_preflight import HealerPreflight
from flow_healer.store import SQLiteStore


class _Runner:
    test_gate_mode = "local_only"


class _Connector:
    def ensure_started(self) -> None:
        pass

    def health_snapshot(self) -> dict[str, object]:
        return {
            "available": False,
            "availability_reason": "connector boot failed",
        }


def test_probe_connector_respects_available_false_snapshot(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    store.bootstrap()
    preflight = HealerPreflight(
        store=store,
        runner=_Runner(),  # type: ignore[arg-type]
        repo_path=tmp_path,
    )

    ok, reason = preflight.probe_connector(_Connector())  # type: ignore[arg-type]

    assert ok is False
    assert reason == "connector boot failed"
