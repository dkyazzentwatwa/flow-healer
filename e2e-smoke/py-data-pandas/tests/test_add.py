from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.add import add


def test_add() -> None:
    assert add(2, 3) == 5


def test_add_does_not_use_non_pandas_add_methods() -> None:
    class CustomAddable:
        def __init__(self, value: int) -> None:
            self.value = value
            self.used_native_add = False

        def __add__(self, other: int) -> "CustomAddable":
            return CustomAddable(self.value + other)

        def add(self, other: int) -> "CustomAddable":
            self.used_native_add = True
            return CustomAddable(self.value + other + 100)

    result = add(CustomAddable(1), 2)

    assert result.value == 3


def test_add_preserves_pandas_series_behavior() -> None:
    values = pd.Series([1, 2, 3], name="value")

    result = add(values, 10)

    expected = pd.Series([11, 12, 13], name="value")
    pd.testing.assert_series_equal(result, expected)


def test_add_uses_pandas_native_add_when_available() -> None:
    class TrackingDataFrame(pd.DataFrame):
        _metadata = ["used_native_add"]

        @property
        def _constructor(self) -> type["TrackingDataFrame"]:
            return TrackingDataFrame

        def add(self, other, *args, **kwargs):  # type: ignore[override]
            result = super().add(other, *args, **kwargs)
            result.used_native_add = True
            return result

    values = TrackingDataFrame({"value": [1, 2, 3]})
    values.used_native_add = False

    result = add(values, 10)

    expected = pd.DataFrame({"value": [11, 12, 13]})
    pd.testing.assert_frame_equal(result, expected, check_frame_type=False)
    assert result.used_native_add is True
