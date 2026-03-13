def add(a: int | str, b: int | str) -> int:
    """Return an integer sum for FastAPI-style numeric inputs."""

    return _coerce_int(a) + _coerce_int(b)


def add_many(first: int | str, second: int | str, third: int | str) -> int:
    """Return an integer sum for three FastAPI-style numeric inputs."""

    return _coerce_int(first) + _coerce_int(second) + _coerce_int(third)


def _coerce_int(value: int | str) -> int:
    if isinstance(value, bool):
        raise TypeError("boolean operands are not allowed")
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise TypeError("blank string operands are not allowed")
    return int(value)
