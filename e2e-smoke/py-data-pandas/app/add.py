import pandas as pd
from typing import Any


def _is_pandas_addable(value: Any) -> bool:
    add_method = getattr(value, "add", None)
    if not callable(add_method):
        return False

    if isinstance(value, pd.core.base.PandasObject):
        return True

    module = getattr(value.__class__, "__module__", "")
    return module.startswith("pandas.")


def add(a: Any, b: Any) -> Any:
    if _is_pandas_addable(a):
        return a.add(b)
    if _is_pandas_addable(b):
        return b.add(a)
    return a + b


def add_many(first: Any, second: Any, third: Any, *rest: Any) -> Any:
    result = add(add(first, second), third)
    for value in rest:
        result = add(result, value)
    return result
