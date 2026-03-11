from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.add import add


def test_add() -> None:
    assert add(2, 3) == 5


def test_add_coerces_flask_string_inputs() -> None:
    assert add("2", "3") == 5


@pytest.mark.parametrize("a, b", [(True, 3), (2, False), (True, False)])
def test_add_rejects_boolean_operands(a: int | bool, b: int | bool) -> None:
    with pytest.raises(TypeError, match="boolean operands are not allowed"):
        add(a, b)
