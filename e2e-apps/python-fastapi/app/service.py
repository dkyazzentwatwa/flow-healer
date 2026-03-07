from __future__ import annotations

from copy import deepcopy

from app.repository import ServiceRecord, ServiceRepository


class DomainService:
    def __init__(self, repository: ServiceRepository) -> None:
        self._repository = repository

    def list_services(self) -> list[ServiceRecord]:
        return deepcopy(self._repository.list_services())
