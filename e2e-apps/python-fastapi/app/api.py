from __future__ import annotations

from typing import Any, Callable


class _Route:
    def __init__(self, path: str, endpoint: Callable[[], dict[str, str]]) -> None:
        self.path = path
        self.endpoint = endpoint


class _FallbackFastAPI:
    def __init__(self) -> None:
        self.routes: list[_Route] = []

    def get(self, path: str) -> Callable[[Callable[[], dict[str, str]]], Callable[[], dict[str, str]]]:
        def decorator(func: Callable[[], dict[str, str]]) -> Callable[[], dict[str, str]]:
            self.routes.append(_Route(path=path, endpoint=func))
            return func

        return decorator


try:
    from fastapi import FastAPI
except ImportError:  # pragma: no cover - exercised only in lightweight sandbox environments.
    FastAPI = _FallbackFastAPI  # type: ignore[assignment]


app = FastAPI()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
