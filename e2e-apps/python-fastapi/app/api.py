from __future__ import annotations

from .service import TodoService

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


def list_todos() -> dict[str, object]:
    return {"items": [item.as_dict() for item in service.list_todos()]}


def create_todo(payload: dict[str, object]) -> dict[str, object]:
    try:
        created = service.create_todo(str(payload.get("title", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": created.as_dict()}


def complete_todo(todo_id: str) -> dict[str, object]:
    try:
        item = service.complete_todo(todo_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"item": item.as_dict()}


def create_app() -> FastAPI:
    app = FastAPI(title="Flow Healer Python FastAPI Sandbox")
    app.get("/health")(health)
    app.get("/todos")(list_todos)
    app.post("/todos")(create_todo)
    app.post("/todos/{todo_id}/complete")(complete_todo)
    return app


app = create_app()
