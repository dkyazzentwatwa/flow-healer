from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ServiceRecord:
    service_id: str
    name: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ServiceRepository:
    def __init__(self, services: list[ServiceRecord] | None = None) -> None:
        self._services = deepcopy(services) if services is not None else []

    def add(self, service: ServiceRecord) -> ServiceRecord:
        stored_service = deepcopy(service)
        self._services.append(stored_service)
        return deepcopy(stored_service)

    def list_services(self) -> list[ServiceRecord]:
        return deepcopy(self._services)
