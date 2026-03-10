from app.add import add


def test_add() -> None:
    assert add(2, 3) == 5


def test_add_accepts_stringable_values() -> None:
    class LazyNumber:
        def __init__(self, value: str) -> None:
            self.value = value

        def __str__(self) -> str:
            return self.value

    assert add(LazyNumber("2"), LazyNumber("3")) == 5
