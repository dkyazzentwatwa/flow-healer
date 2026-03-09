"""Focused addition helper exercised by the Python smoke tests."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math
import operator
import sys
from numbers import Integral


ERROR_MESSAGE = "add() operands must be integers or integer strings"


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
    unsigned_digits = unsigned_value.replace("_", "")
    return len(unsigned_digits) <= limit


def _normalize_string_operand(value: str) -> int:
    """Parse a supported integer string operand into a plain int."""
    normalized_value = _strip_ascii_whitespace(value)
    if not normalized_value or "\x00" in normalized_value:
        raise _operand_type_error()

    if not _is_supported_integer_string(normalized_value):
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


def _normalize_float_operand(value: float) -> int:
    """Round finite float operands with deterministic half-up semantics."""
    if not math.isfinite(value):
        raise _operand_type_error()

    try:
        rounded_value = Decimal(str(value)).to_integral_value(
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, ValueError) as exc:
        raise _operand_type_error(cause=exc)

    try:
        return int(rounded_value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _operand_type_error(cause=exc)


def _strip_ascii_whitespace(value: str) -> str:
    """Trim the same leading and trailing whitespace that int() accepts."""
    return value.strip()


def _is_supported_integer_string(value: str) -> bool:
    """Accept signed decimal digit strings that Python itself can parse as ints."""
    unsigned_value = value.removeprefix("+").removeprefix("-")
    if not unsigned_value:
        return False

    if "_" in unsigned_value:
        if (
            unsigned_value.startswith("_")
            or unsigned_value.endswith("_")
            or "_" * 2 in unsigned_value
        ):
            return False
        return all(part.isdecimal() for part in unsigned_value.split("_"))

    return all(character.isdecimal() for character in unsigned_value)


def _normalize_operand(value: int | str) -> int:
    """Return a plain integer for supported smoke-test operands."""
    if isinstance(value, bool):
        return _normalize_bool_operand(value)

    if isinstance(value, Integral):
        return _normalize_integral_operand(value)

    if isinstance(value, float):
        return _normalize_float_operand(value)

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


def _add_three_normalized_operands(first: int, second: int, third: int) -> int:
    """Compose normalized addition so three-term arithmetic keeps the same rules."""
    partial_sum = _add_normalized_operands(first, second)
    return _add_normalized_operands(partial_sum, third)


def add(left: int | str, right: int | str) -> int:
    """Return the sum of two supported operands as an integer."""
    normalized_left, normalized_right = _coerce_operands(left, right)
    return _add_normalized_operands(normalized_left, normalized_right)


def add3(first: int | str, second: int | str, third: int | str) -> int:
    """Compose two additions so identity and sign handling stay consistent."""
    normalized_first = _normalize_operand(first)
    normalized_second = _normalize_operand(second)
    normalized_third = _normalize_operand(third)
    return _add_three_normalized_operands(
        normalized_first,
        normalized_second,
        normalized_third,
    )
