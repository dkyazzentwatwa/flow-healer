from __future__ import annotations

from flow_healer.config import AppConfig, RelaySettings, ServiceSettings
from flow_healer.control_plane import ControlRouter, parse_command_subject
from flow_healer.service import FlowHealerService
from flow_healer.store import SQLiteStore


def _make_service(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    config = AppConfig(
        service=ServiceSettings(state_root=str(tmp_path / "state")),
        repos=[
            RelaySettings(
                repo_name="demo",
                healer_repo_path=str(repo_path),
                healer_repo_slug="owner/repo",
            )
        ],
    )
    return config, FlowHealerService(config)


def test_parse_command_subject_supports_dsl() -> None:
    parsed = parse_command_subject("FH: scan repo=demo dry_run=true", prefix="FH:")

    assert parsed is not None
    assert parsed.command == "scan"
    assert parsed.repo == "demo"
    assert parsed.args["dry_run"] == "true"


def test_router_executes_and_dedupes(tmp_path) -> None:
    config, service = _make_service(tmp_path)
    router = ControlRouter(config=config, service=service)

    request = parse_command_subject("FH: pause repo=demo", prefix="FH:")
    assert request is not None

    first = router.execute(
        request=request,
        source="mail",
        external_id="mail:msg-1",
        sender="dkyazze@icloud.com",
    )
    duplicate = router.execute(
        request=request,
        source="mail",
        external_id="mail:msg-1",
        sender="dkyazze@icloud.com",
    )

    assert first["ok"] is True
    assert duplicate["duplicate"] is True

    store = SQLiteStore(config.repo_db_path("demo"))
    store.bootstrap()
    assert store.get_state("healer_paused") == "true"
    rows = store.list_control_commands(limit=20)
    store.close()

    assert len(rows) == 1
    assert rows[0]["parsed_command"] == "pause"
    assert rows[0]["status"] == "succeeded"


def test_router_records_failures(tmp_path) -> None:
    config, service = _make_service(tmp_path)
    router = ControlRouter(config=config, service=service)

    request = parse_command_subject("FH: unsupported repo=demo", prefix="FH:")
    assert request is not None

    result = router.execute(
        request=request,
        source="calendar",
        external_id="calendar:evt-1",
        sender="healer-cal",
    )

    assert result["ok"] is False

    store = SQLiteStore(config.repo_db_path("demo"))
    store.bootstrap()
    rows = store.list_control_commands(limit=20)
    store.close()

    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    assert rows[0]["parsed_command"] == "unsupported"
