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


def test_add_rejects_boolean_operands() -> None:
    with pytest.raises(TypeError):
        add(True, 2)
