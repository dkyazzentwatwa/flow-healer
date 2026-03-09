from __future__ import annotations

from collections.abc import Mapping
from .service import TodoItem, TodoService

try:
    from fastapi import FastAPI, HTTPException
except Exception:  # pragma: no cover - lightweight fallback for minimal environments
    class HTTPException(Exception):
        def __init__(self, *, status_code: int, detail: str) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class FastAPI:  # type: ignore[override]
        def __init__(self, *, title: str) -> None:
            self.title = title

        def get(self, _path: str):
            def decorator(func):
                return func

            return decorator

        def post(self, _path: str):
            def decorator(func):
                return func

            return decorator

service = TodoService()


def health() -> dict[str, str]:
    return {"status": "ok"}


def _service_for(request_service: TodoService | None) -> TodoService:
    return request_service or service


def list_todos(todo_service: TodoService | None = None) -> dict[str, object]:
    return {"todos": [_serialize_todo(item) for item in _service_for(todo_service).list_todos()]}


def _serialize_todo(item: TodoItem) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "completed": item.completed,
        "completed_at": item.completed_at,
    }


def _extract_title(payload: Mapping[str, object]) -> str:
    raw_title = payload.get("title", "")
    if not isinstance(raw_title, str):
        return ""
    return raw_title.strip()


def create_todo(
    payload: Mapping[str, object],
    todo_service: TodoService | None = None,
) -> dict[str, object]:
    try:
        created = _service_for(todo_service).create_todo(_extract_title(payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": _serialize_todo(created)}


def complete_todo(todo_id: str, todo_service: TodoService | None = None) -> dict[str, object]:
    try:
        item = _service_for(todo_service).complete_todo(todo_id)
    except KeyError as exc:
        detail = str(exc.args[0]) if exc.args else "todo_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc
    return {"item": _serialize_todo(item)}


def create_app() -> FastAPI:
    app = FastAPI(title="Flow Healer Python FastAPI Sandbox")
    app_service = TodoService()

    def app_list_todos() -> dict[str, object]:
        return list_todos(app_service)

    def app_create_todo(payload: dict[str, object]) -> dict[str, object]:
        return create_todo(payload, app_service)

    def app_complete_todo(todo_id: str) -> dict[str, object]:
        return complete_todo(todo_id, app_service)

    app.get("/health")(health)
    app.get("/todos")(app_list_todos)
    app.post("/todos")(app_create_todo)
    app.post("/todos/{todo_id}/complete")(app_complete_todo)
    return app


app = create_app()
