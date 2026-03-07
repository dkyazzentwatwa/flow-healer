"""Smoke-math fixture used by the Python sandbox tests."""

def add(a: int, b: int) -> int:
    """Return the exact integer sum, including values beyond 64-bit ranges."""
    return a + b
