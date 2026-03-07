from __future__ import annotations

from flow_healer.apple_pollers import (
    CalendarCommandEvent,
    CalendarCommandPoller,
    MailCommandMessage,
    MailCommandPoller,
)
from flow_healer.config import CalendarControlSettings, MailControlSettings


class _FakeRouter:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def execute(self, *, request, source: str, external_id: str, sender: str):
        self.calls.append(
            {
                "command": request.command,
                "source": source,
                "external_id": external_id,
                "sender": sender,
            }
        )
        return {"ok": True}


class _FakeMailAdapter:
    def __init__(self, messages: list[MailCommandMessage]) -> None:
        self.messages = messages
        self.read_ids: list[str] = []
        self.replies: list[str] = []

    def list_unread_messages(self, *, account: str, mailbox: str, limit: int = 30):
        return list(self.messages)

    def mark_as_read(self, *, account: str, mailbox: str, message_id: str) -> None:
        self.read_ids.append(message_id)

    def send_reply(self, *, recipient: str, subject: str, body: str) -> None:
        self.replies.append(recipient)


class _FakeCalendarAdapter:
    def __init__(self, events: list[CalendarCommandEvent]) -> None:
        self.events = events

    def list_command_events(self, *, calendar_name: str, lookback_minutes: int, lookahead_minutes: int, limit: int = 40):
        return list(self.events)


def test_mail_poller_handles_trusted_command() -> None:
    router = _FakeRouter()
    adapter = _FakeMailAdapter(
        [MailCommandMessage(message_id="m1", sender="Ops <dkyazze@icloud.com>", subject="FH: pause repo=demo")]
    )
    settings = MailControlSettings(
        enabled=True,
        account="dkyazze@icloud.com",
        mailbox="INBOX",
        trusted_senders=["dkyazze@icloud.com"],
        send_replies=False,
    )

    poller = MailCommandPoller(settings=settings, router=router, adapter=adapter)
    poller.poll_once()

    assert len(router.calls) == 1
    assert router.calls[0]["command"] == "pause"
    assert adapter.read_ids == ["m1"]


def test_mail_poller_ignores_untrusted_sender() -> None:
    router = _FakeRouter()
    adapter = _FakeMailAdapter(
        [MailCommandMessage(message_id="m2", sender="Attacker <bad@example.com>", subject="FH: pause repo=demo")]
    )
    settings = MailControlSettings(
        enabled=True,
        account="dkyazze@icloud.com",
        mailbox="INBOX",
        trusted_senders=["dkyazze@icloud.com"],
        send_replies=False,
    )

    poller = MailCommandPoller(settings=settings, router=router, adapter=adapter)
    poller.poll_once()

    assert router.calls == []
    assert adapter.read_ids == ["m2"]


def test_calendar_poller_routes_command_events() -> None:
    router = _FakeRouter()
    adapter = _FakeCalendarAdapter(
        [CalendarCommandEvent(uid="u1", start_text="2026-03-07 10:00", title="FH: resume repo=demo")]
    )
    settings = CalendarControlSettings(enabled=True, calendar_name="healer-cal")

    poller = CalendarCommandPoller(settings=settings, router=router, adapter=adapter)
    poller.poll_once()

    assert len(router.calls) == 1
    assert router.calls[0]["command"] == "resume"
    assert router.calls[0]["source"] == "calendar"
