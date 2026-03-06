from __future__ import annotations

import asyncio

from flow_healer.config import AppConfig, RelaySettings, ServiceSettings
from flow_healer.store import SQLiteStore
from flow_healer.tui.app import FlowHealerTUI


def _make_config(tmp_path):
    return AppConfig(
        service=ServiceSettings(state_root=str(tmp_path)),
        repos=[
            RelaySettings(
                repo_name="demo",
                healer_repo_path=str(tmp_path / "repo"),
                healer_repo_slug="owner/demo",
            )
        ],
    )


def test_tui_boots_and_renders_fleet(tmp_path):
    config = _make_config(tmp_path)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    store = SQLiteStore(config.repo_db_path("demo"))
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="401",
        repo="owner/demo",
        title="Fix flaky test",
        body="Body text",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.update_runtime_status(status="idle", touch_heartbeat=True)
    store.close()

    async def _run() -> None:
        app = FlowHealerTUI(config)
        async with app.run_test() as pilot:
            await pilot.pause()
            fleet = app.query_one("#fleet-repos")
            summary = app.query_one("#fleet-summary")
            assert fleet.row_count == 1
            assert app.state.selected_repo == "demo"
            assert "Managed repos: 1" in str(summary.renderable)

    asyncio.run(_run())
