import pandas as pd
from typing import Any


def add(a: Any, b: Any) -> Any:
    if isinstance(a, pd.core.base.PandasObject) and callable(getattr(a, "add", None)):
        return a.add(b)
    return a + b


def add_many(first: Any, second: Any, third: Any, *rest: Any) -> Any:
    result = add(add(first, second), third)
    for value in rest:
        result = add(result, value)
    return result
