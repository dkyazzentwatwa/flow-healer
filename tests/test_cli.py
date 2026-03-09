from pathlib import Path

from flow_healer import cli
from flow_healer.cli import build_parser


def test_doctor_parser_accepts_preflight_flag() -> None:
    parser = build_parser()

    args = parser.parse_args(["doctor", "--preflight"])

    assert args.command == "doctor"
    assert args.preflight is True


def test_recycle_helpers_parser_accepts_idle_only_flag() -> None:
    parser = build_parser()

    args = parser.parse_args(["recycle-helpers", "--repo", "demo", "--idle-only"])

    assert args.command == "recycle-helpers"
    assert args.repo == "demo"
    assert args.idle_only is True


def test_main_start_once_uses_service_start(monkeypatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    class DummyService:
        def __init__(self, _config) -> None:
            pass

        def start(self, repo_name, *, once: bool = False) -> None:
            called["repo_name"] = repo_name
            called["once"] = once

    monkeypatch.setattr(cli, "FlowHealerService", DummyService)
    monkeypatch.setattr(cli.AppConfig, "load", classmethod(lambda cls, _path: object()))
    monkeypatch.setattr(cli, "_configure_logging", lambda _config: None)
    monkeypatch.setattr(cli, "run_serve", lambda **kwargs: called.setdefault("run_serve", kwargs))
    monkeypatch.setattr("sys.argv", ["flow-healer", "--config", str(tmp_path / "config.yaml"), "start", "--once", "--repo", "demo"])

    cli.main()

    assert called["repo_name"] == "demo"
    assert called["once"] is True
    assert "run_serve" not in called


def test_main_start_without_once_uses_serve_runtime(monkeypatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    class DummyService:
        def __init__(self, config) -> None:
            called["service_config"] = config
            called["service_instance"] = self

        def start(self, repo_name, *, once: bool = False) -> None:
            called["service_start"] = {"repo_name": repo_name, "once": once}

    config_obj = object()

    monkeypatch.setattr(cli, "FlowHealerService", DummyService)
    monkeypatch.setattr(cli.AppConfig, "load", classmethod(lambda cls, _path: config_obj))
    monkeypatch.setattr(cli, "_configure_logging", lambda _config: None)
    monkeypatch.setattr(cli, "run_serve", lambda **kwargs: called.setdefault("run_serve", kwargs))
    monkeypatch.setattr("sys.argv", ["flow-healer", "--config", str(tmp_path / "config.yaml"), "start", "--repo", "demo"])

    cli.main()

    assert "service_start" not in called
    assert called["run_serve"] == {
        "config": config_obj,
        "service": called["service_instance"],
        "repo_name": "demo",
        "host": None,
        "port": None,
    }
