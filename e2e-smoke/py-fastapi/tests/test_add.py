from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.add import add, add_many


def test_add() -> None:
    assert add(2, 3) == 5


def test_add_coerces_fastapi_string_inputs() -> None:
    assert add("2", "3") == 5


def test_add_accepts_whitespace_padded_integer_strings() -> None:
    assert add(" 2 ", "\n3\t") == 5


def test_add_many_coerces_integer_strings() -> None:
    assert add_many("2", "3", "4") == 9


def test_add_many_accepts_whitespace_padded_integer_strings() -> None:
    assert add_many(" 2 ", "\n3\t", " 4\n") == 9


def test_add_many_supports_additional_operands() -> None:
    assert add_many(" 2 ", "3", 4, "5 ", 6) == 20


def test_add_many_rejects_blank_string_operands() -> None:
    with pytest.raises(TypeError, match="blank string operands are not allowed"):
        add_many("2", " ", "4")


@pytest.mark.parametrize("a, b", [("", "3"), ("2", " "), ("\t", "\n")])
def test_add_rejects_blank_string_operands(a: str, b: str) -> None:
    with pytest.raises(TypeError, match="blank string operands are not allowed"):
        add(a, b)


@pytest.mark.parametrize("a, b", [(True, 3), (2, False), (True, False)])
def test_add_rejects_boolean_operands(a: int | bool, b: int | bool) -> None:
    with pytest.raises(TypeError, match="boolean operands are not allowed"):
        add(a, b)
