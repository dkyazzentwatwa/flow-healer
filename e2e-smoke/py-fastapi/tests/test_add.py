from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.add import add


def test_add() -> None:
    assert add(2, 3) == 5


def test_add_coerces_fastapi_string_inputs() -> None:
    assert add("2", "3") == 5
