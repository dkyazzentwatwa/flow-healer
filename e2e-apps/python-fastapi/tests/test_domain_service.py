from __future__ import annotations

import pytest

from app.repository import InMemoryTodoRepository, ServiceRecord, ServiceRepository, TodoRecord
from app.service import DomainService, TodoService


def test_repository_list_services_returns_detached_records() -> None:
    repository = ServiceRepository(
        [
            ServiceRecord(
                service_id="svc-1",
                name="billing",
                tags=["core"],
                metadata={"region": "us-west-2"},
            )
        ]
    )

    listed_services = repository.list_services()
    listed_services[0].tags.append("mutated")
    listed_services[0].metadata["region"] = "eu-central-1"
    listed_services.append(ServiceRecord(service_id="svc-2", name="analytics"))

    fresh_services = repository.list_services()

    assert len(fresh_services) == 1
    assert fresh_services[0].tags == ["core"]
    assert fresh_services[0].metadata == {"region": "us-west-2"}


def test_domain_service_list_services_returns_detached_records() -> None:
    repository = ServiceRepository(
        [
            ServiceRecord(
                service_id="svc-1",
                name="billing",
                tags=["core"],
                metadata={"region": "us-west-2"},
            )
        ]
    )
    service = DomainService(repository)

    listed_services = service.list_services()
    listed_services[0].name = "mutated"
    listed_services[0].tags.append("mutated")
    listed_services[0].metadata["region"] = "eu-central-1"

    fresh_services = service.list_services()
    repository_services = repository.list_services()

    assert fresh_services[0].name == "billing"
    assert fresh_services[0].tags == ["core"]
    assert fresh_services[0].metadata == {"region": "us-west-2"}
    assert repository_services[0].name == "billing"


def test_create_todo_trims_title_and_assigns_incrementing_ids() -> None:
    service = TodoService(repository=InMemoryTodoRepository())

    first = service.create_todo("  Ship release  ")
    second = service.create_todo("Stabilize retries")

    assert first.id == "1"
    assert first.title == "Ship release"
    assert second.id == "2"


def test_complete_todo_marks_item_done_with_timestamp() -> None:
    service = TodoService(repository=InMemoryTodoRepository())
    created = service.create_todo("Fix stale lock")

    completed = service.complete_todo(created.id)

    assert completed.completed is True
    assert completed.completed_at is not None


def test_create_todo_uses_next_numeric_id_from_existing_rows() -> None:
    repository = InMemoryTodoRepository()
    repository.put(TodoRecord(id="2", title="Existing task"))
    repository.put(TodoRecord(id="7", title="Another task"))
    repository.put(TodoRecord(id="legacy", title="Imported task"))
    service = TodoService(repository=repository)

    created = service.create_todo("New task")

    assert created.id == "8"


def test_complete_todo_raises_for_unknown_id() -> None:
    service = TodoService(repository=InMemoryTodoRepository())

    with pytest.raises(KeyError):
        service.complete_todo("404")
