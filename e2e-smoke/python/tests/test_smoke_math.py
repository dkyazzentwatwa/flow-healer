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


VALID_ADD_CASES = (
    pytest.param(2, 3, 5, id="adds_two_positive_numbers"),
    pytest.param(-2, 3, 1, id="adds_negative_and_positive_numbers"),
    pytest.param(2, -3, -1, id="adds_positive_and_negative_numbers"),
    pytest.param(-2, -3, -5, id="adds_two_negative_numbers"),
    pytest.param(" 2 ", "3", 5, id="adds_integer_strings_with_whitespace"),
    pytest.param(" +2 ", " -3 ", -1, id="adds_signed_integer_strings"),
    pytest.param(True, False, 1, id="adds_boolean_operands_as_integers"),
    pytest.param(FancyInt(7), 3, 10, id="adds_integral_subclass_operands"),
)

INVALID_ADD_CASES = (
    pytest.param("", 1, id="rejects_empty_string_operand"),
    pytest.param("   ", 1, id="rejects_whitespace_only_string_operand"),
    pytest.param("not-a-number", 1, id="rejects_non_numeric_string_operand"),
    pytest.param(1.5, 1, id="rejects_float_operand"),
)


def _invoke_add(left: object, right: object) -> int:
    return SMOKE_MATH_MODULE.add(left, right)


@pytest.mark.parametrize(("left", "right", "expected_sum"), VALID_ADD_CASES)
def test_add_matches_expected_sum_for_supported_integer_like_operands(
    left: object,
    right: object,
    expected_sum: int,
) -> None:
    actual_sum = _invoke_add(left, right)
    assert actual_sum == expected_sum, (
        f"expected add({left!r}, {right!r}) to return {expected_sum!r}, "
        f"got {actual_sum!r}"
    )


@pytest.mark.parametrize(("invalid_left", "invalid_right"), INVALID_ADD_CASES)
def test_add_rejects_unsupported_operands_with_type_error(
    invalid_left: object,
    invalid_right: object,
) -> None:
    unsupported_operands = (invalid_left, invalid_right)
    with pytest.raises(TypeError):
        _invoke_add(*unsupported_operands)
