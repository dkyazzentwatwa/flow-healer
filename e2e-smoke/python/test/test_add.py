from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import re
import sys
from types import ModuleType

import pytest


ADD_PATH = Path(__file__).resolve().parents[1] / "flow_healer_add.py"


class FancyInt(int):
    """Simple int subclass used to exercise operand normalization."""


class BrokenInt(int):
    """Int subclass whose conversion path fails unexpectedly."""

    def __int__(self) -> int:
        raise OverflowError("cannot normalize")


class TrickyString(str):
    """String subclass that overrides helpers the normalizer should ignore."""

    def __str__(self) -> str:
        return "not-a-number"

    def strip(self, chars: str | None = None) -> str:
        raise AssertionError("strip override should not be used")


def _load_add_module() -> ModuleType:
    spec = spec_from_file_location("flow_healer_add", ADD_PATH)
    assert spec is not None and spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


add_module = _load_add_module()


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    (
        pytest.param(2, 3, 5, id="adds_two_positive_numbers"),
        pytest.param(-2, 3, 1, id="adds_negative_and_positive_numbers"),
        pytest.param(2, -3, -1, id="adds_positive_and_negative_numbers"),
        pytest.param(-2, -3, -5, id="adds_two_negative_numbers"),
        pytest.param(" 2 ", "3", 5, id="adds_integer_strings_with_whitespace"),
        pytest.param(" +2 ", " -3 ", -1, id="adds_signed_integer_strings"),
        pytest.param("\n2\t", "3", 5, id="adds_integer_strings_with_control_whitespace"),
        pytest.param(True, False, 1, id="adds_boolean_operands_as_integers"),
        pytest.param(FancyInt(7), 3, 10, id="adds_integral_subclass_operands"),
    ),
)
def test_add_returns_expected_sum(left: object, right: object, expected: int) -> None:
    assert add_module.add(left, right) == expected


@pytest.mark.parametrize(
    ("left", "right"),
    (
        pytest.param("", 1, id="rejects_empty_string_operand"),
        pytest.param("   ", 1, id="rejects_whitespace_only_string_operand"),
        pytest.param("not-a-number", 1, id="rejects_non_numeric_string_operand"),
        pytest.param(1.5, 1, id="rejects_float_operand"),
    ),
)
def test_add_rejects_invalid_operands(left: object, right: object) -> None:
    with pytest.raises(TypeError, match="integers or integer strings"):
        add_module.add(left, right)


@pytest.mark.parametrize(
    ("left", "right"),
    (
        pytest.param("1_000", 1, id="rejects_underscored_numeric_string_operand"),
        pytest.param("1 0", 1, id="rejects_internal_whitespace_in_numeric_string_operand"),
        pytest.param("1\x00", 1, id="rejects_null_terminated_numeric_string_operand"),
        pytest.param("\u00a02", 1, id="rejects_non_ascii_leading_whitespace"),
        pytest.param("2\u2003", 1, id="rejects_non_ascii_trailing_whitespace"),
        pytest.param("٣", 1, id="rejects_unicode_numeric_string_operand"),
        pytest.param("1.0", 1, id="rejects_decimal_string_operand"),
    ),
)
def test_add_rejects_unsafe_integer_string_formats(left: object, right: object) -> None:
    with pytest.raises(TypeError, match=re.escape(add_module.ERROR_MESSAGE)):
        add_module.add(left, right)


def test_add_rejects_oversized_integer_string_operands() -> None:
    oversized_value = "9" * 5000

    with pytest.raises(TypeError, match=re.escape(add_module.ERROR_MESSAGE)):
        add_module.add(oversized_value, 1)


def test_add_rejects_signed_oversized_integer_string_operands() -> None:
    oversized_value = "+" + ("9" * (sys.get_int_max_str_digits() + 1))

    with pytest.raises(TypeError, match=re.escape(add_module.ERROR_MESSAGE)):
        add_module.add(oversized_value, 1)


def test_add_allows_large_integer_strings_when_digit_limit_is_disabled() -> None:
    original_limit = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    try:
        assert add_module.add("9" * 5000, 1) == int("9" * 5000) + 1
    finally:
        sys.set_int_max_str_digits(original_limit)


def test_normalize_operand_uses_shared_error_message() -> None:
    with pytest.raises(TypeError, match=re.escape(add_module.ERROR_MESSAGE)):
        add_module.normalize_operand("nope")


def test_normalize_operand_returns_plain_int_for_integral_subclasses() -> None:
    normalized = add_module.normalize_operand(FancyInt(9))

    assert normalized == 9
    assert type(normalized) is int


def test_normalize_operand_rewraps_integral_conversion_failures() -> None:
    with pytest.raises(TypeError, match=re.escape(add_module.ERROR_MESSAGE)):
        add_module.normalize_operand(BrokenInt(4))


def test_normalize_integral_operand_returns_plain_int() -> None:
    normalized = add_module._normalize_integral_operand(FancyInt(5))

    assert normalized == 5
    assert type(normalized) is int


def test_normalize_operand_trims_outer_whitespace_before_parsing() -> None:
    assert add_module.normalize_operand(" \n+12\t ") == 12


def test_normalize_operand_uses_plain_string_value_for_string_subclasses() -> None:
    assert add_module.normalize_operand(TrickyString(" \n+12\t ")) == 12


@pytest.mark.parametrize(
    "value",
    (
        pytest.param(None, id="rejects_none_operand"),
        pytest.param(b"4", id="rejects_bytes_operand"),
    ),
)
def test_normalize_operand_rejects_non_string_non_integral_inputs(value: object) -> None:
    with pytest.raises(TypeError, match=re.escape(add_module.ERROR_MESSAGE)):
        add_module.normalize_operand(value)
