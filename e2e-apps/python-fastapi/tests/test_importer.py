from __future__ import annotations

import json

import pytest

from app.importer import import_todos
from app.service import TodoService


def test_import_todos_creates_items_from_json_payload() -> None:
    service = TodoService()

    imported = import_todos(
        json.dumps(
            [
                {"title": "  Ship release  "},
                {"title": "Document API", "completed": True},
            ]
        ),
        todo_service=service,
    )

    assert [item.title for item in imported] == ["Ship release", "Document API"]
    assert [item.completed for item in imported] == [False, True]
    assert imported[0].completed_at is None
    assert imported[1].completed_at is not None
    assert [item.id for item in service.list_todos()] == ["1", "2"]


def test_import_todos_accepts_mapping_with_items_key() -> None:
    imported = import_todos({"items": [{"title": "Backfill analytics"}]})

    assert len(imported) == 1
    assert imported[0].title == "Backfill analytics"


def test_import_todos_rejects_invalid_payload_shapes() -> None:
    with pytest.raises(ValueError, match="items_payload_required"):
        import_todos(None)

    with pytest.raises(ValueError, match="items_payload_required"):
        import_todos("{")

    with pytest.raises(ValueError, match="items_payload_required"):
        import_todos({"items": "not-a-list"})


def test_import_todos_rejects_invalid_item_entries() -> None:
    with pytest.raises(ValueError, match="item_mapping_required"):
        import_todos([None])

    with pytest.raises(ValueError, match="title_required"):
        import_todos([{"title": "   "}])
