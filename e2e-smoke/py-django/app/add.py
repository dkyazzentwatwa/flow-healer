def _coerce_int(value: object) -> int:
    if isinstance(value, bool):
        raise TypeError("boolean operands are not allowed")
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise TypeError("blank string operands are not allowed")
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(str(value))


def add(a: object, b: object) -> int:
    return _coerce_int(a) + _coerce_int(b)
