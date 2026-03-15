from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from .service import TodoItem, TodoService


def import_todos(
    payload: object,
    *,
    todo_service: TodoService | None = None,
) -> list[TodoItem]:
    service = TodoService() if todo_service is None else todo_service
    prepared_items = _prepare_items(payload)
    imported: list[TodoItem] = []

    for prepared in prepared_items:
        created = service.create_todo(prepared["title"])
        if prepared["completed"]:
            created = service.complete_todo(created.id)
        imported.append(created)

    return imported


def _prepare_items(payload: object) -> list[dict[str, object]]:
    prepared: list[dict[str, object]] = []
    for entry in _extract_items(payload):
        prepared.append(
            {
                "title": _extract_title(entry),
                "completed": _is_completed(entry),
            }
        )
    return prepared


def _extract_items(payload: object) -> list[Mapping[str, object]]:
    resolved = _parse_payload(payload)
    if isinstance(resolved, Mapping):
        items = resolved.get("items")
    elif _is_sequence(resolved):
        items = resolved
    else:
        items = None

    if not _is_sequence(items):
        raise ValueError("items_payload_required")

    normalized: list[Mapping[str, object]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("item_mapping_required")
        normalized.append(item)
    return normalized


def _parse_payload(payload: object) -> object:
    if isinstance(payload, (str, bytes, bytearray)):
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("items_payload_required") from exc
    return payload


def _extract_title(item: Mapping[str, object]) -> str:
    title = item.get("title")
    if not isinstance(title, str):
        raise ValueError("title_required")
    normalized = title.strip()
    if not normalized:
        raise ValueError("title_required")
    return normalized


def _is_completed(item: Mapping[str, object]) -> bool:
    return item.get("completed") is True


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
