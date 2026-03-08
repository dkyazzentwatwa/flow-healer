"""Focused addition helper exercised by the Python smoke tests."""

import operator
import re
import sys
from numbers import Integral


ERROR_MESSAGE = "add() operands must be integers or integer strings"
_INTEGER_STRING_PATTERN = re.compile(r"[+-]?[0-9]+")
_ASCII_WHITESPACE = " \t\n\r\v\f"


def _operand_type_error(*, cause: Exception | None = None) -> TypeError:
    """Build the stable operand TypeError used by the smoke sandbox."""
    error = TypeError(ERROR_MESSAGE)
    if cause is not None:
        error.__cause__ = cause
    return error


def _fits_python_integer_string_limit(value: str) -> bool:
    """Mirror the interpreter's integer-string digit guardrail."""
    limit = sys.get_int_max_str_digits()
    if limit == 0:
        return True

    unsigned_value = value.removeprefix("+").removeprefix("-")
    return len(unsigned_value) <= limit


def _normalize_string_operand(value: str) -> int:
    """Parse a supported integer string operand into a plain int."""
    normalized_value = _strip_ascii_whitespace(value)
    if not normalized_value or "\x00" in normalized_value:
        raise _operand_type_error()

    if not _INTEGER_STRING_PATTERN.fullmatch(normalized_value):
        raise _operand_type_error()

    if not _fits_python_integer_string_limit(normalized_value):
        raise _operand_type_error()

    try:
        return int(normalized_value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _operand_type_error(cause=exc)


def _normalize_integral_operand(value: Integral) -> int:
    """Coerce exact integer operands without consulting lossy __int__ hooks."""
    try:
        return operator.index(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _operand_type_error(cause=exc)


def _normalize_bool_operand(value: bool) -> int:
    """Keep bool acceptance explicit even though bool is also an Integral."""
    return int(value)


def _strip_ascii_whitespace(value: str) -> str:
    """Trim ASCII whitespace without altering non-string operand handling."""
    return value.strip(_ASCII_WHITESPACE)


def _normalize_operand(value: int | str) -> int:
    """Return a plain integer for supported smoke-test operands."""
    if isinstance(value, bool):
        return _normalize_bool_operand(value)

    if isinstance(value, Integral):
        return _normalize_integral_operand(value)

    if isinstance(value, str):
        return _normalize_string_operand(value)

    raise _operand_type_error()


def _coerce_operands(left: int | str, right: int | str) -> tuple[int, int]:
    """Normalize both operands before addition so coercion stays explicit."""
    return _normalize_operand(left), _normalize_operand(right)


def _canonicalize_zero(value: int) -> int:
    """Collapse any computed zero onto the additive identity singleton."""
    if value == 0:
        return 0
    if type(value) is int:
        return value
    return operator.index(value)


def _is_additive_identity(value: int) -> bool:
    """Return whether a normalized operand is the additive identity."""
    return value == 0


def _add_normalized_operands(left: int, right: int) -> int:
    """Add normalized ints while preserving zero identity and sign semantics."""
    if _is_additive_identity(left):
        return _canonicalize_zero(right)
    if _is_additive_identity(right):
        return _canonicalize_zero(left)
    return _canonicalize_zero(left + right)


def add(left: int | str, right: int | str) -> int:
    """Return the sum of two supported operands as an integer."""
    normalized_left, normalized_right = _coerce_operands(left, right)
    return _add_normalized_operands(normalized_left, normalized_right)


def add3(first: int | str, second: int | str, third: int | str) -> int:
    """Compose two additions so identity and sign handling stay consistent."""
    partial_sum = add(first, second)
    return add(partial_sum, third)
