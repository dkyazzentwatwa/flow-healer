from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from app.repository import ServiceRecord, ServiceRepository

from .repository import InMemoryTodoRepository, TodoRecord

TODO_NOT_FOUND = "todo_not_found"


class DomainService:
    def __init__(self, repository: ServiceRepository) -> None:
        self._repository = repository

    def list_services(self) -> list[ServiceRecord]:
        return deepcopy(self._repository.list_services())

    def create_service(
        self,
        service_id: str,
        name: str,
        *,
        tags: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ServiceRecord:
        record = ServiceRecord(
            service_id=self._require_text(service_id, "service_id_required"),
            name=self._require_text(name, "name_required"),
            tags=self._normalize_tags(tags),
            metadata=deepcopy({} if metadata is None else metadata),
        )
        return self._repository.add(record)

    def add_service(
        self,
        service_id: str,
        name: str,
        *,
        tags: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ServiceRecord:
        return self.create_service(service_id, name, tags=tags, metadata=metadata)

    def register_service(
        self,
        service_id: str,
        name: str,
        *,
        tags: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ServiceRecord:
        return self.create_service(service_id, name, tags=tags, metadata=metadata)

    @staticmethod
    def _normalize_tags(tags: list[str] | None) -> list[str]:
        if tags is None:
            return []

        normalized: list[str] = []
        seen: set[str] = set()
        for value in tags:
            tag = DomainService._require_text(value, "tag_required")
            if tag in seen:
                continue
            seen.add(tag)
            normalized.append(tag)
        return normalized

    @staticmethod
    def _require_text(value: str, error_code: str) -> str:
        if not isinstance(value, str):
            raise ValueError(error_code)

        normalized = value.strip()
        if not normalized:
            raise ValueError(error_code)
        return normalized


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
        self._repository = InMemoryTodoRepository() if repository is None else repository
        self._next_id = self._compute_next_id()

    def list_todos(self) -> list[TodoItem]:
        return [self._to_item(row) for row in self._repository.list_all()]

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

        normalized_id = TodoService._normalize_todo_id(todo_id)
        if not normalized_id:
            raise KeyError(TODO_NOT_FOUND)

        existing = self._repository.get(normalized_id)
        if existing is None:
            existing = self._find_record_by_normalized_id(normalized_id)
        if existing is None:
            raise KeyError(TODO_NOT_FOUND)
        if not existing.completed or self._is_missing_timestamp(existing.completed_at):
            existing.completed = True
            existing.completed_at = datetime.now(UTC).isoformat()
            self._repository.put(existing)
        return self._to_item(existing)

    @staticmethod
    def _to_item(record: TodoRecord) -> TodoItem:
        return TodoItem(
            id=TodoService._normalize_todo_id(record.id),
            title=record.title,
            completed=record.completed,
            completed_at=record.completed_at,
        )

    @staticmethod
    def _is_missing_timestamp(value: object) -> bool:
        return not isinstance(value, str) or not value.strip()

    def _find_record_by_normalized_id(self, normalized_id: str) -> TodoRecord | None:
        for row in self._repository.list_all():
            if TodoService._normalize_todo_id(row.id) == normalized_id:
                return row
        return None

    def _compute_next_id(self) -> int:
        next_id = 1
        for row in self._repository.list_all():
            try:
                numeric_id = int(str(row.id).strip())
            except (TypeError, ValueError):
                continue
            next_id = max(next_id, numeric_id + 1)
        return next_id

    @staticmethod
    def _normalize_todo_id(value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        unsigned = raw[1:] if raw.startswith("+") else raw
        candidate = unsigned.lstrip("-")
        if candidate and candidate.isdigit():
            try:
                numeric = int(unsigned)
            except ValueError:
                return unsigned
            return str(numeric)
        return unsigned
