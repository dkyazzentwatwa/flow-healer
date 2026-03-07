from app.repository import ServiceRecord, ServiceRepository
from app.service import DomainService


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
