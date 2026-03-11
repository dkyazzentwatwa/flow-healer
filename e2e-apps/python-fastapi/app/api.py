from __future__ import annotations

from collections.abc import Mapping
from .service import TodoItem, TodoService

APP_NAME = "Flow Healer Python FastAPI Sandbox"

try:
    from fastapi import Body, FastAPI, HTTPException
except Exception:  # pragma: no cover - lightweight fallback for minimal environments
    from types import SimpleNamespace

    def Body(default: object = None) -> object:
        return default

    class HTTPException(Exception):
        def __init__(self, *, status_code: int, detail: str) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class FastAPI:  # type: ignore[override]
        def __init__(self, *, title: str) -> None:
            self.title = title
            self.routes: list[SimpleNamespace] = []

        def _route(self, path: str, methods: set[str], endpoint: object, status_code: int = 200) -> None:
            self.routes.append(
                SimpleNamespace(path=path, methods=methods, endpoint=endpoint, status_code=status_code)
            )

        def get(self, _path: str):
            def decorator(func):
                self._route(_path, {"GET"}, func, status_code=200)
                return func

            return decorator

        def post(self, _path: str, **_kwargs: object):
            def decorator(func):
                status_code = _kwargs.get("status_code", 200)
                if not isinstance(status_code, int):
                    status_code = 200
                self._route(_path, {"POST"}, func, status_code=status_code)
                return func

            return decorator

service = TodoService()


def health() -> dict[str, object]:
    return {"status": "ok", "service": {"name": APP_NAME}}


def _service_for(request_service: TodoService | None) -> TodoService:
    return service if request_service is None else request_service


def list_todos(todo_service: TodoService | None = None) -> dict[str, object]:
    return {"todos": [_serialize_todo(item) for item in _service_for(todo_service).list_todos()]}


def _serialize_todo(item: TodoItem) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "completed": item.completed,
        "completed_at": item.completed_at,
    }


def _extract_title(payload: object) -> str:
    if not isinstance(payload, Mapping):
        return ""

    raw_title = payload.get("title", "")
    if not isinstance(raw_title, str):
        return ""
    return raw_title.strip()


def create_todo(
    payload: Mapping[str, object] | None = None,
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
    app = FastAPI(title=APP_NAME)
    app_service = TodoService()

    def app_list_todos() -> dict[str, object]:
        return list_todos(app_service)

    def app_create_todo(payload: object = Body(default=None)) -> dict[str, object]:
        return create_todo(payload, app_service)

    def app_complete_todo(todo_id: str) -> dict[str, object]:
        return complete_todo(todo_id, app_service)

    app.get("/health")(health)
    app.get("/todos")(app_list_todos)
    app.post("/todos", status_code=201)(app_create_todo)
    app.post("/todos/{todo_id}/complete")(app_complete_todo)
    return app


app = create_app()
