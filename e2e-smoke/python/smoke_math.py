"""Focused addition helper exercised by the Python smoke tests."""

import re
import sys
from numbers import Integral


ERROR_MESSAGE = "add() operands must be integers or integer strings"
_INTEGER_STRING_PATTERN = re.compile(r"[+-]?[0-9]+")
_ASCII_WHITESPACE = " \t\n\r\v\f"
_DISALLOWED_STRING_CHARACTERS = ("\x00",)


def _get_max_integer_string_digits() -> int:
    """Return the active interpreter guardrail for integer-string parsing."""
    get_max_digits = getattr(sys, "get_int_max_str_digits", None)
    if get_max_digits is None:
        return 0

    return int(get_max_digits())


def _has_supported_digit_count(value: str) -> bool:
    """Return whether a normalized integer string fits Python's digit limit."""
    unsigned_value = value.removeprefix("+").removeprefix("-")
    max_integer_string_digits = _get_max_integer_string_digits()
    if max_integer_string_digits == 0:
        return True

    return len(unsigned_value) <= max_integer_string_digits


def _normalize_integer_string(value: str) -> int:
    """Return an integer parsed from a supported string operand."""
    stripped_value = str.__str__(value).strip(_ASCII_WHITESPACE)
    if not stripped_value:
        raise TypeError(ERROR_MESSAGE)

    if any(character in stripped_value for character in _DISALLOWED_STRING_CHARACTERS):
        raise TypeError(ERROR_MESSAGE)

    if not _INTEGER_STRING_PATTERN.fullmatch(stripped_value):
        raise TypeError(ERROR_MESSAGE)

    if not _has_supported_digit_count(stripped_value):
        raise TypeError(ERROR_MESSAGE)

    try:
        return int(stripped_value)
    except (TypeError, ValueError) as exc:
        raise TypeError(ERROR_MESSAGE) from exc


def _normalize_integral_operand(value: Integral) -> int:
    """Return a plain integer for supported integral operands."""
    try:
        return int(value)
    except Exception as exc:
        raise TypeError(ERROR_MESSAGE) from exc


def _normalize_operand(value: int | str) -> int:
    """Return an integer for a supported operand."""
    if isinstance(value, bool):
        return int(value)

    if isinstance(value, Integral):
        return _normalize_integral_operand(value)

    if isinstance(value, str):
        return _normalize_integer_string(value)

    raise TypeError(ERROR_MESSAGE)


def add(left: int | str, right: int | str) -> int:
    """Return the sum of two supported operands as an integer."""
    normalized_left = _normalize_operand(left)
    normalized_right = _normalize_operand(right)
    return normalized_left + normalized_right
