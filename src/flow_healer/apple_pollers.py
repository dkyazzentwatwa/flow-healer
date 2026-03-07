from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import re
import subprocess
from typing import Iterable

from .config import CalendarControlSettings, MailControlSettings
from .control_plane import ControlRouter, parse_command_subject

logger = logging.getLogger("apple_flow.apple_pollers")


@dataclass(slots=True)
class MailCommandMessage:
    message_id: str
    sender: str
    subject: str


@dataclass(slots=True)
class CalendarCommandEvent:
    uid: str
    start_text: str
    title: str


class AppleScriptMailAdapter:
    def list_unread_messages(self, *, account: str, mailbox: str, limit: int = 30) -> list[MailCommandMessage]:
        safe_account = _as_string_literal(account)
        safe_mailbox = _as_string_literal(mailbox)
        script = [
            'tell application "Mail"',
            f'if not (exists account {safe_account}) then return ""',
            f'set targetMailbox to mailbox {safe_mailbox} of account {safe_account}',
            'set outRows to {}',
            'set unreadMessages to (every message of targetMailbox whose read status is false)',
            'repeat with msg in unreadMessages',
            'set mid to message id of msg as text',
            'set msgSender to sender of msg as text',
            'set msgSubj to subject of msg as text',
            'set end of outRows to mid & tab & msgSender & tab & msgSubj',
            'end repeat',
            'if (count of outRows) is 0 then return ""',
            "set AppleScript's text item delimiters to linefeed",
            'return outRows as text',
            'end tell',
        ]
        raw = _run_osascript(script)
        rows: list[MailCommandMessage] = []
        for line in raw.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            message_id, sender, subject = (item.strip() for item in parts)
            if not message_id:
                continue
            rows.append(MailCommandMessage(message_id=message_id, sender=sender, subject=subject))
            if len(rows) >= max(1, int(limit)):
                break
        return rows

    def mark_as_read(self, *, account: str, mailbox: str, message_id: str) -> None:
        safe_account = _as_string_literal(account)
        safe_mailbox = _as_string_literal(mailbox)
        safe_id = _as_string_literal(message_id)
        script = [
            'tell application "Mail"',
            f'if not (exists account {safe_account}) then return',
            f'set targetMailbox to mailbox {safe_mailbox} of account {safe_account}',
            f'set targetMessages to (every message of targetMailbox whose message id is {safe_id})',
            'repeat with msg in targetMessages',
            'set read status of msg to true',
            'end repeat',
            'end tell',
        ]
        _run_osascript(script)

    def send_reply(self, *, recipient: str, subject: str, body: str) -> None:
        safe_recipient = _as_string_literal(recipient)
        safe_subject = _as_string_literal(subject[:180])
        safe_body = _as_string_literal(body[:2000])
        script = [
            'tell application "Mail"',
            f'set newMessage to make new outgoing message with properties {{subject:{safe_subject}, content:{safe_body} & return & return, visible:false}}',
            'tell newMessage',
            f'make new to recipient at end of to recipients with properties {{address:{safe_recipient}}}',
            'send',
            'end tell',
            'end tell',
        ]
        _run_osascript(script)


class AppleScriptCalendarAdapter:
    def list_command_events(
        self,
        *,
        calendar_name: str,
        lookback_minutes: int,
        lookahead_minutes: int,
        limit: int = 40,
    ) -> list[CalendarCommandEvent]:
        safe_calendar = _as_string_literal(calendar_name)
        back = max(0, int(lookback_minutes))
        ahead = max(1, int(lookahead_minutes))
        script = [
            'tell application "Calendar"',
            f'if not (exists calendar {safe_calendar}) then return ""',
            f'set targetCalendar to calendar {safe_calendar}',
            'set nowDate to current date',
            f'set startWindow to nowDate - ({back} * minutes)',
            f'set endWindow to nowDate + ({ahead} * minutes)',
            'set outRows to {}',
            'set eventsList to (every event of targetCalendar whose start date >= startWindow and start date <= endWindow)',
            'repeat with ev in eventsList',
            'set eid to uid of ev as text',
            'set estart to start date of ev as text',
            'set etitle to summary of ev as text',
            'set end of outRows to eid & tab & estart & tab & etitle',
            'end repeat',
            'if (count of outRows) is 0 then return ""',
            "set AppleScript's text item delimiters to linefeed",
            'return outRows as text',
            'end tell',
        ]
        raw = _run_osascript(script)
        rows: list[CalendarCommandEvent] = []
        for line in raw.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            uid, start_text, title = (item.strip() for item in parts)
            if not uid:
                continue
            rows.append(CalendarCommandEvent(uid=uid, start_text=start_text, title=title))
            if len(rows) >= max(1, int(limit)):
                break
        return rows


class MailCommandPoller:
    def __init__(
        self,
        *,
        settings: MailControlSettings,
        router: ControlRouter,
        adapter: AppleScriptMailAdapter | None = None,
    ) -> None:
        self.settings = settings
        self.router = router
        self.adapter = adapter or AppleScriptMailAdapter()

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        interval = max(5.0, float(self.settings.poll_interval_seconds))
        while not stop_event.is_set():
            try:
                await asyncio.to_thread(self.poll_once)
            except Exception as exc:
                logger.warning("Mail command poll failed: %s", exc)
            await asyncio.sleep(interval)

    def poll_once(self) -> None:
        if not self.settings.enabled:
            return
        if not self.settings.account.strip():
            return

        trusted = {item.strip().lower() for item in self.settings.trusted_senders if item.strip()}
        messages = self.adapter.list_unread_messages(
            account=self.settings.account,
            mailbox=self.settings.mailbox,
            limit=30,
        )

        for message in messages:
            sender_email = _extract_email(message.sender)
            try:
                parsed = parse_command_subject(message.subject, prefix=self.settings.subject_prefix)
            except Exception as exc:
                logger.warning("Failed to parse mail command subject '%s': %s", message.subject, exc)
                continue
            if parsed is None:
                continue

            if trusted and sender_email not in trusted:
                logger.warning("Ignoring mail command from untrusted sender: %s", message.sender)
                self.adapter.mark_as_read(
                    account=self.settings.account,
                    mailbox=self.settings.mailbox,
                    message_id=message.message_id,
                )
                continue

            result = self.router.execute(
                request=parsed,
                source="mail",
                external_id=f"mail:{message.message_id}",
                sender=sender_email,
            )
            self.adapter.mark_as_read(
                account=self.settings.account,
                mailbox=self.settings.mailbox,
                message_id=message.message_id,
            )
            if self.settings.send_replies and sender_email:
                status = "OK" if result.get("ok") else "ERROR"
                body = f"Flow Healer command: {message.subject}\nStatus: {status}\nResult: {result}"
                try:
                    self.adapter.send_reply(
                        recipient=sender_email,
                        subject=f"Flow Healer [{status}] {parsed.command}",
                        body=body,
                    )
                except Exception as exc:
                    logger.warning("Failed to send mail reply: %s", exc)


class CalendarCommandPoller:
    def __init__(
        self,
        *,
        settings: CalendarControlSettings,
        router: ControlRouter,
        adapter: AppleScriptCalendarAdapter | None = None,
    ) -> None:
        self.settings = settings
        self.router = router
        self.adapter = adapter or AppleScriptCalendarAdapter()

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        interval = max(5.0, float(self.settings.poll_interval_seconds))
        while not stop_event.is_set():
            try:
                await asyncio.to_thread(self.poll_once)
            except Exception as exc:
                logger.warning("Calendar command poll failed: %s", exc)
            await asyncio.sleep(interval)

    def poll_once(self) -> None:
        if not self.settings.enabled:
            return
        events = self.adapter.list_command_events(
            calendar_name=self.settings.calendar_name,
            lookback_minutes=self.settings.lookback_minutes,
            lookahead_minutes=self.settings.lookahead_minutes,
            limit=30,
        )

        for event in events:
            try:
                parsed = parse_command_subject(event.title, prefix=self.settings.subject_prefix)
            except Exception as exc:
                logger.warning("Failed to parse calendar command '%s': %s", event.title, exc)
                continue
            if parsed is None:
                continue
            external_id = f"calendar:{event.uid}:{event.start_text}"
            self.router.execute(
                request=parsed,
                source="calendar",
                external_id=external_id,
                sender=self.settings.calendar_name,
            )


def _run_osascript(lines: Iterable[str], *, timeout: int = 20) -> str:
    cmd = ["osascript"]
    for line in lines:
        cmd.extend(["-e", line])
    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or f"osascript exited {proc.returncode}").strip()
        raise RuntimeError(err)
    return (proc.stdout or "").strip()


def _as_string_literal(value: str) -> str:
    text = (value or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _extract_email(sender: str) -> str:
    text = (sender or "").strip().lower()
    if not text:
        return ""
    match = re.search(r"<([^>]+)>", text)
    if match:
        return match.group(1).strip().lower()
    if "@" in text and " " not in text:
        return text
    return text
