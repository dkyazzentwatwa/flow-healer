from app.api import HTTPException, complete_todo
from app.repository import TodoRecord, TodoRepository
from app.service import DomainService, TodoNotFoundError


def test_create_todo_trims_title_before_storing() -> None:
    service = DomainService(TodoRepository())

    created = service.create_todo("  ship patch  ")

    assert created.title == "ship patch"
    assert created.todo_id == "todo-1"
    assert created.completed is False


def test_create_todo_rejects_blank_title() -> None:
    service = DomainService(TodoRepository())

    try:
        service.create_todo("   ")
    except ValueError as exc:
        assert str(exc) == "Todo title must not be empty."
    else:
        raise AssertionError("Expected blank todo title to raise ValueError")


def test_complete_todo_marks_existing_record_complete() -> None:
    repository = TodoRepository([TodoRecord(todo_id="todo-9", title="ship patch")])
    service = DomainService(repository)

    completed = service.complete_todo("todo-9")

    assert completed.completed is True
    assert repository.get("todo-9") == completed


def test_complete_todo_raises_not_found_for_unknown_todo() -> None:
    service = DomainService(TodoRepository())

    try:
        service.complete_todo("todo-404")
    except TodoNotFoundError as exc:
        assert str(exc) == "Todo 'todo-404' was not found."
    else:
        raise AssertionError("Expected unknown todo completion to raise TodoNotFoundError")


def test_complete_todo_raises_not_found_when_lookup_cannot_find_todo() -> None:
    class MissingOnGetRepository(TodoRepository):
        def get(self, todo_id: str) -> TodoRecord | None:
            raise KeyError(todo_id)

    service = DomainService(MissingOnGetRepository())

    try:
        service.complete_todo("todo-404")
    except TodoNotFoundError as exc:
        assert str(exc) == "Todo 'todo-404' was not found."
    else:
        raise AssertionError("Expected lookup miss to raise TodoNotFoundError")


def test_complete_todo_raises_not_found_when_update_cannot_find_todo() -> None:
    class MissingOnUpdateRepository(TodoRepository):
        def get(self, todo_id: str) -> TodoRecord | None:
            return TodoRecord(todo_id=todo_id, title="ship patch")

        def update(self, updated_todo: TodoRecord) -> TodoRecord:
            raise KeyError(updated_todo.todo_id)

    service = DomainService(MissingOnUpdateRepository())

    try:
        service.complete_todo("todo-404")
    except TodoNotFoundError as exc:
        assert str(exc) == "Todo 'todo-404' was not found."
    else:
        raise AssertionError("Expected update miss to raise TodoNotFoundError")


def test_complete_todo_raises_not_found_when_update_returns_none() -> None:
    class MissingOnUpdateRepository(TodoRepository):
        def get(self, todo_id: str) -> TodoRecord | None:
            return TodoRecord(todo_id=todo_id, title="ship patch")

        def update(self, updated_todo: TodoRecord) -> TodoRecord:
            return None

    service = DomainService(MissingOnUpdateRepository())

    try:
        service.complete_todo("todo-404")
    except TodoNotFoundError as exc:
        assert str(exc) == "Todo 'todo-404' was not found."
    else:
        raise AssertionError("Expected empty update result to raise TodoNotFoundError")


def test_complete_todo_api_returns_not_found_for_unknown_todo() -> None:
    try:
        complete_todo("todo-404")
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "Todo 'todo-404' was not found."
    else:
        raise AssertionError("Expected API completion path to raise HTTPException")


def test_complete_todo_api_returns_not_found_when_service_returns_none() -> None:
    original_service = complete_todo.__globals__["service"]

    class MissingTodoService:
        def complete_todo(self, todo_id: str) -> None:
            return None

    complete_todo.__globals__["service"] = MissingTodoService()
    try:
        complete_todo("todo-404")
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "Todo 'todo-404' was not found."
    else:
        raise AssertionError("Expected missing API todo to raise HTTPException")
    finally:
        complete_todo.__globals__["service"] = original_service
