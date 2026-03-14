from app.add import add

import pytest


def test_add() -> None:
    assert add(2, 3) == 5


def test_add_accepts_stringable_values() -> None:
    class DjangoStringable:
        def __init__(self, value: str) -> None:
            self.value = value

        def __str__(self) -> str:
            return self.value

    assert add(DjangoStringable("2"), DjangoStringable("3")) == 5


def test_add_unwraps_value_wrappers() -> None:
    class DjangoValueWrapper:
        def __init__(self, value: object) -> None:
            self.value = value

    wrapped = DjangoValueWrapper(DjangoValueWrapper(" 2 "))
    unwrapped = DjangoValueWrapper("3")

    assert add(wrapped, unwrapped) == 5


def test_add_accepts_numeric_string_wrappers_with_broken_int_conversion() -> None:
    class DjangoBoundaryValue:
        def __init__(self, value: str) -> None:
            self.value = value

        def __int__(self) -> int:
            raise ValueError("boundary coercion failed")

        def __str__(self) -> str:
            return self.value

    assert add(DjangoBoundaryValue("2"), DjangoBoundaryValue("3")) == 5


def test_add_accepts_whitespace_padded_integer_strings() -> None:
    assert add(" 2 ", "\n3\t") == 5


@pytest.mark.parametrize("a, b", [("", "3"), ("2", " "), ("\t", "\n")])
def test_add_rejects_blank_string_operands(a: str, b: str) -> None:
    with pytest.raises(TypeError, match="blank string operands are not allowed"):
        add(a, b)


def test_add_rejects_boolean_operands() -> None:
    with pytest.raises(TypeError):
        add(True, 2)
