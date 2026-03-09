from __future__ import annotations

import pytest

from app.api import complete_todo, create_app, create_todo, health


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
    assert getattr(error, "detail", "") == "todo_not_found"


def test_create_app_keeps_todo_state_isolated_per_app_instance() -> None:
    first_app = create_app()
    second_app = create_app()

    first_create = next(
        route.endpoint
        for route in first_app.routes
        if getattr(route, "path", None) == "/todos" and "POST" in getattr(route, "methods", set())
    )
    first_list = next(
        route.endpoint
        for route in first_app.routes
        if getattr(route, "path", None) == "/todos" and "GET" in getattr(route, "methods", set())
    )
    second_list = next(
        route.endpoint
        for route in second_app.routes
        if getattr(route, "path", None) == "/todos" and "GET" in getattr(route, "methods", set())
    )

    created = first_create({"title": "Ship fix"})

    assert created["item"]["id"] == "1"
    assert first_list()["items"] == [created["item"]]
    assert second_list()["items"] == []
