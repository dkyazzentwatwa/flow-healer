from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.add import add


def test_add() -> None:
    assert add(2, 3) == 5


def test_add_preserves_pandas_series_behavior() -> None:
    values = pd.Series([1, 2, 3], name="value")

    result = add(values, 10)

    expected = pd.Series([11, 12, 13], name="value")
    pd.testing.assert_series_equal(result, expected)
