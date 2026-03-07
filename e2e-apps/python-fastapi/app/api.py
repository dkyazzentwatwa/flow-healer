from __future__ import annotations

from dataclasses import asdict, dataclass

from app.repository import TodoRepository
from app.service import DomainService, TodoNotFoundError


class HTTPException(Exception):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class status:
    HTTP_201_CREATED = 201
    HTTP_404_NOT_FOUND = 404
    HTTP_422_UNPROCESSABLE_ENTITY = 422


class FastAPI:
    def post(self, _path: str, **_kwargs: object):
        def decorator(func):
            return func

        return decorator


@dataclass(slots=True)
class TodoCreateRequest:
    title: str


repository = TodoRepository()
service = DomainService(repository)
app = FastAPI()


@app.post("/todos", status_code=status.HTTP_201_CREATED)
def create_todo(payload: TodoCreateRequest) -> dict[str, object]:
    try:
        todo = service.create_todo(payload.title)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return asdict(todo)


@app.post("/todos/{todo_id}/complete")
def complete_todo(todo_id: str) -> dict[str, object]:
    try:
        todo = service.complete_todo(todo_id)
    except TodoNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Todo '{todo_id}' was not found.",
        ) from exc
    return asdict(todo)
