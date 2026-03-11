from __future__ import annotations

from app.reporting import generate_report
from app.service import TodoService


def test_generate_report_summarizes_todo_state() -> None:
    service = TodoService()
    first = service.create_todo("Ship release")
    second = service.create_todo("Document API")
    service.complete_todo(second.id)

    report = generate_report(service)

    assert report["summary"] == {
        "total": 2,
        "completed": 1,
        "pending": 1,
        "completion_rate": 0.5,
        "last_completed_at": report["todos"][1]["completed_at"],
    }
    assert report["todos"] == [
        {
            "id": first.id,
            "title": "Ship release",
            "completed": False,
            "completed_at": None,
        },
        {
            "id": second.id,
            "title": "Document API",
            "completed": True,
            "completed_at": report["todos"][1]["completed_at"],
        },
    ]
    assert isinstance(report["generated_at"], str)
    assert report["todos"][1]["completed_at"] is not None


def test_generate_report_handles_empty_state() -> None:
    report = generate_report(TodoService())

    assert report["summary"] == {
        "total": 0,
        "completed": 0,
        "pending": 0,
        "completion_rate": 0.0,
        "last_completed_at": None,
    }
    assert report["todos"] == []
    assert isinstance(report["generated_at"], str)


def test_generate_report_uses_latest_completed_timestamp_in_summary() -> None:
    service = TodoService()
    first = service.create_todo("Prepare report")
    second = service.create_todo("Review report")

    completed_first = service.complete_todo(first.id)
    completed_second = service.complete_todo(second.id)

    report = generate_report(service)

    assert completed_first.completed_at is not None
    assert completed_second.completed_at is not None
    assert report["summary"]["last_completed_at"] == max(
        completed_first.completed_at,
        completed_second.completed_at,
    )
