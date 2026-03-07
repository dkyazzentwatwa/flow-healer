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


def test_add_handles_zero_inputs() -> None:
    assert smoke_math.add(0, 0) == 0
    assert smoke_math.add(0, 7) == 7
    assert smoke_math.add(9, 0) == 9
