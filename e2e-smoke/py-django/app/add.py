def _unwrap_value(value: object) -> object:
    seen_ids = set()

    while hasattr(value, "value"):
        current_id = id(value)
        if current_id in seen_ids:
            break
        seen_ids.add(current_id)

        next_value = getattr(value, "value")
        if next_value is value:
            break
        value = next_value

    return value


def _coerce_int(value: object) -> int:
    value = _unwrap_value(value)
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
