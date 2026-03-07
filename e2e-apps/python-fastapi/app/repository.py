from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass


@dataclass(slots=True)
class TodoRecord:
    todo_id: str
    title: str
    completed: bool = False


class TodoRepository:
    def __init__(self, todos: list[TodoRecord] | None = None) -> None:
        self._todos = deepcopy(todos) if todos is not None else []

    def add(self, todo: TodoRecord) -> TodoRecord:
        stored_todo = deepcopy(todo)
        self._todos.append(stored_todo)
        return deepcopy(stored_todo)

    def get(self, todo_id: str) -> TodoRecord | None:
        for todo in self._todos:
            if todo.todo_id == todo_id:
                return deepcopy(todo)
        return None

    def update(self, updated_todo: TodoRecord) -> TodoRecord:
        for index, todo in enumerate(self._todos):
            if todo.todo_id == updated_todo.todo_id:
                stored_todo = deepcopy(updated_todo)
                self._todos[index] = stored_todo
                return deepcopy(stored_todo)
        raise KeyError(updated_todo.todo_id)
