from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest


SMOKE_MATH_PATH = Path(__file__).resolve().parents[1] / "smoke_math.py"


class FancyInt(int):
    """Simple int subclass used to exercise operand normalization."""


def _load_smoke_math_module() -> ModuleType:
    spec = spec_from_file_location("smoke_math", SMOKE_MATH_PATH)
    assert spec is not None and spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SMOKE_MATH_MODULE = _load_smoke_math_module()


# Supported inputs should keep the smoke suite readable at a glance.
ADD_VALID_OPERANDS = (
    pytest.param(2, 3, 5, id="positive_ints"),
    pytest.param(-2, 3, 1, id="negative_plus_positive"),
    pytest.param(2, -3, -1, id="positive_plus_negative"),
    pytest.param(-2, -3, -5, id="negative_ints"),
    pytest.param(" 2 ", "3", 5, id="string_ints_with_whitespace"),
    pytest.param(" +2 ", " -3 ", -1, id="signed_string_ints"),
    pytest.param(True, False, 1, id="bool_operands"),
    pytest.param(FancyInt(7), 3, 10, id="int_subclass_operand"),
)

ADD_INVALID_OPERANDS = (
    pytest.param("", 1, id="empty_string"),
    pytest.param("   ", 1, id="whitespace_only_string"),
    pytest.param("not-a-number", 1, id="non_numeric_string"),
    pytest.param(1.5, 1, id="float_operand"),
)

EXPECTED_VALID_CASE_COUNT = 8
EXPECTED_INVALID_CASE_COUNT = 4


def _call_add(left: object, right: object) -> int:
    return SMOKE_MATH_MODULE.add(left, right)


def _assert_case_group_size(cases: tuple[object, ...], expected_size: int) -> None:
    assert len(cases) == expected_size


@pytest.mark.parametrize(("left", "right", "expected"), ADD_VALID_OPERANDS)
def test_add_returns_expected_sum(
    left: object,
    right: object,
    expected: int,
) -> None:
    """Smoke-check supported operand combinations return the expected total."""
    result = _call_add(left, right)
    assert result == expected, (
        f"expected add({left!r}, {right!r}) to return {expected!r}, "
        f"got {result!r}"
    )


@pytest.mark.parametrize(("left", "right"), ADD_INVALID_OPERANDS)
def test_add_rejects_invalid_operands(
    left: object,
    right: object,
) -> None:
    """Smoke-check unsupported operands raise a TypeError."""
    with pytest.raises(TypeError):
        _call_add(left, right)


def test_add_case_groups_cover_expected_smoke_scenarios() -> None:
    """Keep the smoke suite split between valid and invalid operand groups."""
    _assert_case_group_size(ADD_VALID_OPERANDS, EXPECTED_VALID_CASE_COUNT)
    _assert_case_group_size(ADD_INVALID_OPERANDS, EXPECTED_INVALID_CASE_COUNT)
