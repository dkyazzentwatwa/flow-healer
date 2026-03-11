def add(a: int | str, b: int | str) -> int:
    return _coerce_int(a) + _coerce_int(b)


def _coerce_int(value: int | str) -> int:
    if isinstance(value, bool):
        raise TypeError("boolean operands are not allowed")
    return int(value)
