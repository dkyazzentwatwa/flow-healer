"""Compatibility add helper for issue-scoped smoke tasks."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import re
import sys
from numbers import Integral
from types import ModuleType


def _load_smoke_math_module() -> ModuleType:
    """Load the sibling smoke helper without depending on package imports."""
    smoke_math_path = Path(__file__).resolve().with_name("smoke_math.py")
    spec = spec_from_file_location("smoke_math", smoke_math_path)
    assert spec is not None and spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_smoke_math = _load_smoke_math_module()

ERROR_MESSAGE = _smoke_math.ERROR_MESSAGE
_INTEGER_STRING_PATTERN = re.compile(r"[+-]?[0-9]+")
_ASCII_WHITESPACE = " \t\n\r\v\f"
_DISALLOWED_STRING_CHARACTERS = ("\x00",)
def _get_max_integer_string_digits() -> int:
    """Return Python's active integer-string digit guardrail."""
    return sys.get_int_max_str_digits()


def _has_supported_digit_count(value: str) -> bool:
    """Return whether a normalized integer string fits Python's digit limit."""
    unsigned_value = value.removeprefix("+").removeprefix("-")
    max_integer_string_digits = _get_max_integer_string_digits()
    if max_integer_string_digits == 0:
        return True

    return len(unsigned_value) <= max_integer_string_digits


def _normalize_string_operand(value: str) -> int:
    """Normalize supported integer strings after trimming ASCII outer whitespace."""
    plain_value = str.__str__(value)
    stripped_value = plain_value.strip(_ASCII_WHITESPACE)
    if any(character in stripped_value for character in _DISALLOWED_STRING_CHARACTERS):
        raise TypeError(ERROR_MESSAGE)

    if stripped_value and _INTEGER_STRING_PATTERN.fullmatch(stripped_value):
        if not _has_supported_digit_count(stripped_value):
            raise TypeError(ERROR_MESSAGE)
        try:
            return int(stripped_value)
        except ValueError as exc:
            raise TypeError(ERROR_MESSAGE) from exc

    raise TypeError(ERROR_MESSAGE)


def _normalize_integral_operand(value: Integral) -> int:
    """Coerce integral inputs while preserving the helper's public error contract."""
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TypeError(ERROR_MESSAGE) from exc


def normalize_operand(value: object) -> int:
    """Normalize supported operands to a plain ``int`` for compatibility."""
    if isinstance(value, bool):
        return int(value)

    if isinstance(value, Integral):
        return _normalize_integral_operand(value)

    if isinstance(value, str):
        return _normalize_string_operand(value)

    raise TypeError(ERROR_MESSAGE)


def add(left: object, right: object) -> int:
    """Return the integer sum for the provided operands."""
    return normalize_operand(left) + normalize_operand(right)

__all__ = ["ERROR_MESSAGE", "add", "normalize_operand"]
