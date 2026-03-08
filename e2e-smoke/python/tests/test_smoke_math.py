from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


def _load_smoke_math_module():
    module_path = Path(__file__).resolve().parents[1] / "smoke_math.py"
    spec = spec_from_file_location("smoke_math", module_path)
    assert spec is not None and spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SMOKE_MATH_MODULE = _load_smoke_math_module()
ADDITION_CASES = [
    pytest.param(2, 3, 5, id="two_positive_numbers"),
    pytest.param(-2, 3, 1, id="negative_plus_positive"),
    pytest.param(2, -3, -1, id="positive_plus_negative"),
    pytest.param(-2, -3, -5, id="two_negative_numbers"),
]


@pytest.mark.parametrize(("left", "right", "expected_sum"), ADDITION_CASES)
def test_add_returns_expected_sum(
    left: int, right: int, expected_sum: int
) -> None:
    assert SMOKE_MATH_MODULE.add(left, right) == expected_sum
