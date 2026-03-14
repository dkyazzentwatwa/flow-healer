from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


HELLO_MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "hello.py"


def _load_hello_module():
    spec = spec_from_file_location("src.hello", HELLO_MODULE_PATH)
    assert spec is not None and spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hello_returns_world() -> None:
    module = _load_hello_module()

    assert module.hello() == "world"
