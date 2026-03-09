from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

try:
    from fastapi import FastAPI, HTTPException
except Exception:  # pragma: no cover - fallback when FastAPI is unavailable
    from types import SimpleNamespace

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

        def get(self, path: str):
            def decorator(func):
                self._route(path, {"GET"}, func)
                return func

            return decorator

        def post(self, path: str, *, status_code: int = 200):
            def decorator(func):
                self._route(path, {"POST"}, func, status_code=status_code)
                return func

            return decorator


TODO_NOT_FOUND = "todo_not_found"


@dataclass(slots=True)
class TodoRecord:
    id: str
    title: str
    completed: bool = False
    completed_at: str | None = None


class InMemoryTodoRepository:
    def __init__(self, rows: list[TodoRecord] | None = None) -> None:
        self._rows: dict[str, TodoRecord] = {}
        for row in rows or []:
            self.put(row)

    def list_all(self) -> list[TodoRecord]:
        return [self._clone(row) for row in self._rows.values()]

    def get(self, todo_id: str) -> TodoRecord | None:
        row = self._rows.get(todo_id)
        if row is None:
            return None
        return self._clone(row)

    def put(self, record: TodoRecord) -> None:
        self._rows[record.id] = self._clone(record)

    @staticmethod
    def _clone(record: TodoRecord) -> TodoRecord:
        return deepcopy(record)


@dataclass(slots=True)
class TodoItem:
    id: str
    title: str
    completed: bool
    completed_at: str | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class TodoService:
    def __init__(self, repository: InMemoryTodoRepository | None = None) -> None:
        self._repository = repository or InMemoryTodoRepository()
        self._next_id = self._compute_next_id()

    def list_todos(self) -> list[TodoItem]:
        return [self._to_item(record) for record in self._repository.list_all()]

    def create_todo(self, title: str) -> TodoItem:
        if not isinstance(title, str):
            raise ValueError("title_required")

        normalized = title.strip()
        if not normalized:
            raise ValueError("title_required")

        item = TodoRecord(id=str(self._next_id), title=normalized)
        self._next_id += 1
        self._repository.put(item)
        return self._to_item(item)

    def complete_todo(self, todo_id: str) -> TodoItem:
        if not isinstance(todo_id, str):
            raise KeyError(TODO_NOT_FOUND)

        normalized_id = todo_id.strip()
        if not normalized_id:
            raise KeyError(TODO_NOT_FOUND)

        record = self._repository.get(normalized_id)
        if record is None:
            raise KeyError(TODO_NOT_FOUND)

        if not record.completed or self._is_missing_timestamp(record.completed_at):
            record.completed = True
            record.completed_at = datetime.now(UTC).isoformat()
            self._repository.put(record)
        return self._to_item(record)

    @staticmethod
    def _to_item(record: TodoRecord) -> TodoItem:
        return TodoItem(
            id=record.id,
            title=record.title,
            completed=record.completed,
            completed_at=record.completed_at,
        )

    @staticmethod
    def _is_missing_timestamp(value: object) -> bool:
        return not isinstance(value, str) or not value.strip()

    def _compute_next_id(self) -> int:
        next_id = 1
        for row in self._repository.list_all():
            try:
                numeric_id = int(str(row.id).strip())
            except (TypeError, ValueError):
                continue
            next_id = max(next_id, numeric_id + 1)
        return next_id


service = TodoService()


def health() -> dict[str, str]:
    return {"status": "ok"}


def _service_for(request_service: TodoService | None) -> TodoService:
    return request_service or service


def _serialize_todo(item: TodoItem) -> dict[str, object]:
    return item.as_dict()


def list_todos(todo_service: TodoService | None = None) -> dict[str, object]:
    return {"todos": [_serialize_todo(item) for item in _service_for(todo_service).list_todos()]}


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
        item = _service_for(todo_service).create_todo(_extract_title(payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": _serialize_todo(item)}


def complete_todo(todo_id: str, todo_service: TodoService | None = None) -> dict[str, object]:
    try:
        item = _service_for(todo_service).complete_todo(todo_id)
    except KeyError as exc:
        detail = str(exc.args[0]) if exc.args else TODO_NOT_FOUND
        raise HTTPException(status_code=404, detail=detail) from exc
    return {"item": _serialize_todo(item)}


def create_app() -> FastAPI:
    app = FastAPI(title="Flow Healer Python App Smoke Sandbox")
    app_service = TodoService()

    def app_list_todos() -> dict[str, object]:
        return list_todos(app_service)

    def app_create_todo(payload: dict[str, object]) -> dict[str, object]:
        return create_todo(payload, app_service)

    def app_complete_todo(todo_id: str) -> dict[str, object]:
        return complete_todo(todo_id, app_service)

    app.get("/health")(health)
    app.get("/todos")(app_list_todos)
    app.post("/todos", status_code=201)(app_create_todo)
    app.post("/todos/{todo_id}/complete")(app_complete_todo)
    return app


app = create_app()
