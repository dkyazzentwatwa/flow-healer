from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.add import add


def test_add() -> None:
    assert add(2, 3) == 5


def test_add_preserves_numpy_array_behavior() -> None:
    values = np.array([1.0, 2.0, 3.0])

    result = add(values, 0.5)

    np.testing.assert_allclose(result, np.array([1.5, 2.5, 3.5]))


def test_add_supports_sklearn_style_array_like_inputs() -> None:
    values = [1.0, 2.0, 3.0]

    result = add(values, 0.5)

    np.testing.assert_allclose(result, np.array([1.5, 2.5, 3.5]))


def test_add_supports_array_protocol_inputs() -> None:
    class ArrayLike:
        def __init__(self, values):
            self._values = np.array(values)

        def __array__(self, dtype=None):
            return np.asarray(self._values, dtype=dtype)

    left = ArrayLike([1.0, 2.0, 3.0])
    right = ArrayLike([0.5, 0.5, 0.5])

    np.testing.assert_allclose(add(left, right), np.array([1.5, 2.5, 3.5]))
    np.testing.assert_allclose(add(0.5, right), np.array([1.0, 1.0, 1.0]))
