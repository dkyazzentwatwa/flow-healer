from __future__ import annotations

from dataclasses import dataclass

from app.repository import TodoRecord, TodoRepository


class TodoNotFoundError(LookupError):
    """Raised when a requested todo record does not exist."""


@dataclass(slots=True)
class DomainService:
    repository: TodoRepository

    @staticmethod
    def _todo_not_found(todo_id: str) -> TodoNotFoundError:
        return TodoNotFoundError(f"Todo '{todo_id}' was not found.")

    def create_todo(self, title: str) -> TodoRecord:
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("Todo title must not be empty.")

        next_id = f"todo-{len(self.repository._todos) + 1}"
        todo = TodoRecord(todo_id=next_id, title=normalized_title)
        return self.repository.add(todo)

    def complete_todo(self, todo_id: str) -> TodoRecord:
        try:
            todo = self.repository.get(todo_id)
        except KeyError as exc:
            raise self._todo_not_found(todo_id) from exc

        if todo is None:
            raise self._todo_not_found(todo_id)

        todo.completed = True
        try:
            return self.repository.update(todo)
        except KeyError as exc:
            raise self._todo_not_found(todo_id) from exc
