from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_api_module():
    module_path = Path(__file__).resolve().parents[1] / "app" / "api.py"
    spec = spec_from_file_location("app.api", module_path)
    assert spec is not None and spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


api = _load_api_module()


def test_health_returns_exact_contract() -> None:
    assert api.health() == {"status": "ok"}


def test_health_route_is_registered_at_expected_path() -> None:
    route = next(route for route in api.app.routes if route.path == "/health")
    assert route.endpoint() == {"status": "ok"}
