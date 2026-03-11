from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ServiceRecord:
    service_id: str
    name: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ServiceRepository:
    def __init__(self, services: list[ServiceRecord] | None = None) -> None:
        source_services = [] if services is None else services
        self._services = [self._clone(service) for service in source_services]

    def add(self, service: ServiceRecord) -> ServiceRecord:
        stored_service = self._clone(service)
        self._services.append(stored_service)
        return self._clone(stored_service)

    def list_services(self) -> list[ServiceRecord]:
        return [self._clone(service) for service in self._services]

    @staticmethod
    def _clone(service: ServiceRecord) -> ServiceRecord:
        return deepcopy(service)


@dataclass(slots=True)
class TodoRecord:
    id: str
    title: str
    completed: bool = False
    completed_at: str | None = None


class InMemoryTodoRepository:
    def __init__(self, rows: list[TodoRecord] | None = None) -> None:
        self._rows: dict[str, TodoRecord] = {}
        for row in [] if rows is None else rows:
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
