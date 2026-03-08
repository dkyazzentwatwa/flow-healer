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


# Keep the smoke matrix compact so the two expectations stay obvious:
# valid inputs should add cleanly, and invalid inputs should fail cleanly.
ADD_SUCCESS_CASES = (
    pytest.param(2, 3, 5, id="adds_positive_integers"),
    pytest.param(-2, 3, 1, id="adds_negative_and_positive_integers"),
    pytest.param(2, -3, -1, id="adds_positive_and_negative_integers"),
    pytest.param(-2, -3, -5, id="adds_negative_integers"),
    pytest.param(" 2 ", "3", 5, id="adds_integer_strings_with_whitespace"),
    pytest.param(" +2 ", " -3 ", -1, id="adds_signed_integer_strings"),
    pytest.param(True, False, 1, id="adds_boolean_operands"),
    pytest.param(FancyInt(7), 3, 10, id="adds_integer_subclass_operand"),
)

ADD_TYPE_ERROR_CASES = (
    pytest.param("", 1, id="rejects_empty_string_operand"),
    pytest.param("   ", 1, id="rejects_whitespace_only_string_operand"),
    pytest.param("not-a-number", 1, id="rejects_non_numeric_string_operand"),
    pytest.param(1.5, 1, id="rejects_float_operand"),
)

EXPECTED_ADD_SUCCESS_CASE_COUNT = 8
EXPECTED_ADD_TYPE_ERROR_CASE_COUNT = 4


def _call_add(left: object, right: object) -> int:
    return SMOKE_MATH_MODULE.add(left, right)


@pytest.mark.parametrize(("left", "right", "expected"), ADD_SUCCESS_CASES)
def test_add_success_cases_return_expected_sum(
    left: object,
    right: object,
    expected: int,
) -> None:
    """Smoke-check valid operand combinations return the expected total."""
    result = _call_add(left, right)
    assert result == expected, (
        f"expected add({left!r}, {right!r}) to return {expected!r}, "
        f"got {result!r}"
    )


@pytest.mark.parametrize(("left", "right"), ADD_TYPE_ERROR_CASES)
def test_add_type_error_cases_raise_type_error(
    left: object,
    right: object,
) -> None:
    """Smoke-check invalid operands raise a TypeError."""
    with pytest.raises(TypeError):
        _call_add(left, right)


@pytest.mark.parametrize(
    ("cases", "expected_size"),
    (
        pytest.param(
            ADD_SUCCESS_CASES,
            EXPECTED_ADD_SUCCESS_CASE_COUNT,
            id="successful_operands",
        ),
        pytest.param(
            ADD_TYPE_ERROR_CASES,
            EXPECTED_ADD_TYPE_ERROR_CASE_COUNT,
            id="type_error_operands",
        ),
    ),
)
def test_add_case_groups_keep_expected_coverage_shape(
    cases: tuple[object, ...],
    expected_size: int,
) -> None:
    """Keep each smoke coverage group intentionally compact."""
    assert len(cases) == expected_size
