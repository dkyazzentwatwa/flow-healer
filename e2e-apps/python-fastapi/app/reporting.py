from __future__ import annotations

from datetime import UTC, datetime

from .service import TodoItem, TodoService


def generate_report(todo_service: TodoService) -> dict[str, object]:
    todos = [_serialize_todo(item) for item in todo_service.list_todos()]
    total = len(todos)
    completed = sum(1 for item in todos if item["completed"])

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "total": total,
            "completed": completed,
            "pending": total - completed,
            "completion_rate": _completion_rate(total, completed),
        },
        "todos": todos,
    }


def _serialize_todo(item: TodoItem) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "completed": item.completed,
        "completed_at": item.completed_at,
    }


def _completion_rate(total: int, completed: int) -> float:
    if total == 0:
        return 0.0
    return completed / total
