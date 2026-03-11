import pandas as pd
from typing import Any


def add(a: Any, b: Any) -> Any:
    if isinstance(a, (pd.Series, pd.DataFrame)):
        return a.add(b)
    return a + b
