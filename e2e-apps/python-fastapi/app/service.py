from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from app.repository import ServiceRecord, ServiceRepository

from .repository import InMemoryTodoRepository, TodoRecord


class DomainService:
    def __init__(self, repository: ServiceRepository) -> None:
        self._repository = repository

    def list_services(self) -> list[ServiceRecord]:
        return deepcopy(self._repository.list_services())


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
        return [self._to_item(row) for row in self._repository.list_all()]

    def create_todo(self, title: str) -> TodoItem:
        normalized = str(title or "").strip()
        if not normalized:
            raise ValueError("title_required")
        item = TodoRecord(id=str(self._next_id), title=normalized)
        self._next_id += 1
        self._repository.put(item)
        return self._to_item(item)

    def complete_todo(self, todo_id: str) -> TodoItem:
        existing = self._repository.get(str(todo_id))
        if existing is None:
            raise KeyError("todo_not_found")
        if not existing.completed:
            existing.completed = True
            existing.completed_at = datetime.now(UTC).isoformat()
            self._repository.put(existing)
        return self._to_item(existing)

    @staticmethod
    def _to_item(record: TodoRecord) -> TodoItem:
        return TodoItem(
            id=record.id,
            title=record.title,
            completed=record.completed,
            completed_at=record.completed_at,
        )

    def _compute_next_id(self) -> int:
        next_id = 1
        for row in self._repository.list_all():
            try:
                numeric_id = int(row.id)
            except (TypeError, ValueError):
                continue
            next_id = max(next_id, numeric_id + 1)
        return next_id
