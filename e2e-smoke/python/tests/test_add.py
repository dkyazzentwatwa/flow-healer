from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


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
