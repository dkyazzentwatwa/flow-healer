from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.add import add


def test_add() -> None:
    assert add(2, 3) == 5


def test_add_coerces_fastapi_string_inputs() -> None:
    assert add("2", "3") == 5


def test_add_accepts_whitespace_padded_integer_strings() -> None:
    assert add(" 2 ", "\n3\t") == 5


@pytest.mark.parametrize("a, b", [("", "3"), ("2", " "), ("\t", "\n")])
def test_add_rejects_blank_string_operands(a: str, b: str) -> None:
    with pytest.raises(TypeError, match="blank string operands are not allowed"):
        add(a, b)
