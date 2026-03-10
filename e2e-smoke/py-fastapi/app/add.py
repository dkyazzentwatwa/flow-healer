def add(a: int | str, b: int | str) -> int:
    """Return an integer sum for FastAPI-style numeric inputs."""

    return int(a) + int(b)
