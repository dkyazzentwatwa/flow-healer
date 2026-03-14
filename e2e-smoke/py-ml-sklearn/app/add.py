from typing import Any, Optional

import numpy as np


def _coerce_array_like(value: Any) -> Optional[np.ndarray]:
    if isinstance(value, (np.ndarray, list, tuple)):
        return np.asarray(value)

    array_function = getattr(value, "__array__", None)
    if callable(array_function):
        return np.asarray(value)

    return None


def add(a: Any, b: Any) -> Any:
    left_array = _coerce_array_like(a)
    right_array = _coerce_array_like(b)

    if left_array is not None or right_array is not None:
        left_value = left_array if left_array is not None else a
        right_value = right_array if right_array is not None else b
        return np.add(left_value, right_value)

    return a + b
