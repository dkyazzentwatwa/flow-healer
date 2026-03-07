from __future__ import annotations

import asyncio
import logging
from typing import Any

from .apple_pollers import CalendarCommandPoller, MailCommandPoller
from .config import AppConfig, RelaySettings
from .control_plane import ControlRouter
from .service import FlowHealerService
from .web_dashboard import DashboardServer

logger = logging.getLogger("apple_flow.serve_runtime")


class FlowHealerServeRuntime:
    def __init__(
        self,
        *,
        config: AppConfig,
        service: FlowHealerService,
        repo_name: str | None,
        host: str | None,
        port: int | None,
    ) -> None:
        self.config = config
        self.service = service
        self.repo_name = repo_name
        self.host = host or config.control.web.host
        self.port = int(port or config.control.web.port)

    async def run(self) -> None:
        repos = self.service.config.select_repos(self.repo_name)
        runtimes = [self.service.build_runtime(repo) for repo in repos]
        stop_event = asyncio.Event()
        router = ControlRouter(config=self.config, service=self.service, shutdown_hook=stop_event.set)

        tasks: list[asyncio.Task[Any]] = []
        for runtime in runtimes:
            tasks.append(asyncio.create_task(runtime.loop.run_forever(stop_event.is_set), name=f"healer:{runtime.settings.repo_name}"))

        web_server: DashboardServer | None = None
        if self.config.control.web.enabled:
            web_server = DashboardServer(
                config=self.config,
                service=self.service,
                router=router,
                host=self.host,
                port=self.port,
            )
            web_server.start()
            logger.info("Flow Healer web dashboard listening on http://%s:%s", self.host, self.port)

        if self.config.control.mail.enabled:
            mail_poller = MailCommandPoller(settings=self.config.control.mail, router=router)
            tasks.append(asyncio.create_task(mail_poller.run_forever(stop_event), name="poller:mail"))
            logger.info("Mail poller enabled for account '%s'", self.config.control.mail.account)

        if self.config.control.calendar.enabled:
            calendar_poller = CalendarCommandPoller(settings=self.config.control.calendar, router=router)
            tasks.append(asyncio.create_task(calendar_poller.run_forever(stop_event), name="poller:calendar"))
            logger.info("Calendar poller enabled for calendar '%s'", self.config.control.calendar.calendar_name)

        try:
            await stop_event.wait()
        finally:
            stop_event.set()
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if web_server is not None:
                web_server.stop()
            for runtime in runtimes:
                runtime.store.close()


def run_serve(
    *,
    config: AppConfig,
    service: FlowHealerService,
    repo_name: str | None,
    host: str | None,
    port: int | None,
) -> None:
    runtime = FlowHealerServeRuntime(
        config=config,
        service=service,
        repo_name=repo_name,
        host=host,
        port=port,
    )
    try:
        asyncio.run(runtime.run())
    except KeyboardInterrupt:
        logger.info("Flow Healer serve interrupted by user.")
