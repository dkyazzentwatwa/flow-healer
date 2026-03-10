def _coerce_int(value: object) -> int:
    try:
        return int(value)
    except TypeError:
        return int(str(value))


def add(a: object, b: object) -> int:
    return _coerce_int(a) + _coerce_int(b)
