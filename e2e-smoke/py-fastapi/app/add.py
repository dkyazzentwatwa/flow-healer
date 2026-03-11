def add(a: int | str, b: int | str) -> int:
    """Return an integer sum for FastAPI-style numeric inputs."""

    return _coerce_int(a) + _coerce_int(b)


def _coerce_int(value: int | str) -> int:
    if isinstance(value, bool):
        raise TypeError("boolean operands are not allowed")
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise TypeError("blank string operands are not allowed")
    return int(value)
