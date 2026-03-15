def add(a: int | str, b: int | str) -> int:
    """Return an integer sum for FastAPI-style numeric inputs."""

    return _coerce_int(a) + _coerce_int(b)


def add_many(
    first: int | str,
    second: int | str,
    third: int | str,
    *rest: int | str,
) -> int:
    """Return an integer sum for one or more FastAPI-style numeric inputs."""

    total = _coerce_int(first) + _coerce_int(second) + _coerce_int(third)

    for value in rest:
        total += _coerce_int(value)

    return total


def _coerce_int(value: int | str) -> int:
    if isinstance(value, bool):
        raise TypeError("boolean operands are not allowed")

    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise TypeError("blank string operands are not allowed")
        try:
            return int(value)
        except ValueError as exc:
            raise TypeError("integer operands are required") from exc

    if isinstance(value, int):
        return value

    raise TypeError("integer operands are required")
