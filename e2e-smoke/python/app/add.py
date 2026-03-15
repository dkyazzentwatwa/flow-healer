"""Minimal arithmetic helper for the Python smoke sandbox."""


def _coerce_int(value: int | str) -> int:
    if isinstance(value, bool):
        raise TypeError("bool inputs are not supported")

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as exc:
            raise TypeError("add() operands must be integers") from exc

    raise TypeError("add() operands must be integers")


def add(left: int | str, right: int | str) -> int:
    """Return the arithmetic sum for integer-like inputs, rejecting invalid inputs."""
    return _coerce_int(left) + _coerce_int(right)


def add_many(*args: int | str) -> int:
    """Return the arithmetic sum for an arbitrary number of integer-like inputs."""
    total = 0
    for arg in args:
        total += _coerce_int(arg)
    return total
