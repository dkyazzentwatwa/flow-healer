from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_smoke_math():
    module_path = Path(__file__).resolve().parents[1] / "smoke_math.py"
    spec = spec_from_file_location("smoke_math", module_path)
    assert spec is not None and spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke_math = _load_smoke_math()


def test_add_returns_sum() -> None:
    assert smoke_math.add(2, 3) == 5


def test_add_handles_larger_integers() -> None:
    left = 10**18
    right = 10**18 + 7

    assert smoke_math.add(left, right) == 2 * 10**18 + 7
