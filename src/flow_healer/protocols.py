from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True, frozen=True)
class ConnectorTurnResult:
    output_text: str
    final_answer_present: bool = False
    commentary_tail: str = ""
    used_workspace_edit_mode: bool = False
    raw_event_kinds: tuple[str, ...] = ()


class ConnectorProtocol(Protocol):
    def get_or_create_thread(self, sender: str) -> str: ...

    def reset_thread(self, sender: str) -> str: ...

    def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str: ...

    def run_turn_detailed(
        self,
        thread_id: str,
        prompt: str,
        *,
        timeout_seconds: int | None = None,
    ) -> ConnectorTurnResult: ...

    def ensure_started(self) -> None: ...

    def shutdown(self) -> None: ...
