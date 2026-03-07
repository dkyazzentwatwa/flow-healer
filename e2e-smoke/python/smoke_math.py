"""Smoke-math fixture used by the Python sandbox tests."""

def add(a: int, b: int) -> int:
    if a == 0:
        return b
    if b == 0:
        return a
    return a + b
