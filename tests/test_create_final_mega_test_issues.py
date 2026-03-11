from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "create_final_mega_test_issues.py"
    spec = importlib.util.spec_from_file_location("create_final_mega_test_issues", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_run_campaign_validates_then_creates_with_sleep_between_waves() -> None:
    module = _load_module()
    calls: list[list[str]] = []
    sleeps: list[float] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return object()

    module.run_campaign(
        ready_label="healer:ready",
        sleep_seconds=180,
        extra_labels=("difficulty:mega",),
        runner=fake_run,
        sleeper=sleeps.append,
    )

    assert len(calls) == 4
    assert calls[0][-1] == "--dry-run"
    assert calls[1][-1] == "--dry-run"
    assert "--dry-run" not in calls[2]
    assert "--dry-run" not in calls[3]
    assert "mega-final-wave-1" in calls[0]
    assert "mega-final-wave-2" in calls[1]
    assert sleeps == [180]


def test_wave_command_includes_campaign_and_wave_labels() -> None:
    module = _load_module()
    cmd = module._wave_command(
        family="mega-final-wave-1",
        prefix="Mega final sandbox wave 1",
        ready_label="healer:ready",
        extra_labels=("campaign:mega-final", "wave:1"),
        dry_run=True,
    )

    assert "--family" in cmd
    assert "mega-final-wave-1" in cmd
    assert cmd.count("--extra-label") == 2
    assert "--dry-run" in cmd
