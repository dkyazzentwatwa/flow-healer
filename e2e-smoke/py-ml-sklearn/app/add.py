from typing import Any

import numpy as np


def add(a: Any, b: Any) -> Any:
    if isinstance(a, (np.ndarray, list, tuple)):
        return np.add(a, b)
    return a + b
