from __future__ import annotations

import pytest

from app.api import complete_todo, create_todo, health


def test_health_returns_ok_status() -> None:
    assert health() == {"status": "ok"}


def test_create_todo_rejects_blank_titles() -> None:
    with pytest.raises(Exception) as exc_info:
        create_todo({"title": "   "})

    error = exc_info.value
    assert getattr(error, "status_code", None) == 400
    assert getattr(error, "detail", "") == "title_required"


def test_complete_todo_raises_not_found_for_unknown_id() -> None:
    with pytest.raises(Exception) as exc_info:
        complete_todo("404")

    error = exc_info.value
    assert getattr(error, "status_code", None) == 404
    assert "todo_not_found" in getattr(error, "detail", "")
