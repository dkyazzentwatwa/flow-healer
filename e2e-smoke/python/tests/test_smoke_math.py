from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


def _load_smoke_math():
    module_path = Path(__file__).resolve().parents[1] / "smoke_math.py"
    spec = spec_from_file_location("smoke_math", module_path)
    assert spec is not None and spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke_math = _load_smoke_math()


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        pytest.param(2, 3, 5, id="adds_two_positive_numbers"),
        pytest.param(-2, 3, 1, id="adds_negative_and_positive_numbers"),
        pytest.param(2, -3, -1, id="adds_positive_and_negative_numbers"),
        pytest.param(-2, -3, -5, id="adds_two_negative_numbers"),
    ],
)
def test_add_returns_sum(left: int, right: int, expected: int) -> None:
    assert smoke_math.add(left, right) == expected
