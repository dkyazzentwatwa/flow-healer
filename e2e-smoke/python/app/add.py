"""Minimal arithmetic helper for the Python smoke sandbox."""


def add(left: int, right: int) -> int:
    """Return the arithmetic sum for two integers, rejecting invalid inputs."""
    if isinstance(left, bool) or isinstance(right, bool):
        raise TypeError("bool inputs are not supported")
    if type(left) is not int or type(right) is not int:
        raise TypeError("add() operands must be integers")
    return left + right
