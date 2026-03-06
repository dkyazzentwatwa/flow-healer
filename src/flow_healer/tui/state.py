from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

try:
    from enum import StrEnum
except ImportError:
    class StrEnum(str, Enum):
        pass


class WorkspaceId(StrEnum):
    FLEET = "fleet"
    REPO = "repo"
    ISSUES = "issues"
    ATTEMPTS = "attempts"
    SCANS = "scans"
    AUDIT = "audit"


@dataclass(slots=True)
class TUIState:
    selected_repo: str = ""
    issue_state_filter: str = ""
    selected_issue_id: str = ""
    selected_attempt_id: str = ""
