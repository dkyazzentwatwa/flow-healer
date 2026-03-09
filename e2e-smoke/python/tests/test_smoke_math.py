from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest


SMOKE_MATH_PATH = Path(__file__).resolve().parents[1] / "smoke_math.py"


class FancyInt(int):
    """Simple int subclass used to exercise operand normalization."""


class IndexStableInt(int):
    """Exercise exact integer coercion when __int__ disagrees with __index__."""

    def __int__(self) -> int:
        return super().__int__() + 100


class OverflowingInt(int):
    """Exercise exact integer coercion when __int__ raises unexpectedly."""

    def __int__(self) -> int:
        raise OverflowError("lossy int coercion should not be consulted")


class IntLikeButNotIntegral:
    """Mimic numeric coercion hooks without opting into Integral semantics."""

    def __int__(self) -> int:
        return 9


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
    pytest.param(2.5, 3, 6, id="adds_float_using_half_up_rounding"),
    pytest.param(-2.5, 3, 0, id="adds_negative_float_using_half_up_rounding"),
    pytest.param(" 2 ", "3", 5, id="adds_integer_strings_with_whitespace"),
    pytest.param("\u2003+2\u2003", "\u00a03\u00a0", 5, id="adds_integer_strings_with_unicode_whitespace"),
    pytest.param(" +2 ", " -3 ", -1, id="adds_signed_integer_strings"),
    pytest.param("١٢", "３", 15, id="adds_unicode_decimal_digit_strings"),
    pytest.param(True, False, 1, id="adds_boolean_operands"),
    pytest.param(FancyInt(7), 3, 10, id="adds_integer_subclass_operand"),
    pytest.param(IndexStableInt(4), -1, 3, id="uses_exact_index_for_int_subclass"),
    pytest.param(OverflowingInt(6), "-2", 4, id="ignores_overflowing_int_hook"),
    pytest.param("1_000", "2_000", 3000, id="adds_underscored_integer_strings"),
)

ADD_TYPE_ERROR_CASES = (
    pytest.param("", 1, id="rejects_empty_string_operand"),
    pytest.param("   ", 1, id="rejects_whitespace_only_string_operand"),
    pytest.param("not-a-number", 1, id="rejects_non_numeric_string_operand"),
    pytest.param(float("inf"), 1, id="rejects_infinite_float_operand"),
)

EXPECTED_ADD_SUCCESS_CASE_COUNT = 15
EXPECTED_ADD_TYPE_ERROR_CASE_COUNT = 4


def _call_add(left: object, right: object) -> int:
    return SMOKE_MATH_MODULE.add(left, right)


def _normalize_operand(value: object) -> int:
    return SMOKE_MATH_MODULE._normalize_operand(value)


def _coerce_operands(left: object, right: object) -> tuple[int, int]:
    return SMOKE_MATH_MODULE._coerce_operands(left, right)


def _add_normalized_operands(left: int, right: int) -> int:
    return SMOKE_MATH_MODULE._add_normalized_operands(left, right)


def _add_three_normalized_operands(first: int, second: int, third: int) -> int:
    return SMOKE_MATH_MODULE._add_three_normalized_operands(first, second, third)


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
    ("left", "right"),
    (
        pytest.param("1.0", 1, id="rejects_decimal_string_operand"),
        pytest.param("1__0", 1, id="rejects_double_underscore_integer_string_operand"),
        pytest.param("_1_000", 1, id="rejects_leading_underscore_integer_string_operand"),
        pytest.param("1_000_", 1, id="rejects_trailing_underscore_integer_string_operand"),
        pytest.param(b"2", 1, id="rejects_bytes_operand"),
        pytest.param(object(), 1, id="rejects_object_operand"),
        pytest.param(
            IntLikeButNotIntegral(),
            1,
            id="rejects_int_like_non_integral_operand",
        ),
        pytest.param("1\x00", 1, id="rejects_embedded_nul_in_string_operand"),
    ),
)
def test_add_invalid_operands_keep_stable_type_error_message(
    left: object,
    right: object,
) -> None:
    """Invalid operands should preserve the public exception contract."""
    with pytest.raises(TypeError) as exc_info:
        _call_add(left, right)

    assert str(exc_info.value) == SMOKE_MATH_MODULE.ERROR_MESSAGE


def test_add_oversized_integer_string_raises_type_error_with_stable_message() -> None:
    """Digit-limit failures should stay mapped onto the public TypeError."""
    limit = sys.get_int_max_str_digits()
    if limit == 0:
        pytest.skip("digit limit disabled in this interpreter")

    oversized_operand = "9" * (limit + 1)

    with pytest.raises(TypeError) as exc_info:
        _call_add(oversized_operand, 1)

    assert str(exc_info.value) == SMOKE_MATH_MODULE.ERROR_MESSAGE


@pytest.mark.parametrize(
    ("left", "right"),
    (
        pytest.param(0, 5, id="zero_left_identity_for_positive_int"),
        pytest.param(-7, 0, id="zero_right_identity_for_negative_int"),
        pytest.param("0", "12", id="zero_string_identity_for_positive_string"),
        pytest.param(" -9 ", " 0 ", id="zero_string_identity_for_negative_string"),
        pytest.param(" +0 ", FancyInt(-4), id="signed_zero_left_identity"),
        pytest.param(True, "-0", id="signed_zero_right_identity"),
    ),
)
def test_add_preserves_additive_identity(left: object, right: object) -> None:
    """Adding zero should preserve the other operand's normalized value."""
    left_value = _normalize_operand(left)
    right_value = _normalize_operand(right)
    result = _call_add(left, right)

    if left_value == 0:
        assert result == right_value
    else:
        assert result == left_value
    assert type(result) is int


@pytest.mark.parametrize(
    ("left", "right"),
    (
        pytest.param(-4, 4, id="int_operands_cancel_across_signs"),
        pytest.param(4, -4, id="int_operands_cancel_across_signs_reversed"),
        pytest.param(" +15 ", "-15", id="string_operands_cancel_across_signs"),
        pytest.param("-15", " +15 ", id="string_operands_cancel_across_signs_reversed"),
        pytest.param(FancyInt(-2), True, id="normalized_operands_keep_sign"),
    ),
)
def test_add_preserves_sign_when_operands_cross_zero(
    left: object,
    right: object,
) -> None:
    """Opposite signed inputs should keep the true arithmetic result."""
    expected = _normalize_operand(left) + _normalize_operand(right)
    assert _call_add(left, right) == expected


@pytest.mark.parametrize(
    ("left", "right"),
    (
        pytest.param("-0", "-0", id="negative_zero_strings_cancel_to_zero"),
        pytest.param(" +0 ", "-0", id="mixed_signed_zero_strings_cancel_to_zero"),
        pytest.param("-5", "5", id="signed_strings_cancel_to_additive_identity"),
        pytest.param(FancyInt(-11), "11", id="integral_and_string_cancel_to_zero"),
    ),
)
def test_add_canonicalizes_zero_when_signed_inputs_cancel(
    left: object,
    right: object,
) -> None:
    """Cancellation should always land on the plain additive identity."""
    result = _call_add(left, right)
    assert result == 0
    assert type(result) is int


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    (
        pytest.param(
            10**80,
            -(10**80) + 1,
            1,
            id="large_positive_and_negative_operands_keep_positive_edge",
        ),
        pytest.param(
            -(10**80),
            (10**80) - 1,
            -1,
            id="large_negative_and_positive_operands_keep_negative_edge",
        ),
        pytest.param(
            f"+{10**80}",
            str(-(10**80)),
            0,
            id="large_string_operands_cancel_to_canonical_zero",
        ),
    ),
)
def test_add_matches_python_int_arithmetic_for_large_mixed_sign_operands(
    left: object,
    right: object,
    expected: int,
) -> None:
    """Mixed-sign edge cases should keep Python int arithmetic semantics."""
    result = _call_add(left, right)
    assert result == expected
    assert result == _normalize_operand(left) + _normalize_operand(right)
    assert type(result) is int


@pytest.mark.parametrize(
    ("left", "right"),
    (
        pytest.param(-23, 23, id="ints_cancel_directly"),
        pytest.param(23, -23, id="ints_cancel_directly_reversed"),
        pytest.param(-1, 1, id="unit_values_cancel_directly"),
    ),
)
def test_add_normalized_operands_short_circuits_cancelled_pairs(
    left: int,
    right: int,
) -> None:
    """Already-normalized opposite values should resolve to canonical zero."""
    result = _add_normalized_operands(left, right)
    assert result == 0
    assert type(result) is int


def test_coerce_operands_normalizes_string_and_numeric_inputs_together() -> None:
    """Shared operand coercion should return plain ints before addition."""
    assert _coerce_operands(" +8 ", FancyInt(-3)) == (8, -3)


def test_coerce_operands_normalizes_bool_before_integral_fallback() -> None:
    """Bool operands should stay explicitly supported through shared coercion."""
    assert _coerce_operands(True, " 2 ") == (1, 2)


def test_coerce_operands_prefers_exact_index_over_custom_int_rounding() -> None:
    """Integral normalization should preserve exact integer semantics."""
    assert _coerce_operands(IndexStableInt(-4), " 1 ") == (-4, 1)


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        pytest.param(2.5, 3, id="rounds_positive_half_up"),
        pytest.param(-2.5, -3, id="rounds_negative_half_up"),
        pytest.param(2.49, 2, id="rounds_positive_fraction_down"),
        pytest.param(-2.49, -2, id="rounds_negative_fraction_toward_zero"),
        pytest.param(1.005, 1, id="uses_decimal_string_coercion_for_stable_rounding"),
        pytest.param(1e100, 10**100, id="handles_large_float_scientific_notation"),
    ),
)
def test_normalize_operand_rounds_float_inputs_deterministically(
    value: float,
    expected: int,
) -> None:
    """Float operands should round predictably before addition."""
    assert _normalize_operand(value) == expected


def test_coerce_operands_ignores_overflowing_int_hook_for_integral_subclass() -> None:
    """Integral normalization should not fail because __int__ is unstable."""
    assert _coerce_operands(OverflowingInt(8), "-3") == (8, -3)


def test_add3_preserves_identity_across_signed_inputs() -> None:
    """Composed additions should keep the same identity guarantees."""
    assert SMOKE_MATH_MODULE.add3(" +0 ", FancyInt(-6), " 0 ") == -6


def test_add3_keeps_cancellation_and_identity_stable() -> None:
    """Composed additions should preserve zero after opposite signed sums cancel."""
    result = SMOKE_MATH_MODULE.add3("-8", "8", "-0")
    assert result == 0
    assert type(result) is int


def test_add3_keeps_signed_identity_for_non_zero_result() -> None:
    """Composed additions should preserve sign when only the final term is zero."""
    result = SMOKE_MATH_MODULE.add3("-5", "2", "0")
    assert result == -3
    assert type(result) is int


def test_add3_preserves_additive_identity_after_signed_zero_cancellation() -> None:
    """A signed-zero partial sum should remain a true identity for the final term."""
    result = SMOKE_MATH_MODULE.add3("-0", " +0 ", FancyInt(9))
    assert result == 9
    assert type(result) is int


def test_add_normalized_operands_promotes_exact_int_subclass_without_int_hook() -> None:
    """Zero fast paths should preserve exact integer coercion semantics."""
    result = _add_normalized_operands(0, OverflowingInt(9))
    assert result == 9
    assert type(result) is int


@pytest.mark.parametrize(
    ("first", "second", "third", "expected"),
    (
        pytest.param(
            10**80,
            -(10**80),
            1,
            1,
            id="large_opposites_cancel_before_positive_edge_term",
        ),
        pytest.param(
            -(10**80),
            10**80,
            -1,
            -1,
            id="large_opposites_cancel_before_negative_edge_term",
        ),
        pytest.param(
            f"+{10**80}",
            str(-(10**80) + 1),
            "-1",
            0,
            id="large_string_operands_cross_zero_then_canonicalize",
        ),
        pytest.param(
            10**80,
            str(-(10**80) + 1),
            "-2",
            -1,
            id="large_partial_sum_crosses_zero_on_final_negative_term",
        ),
        pytest.param(
            -(10**80),
            str((10**80) - 1),
            "2",
            1,
            id="large_partial_sum_crosses_zero_on_final_positive_term",
        ),
    ),
)
def test_add3_matches_python_int_arithmetic_for_large_mixed_sign_operands(
    first: object,
    second: object,
    third: object,
    expected: int,
) -> None:
    """Three-term mixed-sign arithmetic should stay aligned with Python ints."""
    result = SMOKE_MATH_MODULE.add3(first, second, third)
    assert result == expected
    assert result == (
        _normalize_operand(first)
        + _normalize_operand(second)
        + _normalize_operand(third)
    )
    assert type(result) is int


def test_add_three_normalized_operands_canonicalizes_zero_after_partial_cancellation() -> None:
    """A zero-valued partial sum should remain a true identity for the final term."""
    result = _add_three_normalized_operands(-(10**80), 10**80, 7)
    assert result == 7
    assert type(result) is int


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
