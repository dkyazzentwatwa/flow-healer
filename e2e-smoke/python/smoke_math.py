"""Focused addition helper exercised by the Python smoke tests."""

from numbers import Integral


ERROR_MESSAGE = "add() operands must be integers or integer strings"

def _normalize_operand(value: int | str) -> int:
    """Return an integer for a supported operand."""
    if isinstance(value, bool):
        return int(value)

    if isinstance(value, Integral):
        return int(value)

    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            try:
                return int(stripped)
            except ValueError as exc:
                raise TypeError(ERROR_MESSAGE) from exc

    raise TypeError(ERROR_MESSAGE)


def add(left: int | str, right: int | str) -> int:
    """Return the sum of two supported operands as an integer."""
    left_value = _normalize_operand(left)
    right_value = _normalize_operand(right)
    return left_value + right_value
