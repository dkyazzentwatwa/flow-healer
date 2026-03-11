from __future__ import annotations

import pytest

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import complete_todo, create_app, create_todo, health, list_todos


def _expected_todo_payload(
    *,
    todo_id: str,
    title: str,
    completed: bool = False,
    completed_at: str | None = None,
) -> dict[str, object]:
    return {
        "id": todo_id,
        "title": title,
        "completed": completed,
        "completed_at": completed_at,
    }


def _route_endpoint_for(app, path: str, method: str):
    matches = [
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set())
    ]
    assert len(matches) == 1
    return matches[0]


def _route_for(app, path: str, method: str):
    matches = [
        route
        for route in app.routes
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set())
    ]
    assert len(matches) == 1
    return matches[0]


def test_health_returns_ok_status() -> None:
    assert health() == {"status": "ok"}


def test_create_todo_rejects_blank_titles() -> None:
    with pytest.raises(HTTPException) as exc_info:
        create_todo({"title": "   "})

    error = exc_info.value
    assert error.status_code == 400
    assert error.detail == "title_required"


def test_create_todo_rejects_non_text_title_payloads() -> None:
    for payload in (None, {}, {"title": None}, {"title": 123}, {"text": "Ship"}):
        with pytest.raises(HTTPException) as exc_info:
            create_todo(payload)

        error = exc_info.value
        assert error.status_code == 400
        assert error.detail == "title_required"


def test_create_todo_route_rejects_missing_and_non_object_bodies_with_contract_error() -> None:
    client = TestClient(create_app())

    for request_kwargs in ({}, {"json": None}, {"json": []}):
        response = client.post("/todos", **request_kwargs)

        assert response.status_code == 400
        assert response.json() == {"detail": "title_required"}


def test_list_todos_returns_stable_todos_payload() -> None:
    app = create_app()
    create = _route_endpoint_for(app, "/todos", "POST")
    list_items = _route_endpoint_for(app, "/todos", "GET")
    created = create({"title": "Ship fix"})
    expected_todo = _expected_todo_payload(todo_id="1", title="Ship fix")

    assert created == {"item": expected_todo}
    assert list_items() == {"todos": [expected_todo]}


def test_todo_payload_mutations_do_not_leak_back_into_repository_state() -> None:
    app = create_app()
    create = _route_endpoint_for(app, "/todos", "POST")
    list_items = _route_endpoint_for(app, "/todos", "GET")
    expected_todo = _expected_todo_payload(todo_id="1", title="Ship fix")

    created = create({"title": "Ship fix"})
    assert created == {"item": expected_todo}

    created["item"]["title"] = "Mutated outside the API"

    listed = list_items()
    listed["todos"][0]["completed"] = True

    assert list_items() == {"todos": [expected_todo]}


def test_complete_todo_raises_not_found_for_unknown_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        complete_todo("404")

    error = exc_info.value
    assert error.status_code == 404
    assert error.detail == "todo_not_found"


def test_create_app_keeps_todo_state_isolated_per_app_instance() -> None:
    first_app = create_app()
    second_app = create_app()

    first_create = _route_endpoint_for(first_app, "/todos", "POST")
    first_list = _route_endpoint_for(first_app, "/todos", "GET")
    second_list = _route_endpoint_for(second_app, "/todos", "GET")
    expected_todo = _expected_todo_payload(todo_id="1", title="Ship fix")

    created = first_create({"title": "Ship fix"})

    assert created == {"item": expected_todo}
    assert first_list() == {"todos": [expected_todo]}
    assert second_list()["todos"] == []


def test_create_todo_route_uses_created_status_code() -> None:
    app = create_app()
    create_route = _route_for(app, "/todos", "POST")

    assert create_route.status_code == 201


def test_complete_todo_returns_completed_todo_payload() -> None:
    app = create_app()
    create = _route_endpoint_for(app, "/todos", "POST")
    complete = _route_endpoint_for(app, "/todos/{todo_id}/complete", "POST")

    created = create({"title": "Ship fix"})
    todo_id = created["item"]["id"]
    completed = complete(todo_id)

    expected_completed_todo = _expected_todo_payload(
        todo_id=todo_id,
        title="Ship fix",
        completed=True,
        completed_at=completed["item"]["completed_at"],
    )

    assert completed == {"item": expected_completed_todo}
    assert completed["item"]["completed_at"] is not None
