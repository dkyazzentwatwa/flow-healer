from typing import TypeVar

AddableT = TypeVar("AddableT")


def add(a: AddableT, b: AddableT) -> AddableT:
    return a + b
