"""Simple addition helper used by the Python smoke tests."""

from numbers import Integral


ERROR_MESSAGE = "add() operands must be integers or integer strings"

def _normalize_operand(value: int | str) -> int:
    """Return an integer for supported operand inputs."""
    if isinstance(value, bool):
        return int(value)

    if isinstance(value, Integral):
        return value

    if isinstance(value, str):
        stripped_value = value.strip()
        if stripped_value:
            try:
                return int(stripped_value)
            except ValueError as exc:
                raise TypeError(ERROR_MESSAGE) from exc

    raise TypeError(ERROR_MESSAGE)


def add(left: int | str, right: int | str) -> int:
    """Return the integer sum for the provided operands, including negatives."""
    total = _normalize_operand(left) + _normalize_operand(right)
    return total
