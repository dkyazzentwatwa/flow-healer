from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


ADD_MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "add.py"


def _load_add_module():
    spec = spec_from_file_location("app.add", ADD_MODULE_PATH)
    assert spec is not None and spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_add_returns_the_sum_of_two_integers() -> None:
    module = _load_add_module()

    assert module.add(2, 3) == 5


def test_add_keeps_integer_addition_unchanged_for_negative_values() -> None:
    module = _load_add_module()

    assert module.add(-4, 7) == 3


def test_add_accepts_stringified_integer_operands() -> None:
    module = _load_add_module()

    assert module.add("2", "3") == 5


def test_add_many_returns_the_sum_of_three_integers() -> None:
    module = _load_add_module()

    assert module.add_many(2, 3, 4) == 9


def test_add_many_accepts_stringified_integer_operands() -> None:
    module = _load_add_module()

    assert module.add_many("2", "3", "4") == 9


def test_add_many_rejects_invalid_operands() -> None:
    module = _load_add_module()

    with pytest.raises(TypeError, match=r"^add\(\) operands must be integers$"):
        module.add_many("two", 3, 4)


@pytest.mark.parametrize(
    ("left", "right"),
    (
        pytest.param(2.5, 3, id="rejects_float_operand"),
        pytest.param("two", 3, id="rejects_non_numeric_string_operand"),
    ),
)
def test_add_rejects_non_boolean_non_integer_operands(left: object, right: object) -> None:
    module = _load_add_module()

    with pytest.raises(TypeError, match=r"^add\(\) operands must be integers$"):
        module.add(left, right)


@pytest.mark.parametrize(
    ("left", "right"),
    [(True, 3), (2, False), (True, False)],
)
def test_add_rejects_boolean_inputs(left: int, right: int) -> None:
    module = _load_add_module()

    with pytest.raises(TypeError, match="bool inputs are not supported"):
        module.add(left, right)
