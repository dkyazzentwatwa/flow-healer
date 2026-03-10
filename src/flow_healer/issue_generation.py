from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


_PROSPER_CHAT_ROOT = "e2e-apps/prosper-chat"
_PROSPER_CHAT_SQL_PREFIXES = (
    f"{_PROSPER_CHAT_ROOT}/supabase/migrations/",
    f"{_PROSPER_CHAT_ROOT}/supabase/assertions/",
)
_PROSPER_CHAT_BACKEND_PREFIX = f"{_PROSPER_CHAT_ROOT}/supabase/functions/"
_PROSPER_CHAT_DB_COMMAND = "./scripts/healer_validate.sh db"
_PROSPER_CHAT_BACKEND_COMMAND = "./scripts/healer_validate.sh backend"
_PROSPER_CHAT_FULL_COMMAND = "./scripts/healer_validate.sh full"
_SQL_TITLE_HINTS = ("migration", "rls", "policy", "constraint", "trigger", "function", "sql")


@dataclass(frozen=True, slots=True)
class IssueTemplate:
    kind: str
    targets: tuple[str, ...]
    validation_command: str
    labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IssueDraft:
    title: str
    body: str
    labels: tuple[str, ...]


DEFAULT_FAMILY = "default"
PROSPER_CHAT_DB_FAMILY = "prosper-chat-db"


def available_issue_families() -> tuple[str, ...]:
    return (DEFAULT_FAMILY, PROSPER_CHAT_DB_FAMILY)


def select_validation_command(
    *,
    title: str,
    targets: Sequence[str],
    default_command: str,
) -> str:
    normalized_targets = tuple(_normalize_path(target) for target in targets if _normalize_path(target))
    if _is_sql_only_prosper_chat_target_set(normalized_targets):
        return _PROSPER_CHAT_DB_COMMAND
    if _is_backend_only_prosper_chat_target_set(normalized_targets):
        return _PROSPER_CHAT_BACKEND_COMMAND
    if normalized_targets and all(target.startswith(f"{_PROSPER_CHAT_ROOT}/") for target in normalized_targets):
        return _PROSPER_CHAT_FULL_COMMAND
    normalized_title = str(title or "").strip().lower()
    if normalized_title.startswith("prosper chat") and any(hint in normalized_title for hint in _SQL_TITLE_HINTS):
        return _PROSPER_CHAT_DB_COMMAND
    return str(default_command or "").strip()


def build_issue_drafts(
    *,
    count: int,
    prefix: str,
    ready_label: str,
    extra_labels: Sequence[str] = (),
    family: str = DEFAULT_FAMILY,
) -> list[IssueDraft]:
    templates = get_issue_templates(family)
    if not templates:
        return []

    normalized_ready = str(ready_label or "").strip()
    shared_labels = tuple(_dedupe_labels([normalized_ready, *extra_labels]))
    drafts: list[IssueDraft] = []
    for index in range(count):
        template = templates[index % len(templates)]
        title = f"{prefix} {index + 1}: {template.kind}".strip()
        validation = select_validation_command(
            title=title,
            targets=template.targets,
            default_command=template.validation_command,
        )
        body = render_issue_body(template.targets, validation)
        labels = tuple(_dedupe_labels([*shared_labels, *template.labels]))
        drafts.append(IssueDraft(title=title, body=body, labels=labels))
    return drafts


def render_issue_body(targets: Sequence[str], validation_command: str) -> str:
    body = "Required code outputs:\n"
    for target in targets:
        body += f"- {target}\n"
    body += "\nValidation:\n"
    body += f"- {validation_command}\n"
    return body


def get_issue_templates(family: str) -> tuple[IssueTemplate, ...]:
    normalized_family = str(family or DEFAULT_FAMILY).strip().lower() or DEFAULT_FAMILY
    if normalized_family == DEFAULT_FAMILY:
        return _default_templates()
    if normalized_family == PROSPER_CHAT_DB_FAMILY:
        return _prosper_chat_db_templates()
    raise ValueError(
        f"unknown issue family '{family}'. Available families: {', '.join(available_issue_families())}"
    )


def _default_templates() -> tuple[IssueTemplate, ...]:
    return (
        IssueTemplate(
            kind="Node smoke regression",
            targets=(
                "e2e-smoke/node/src/add.js",
                "e2e-smoke/node/test/add.test.js",
            ),
            validation_command="cd e2e-smoke/node && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="Python smoke regression",
            targets=(
                "e2e-smoke/python/smoke_math.py",
                "e2e-smoke/python/tests/test_smoke_math.py",
            ),
            validation_command="cd e2e-smoke/python && pytest -q",
        ),
        IssueTemplate(
            kind="Node app regression",
            targets=(
                "e2e-apps/node-next/lib/todo-service.js",
                "e2e-apps/node-next/tests/todo-service.test.js",
            ),
            validation_command="cd e2e-apps/node-next && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="FastAPI app regression",
            targets=(
                "e2e-apps/python-fastapi/app/service.py",
                "e2e-apps/python-fastapi/tests/test_domain_service.py",
            ),
            validation_command="cd e2e-apps/python-fastapi && pytest -q",
        ),
    )


def _prosper_chat_db_templates() -> tuple[IssueTemplate, ...]:
    return (
        IssueTemplate(
            kind="Prosper chat DB: schema core inventory stays aligned",
            targets=(
                "e2e-apps/prosper-chat/supabase/assertions/schema_core.sql",
                "e2e-apps/prosper-chat/supabase/assertions/manifest.json",
            ),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            labels=("area:db", "kind:migration", "difficulty:easy"),
        ),
        IssueTemplate(
            kind="Prosper chat DB: policy core audit stays current",
            targets=(
                "e2e-apps/prosper-chat/supabase/assertions/policies_core.sql",
                "e2e-apps/prosper-chat/supabase/assertions/manifest.json",
            ),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            labels=("area:db", "kind:rls", "difficulty:easy"),
        ),
        IssueTemplate(
            kind="Prosper chat DB: anon access tightening remains enforced",
            targets=(
                "e2e-apps/prosper-chat/supabase/migrations/20260302101500_7f8d9de2-cb2b-4f35-b3b8-6d8a8f519e7e.sql",
                "e2e-apps/prosper-chat/supabase/assertions/anon_access_controls.sql",
            ),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            labels=("area:db", "kind:rls", "difficulty:medium"),
        ),
        IssueTemplate(
            kind="Prosper chat DB: subscription visibility stays owner-scoped",
            targets=(
                "e2e-apps/prosper-chat/supabase/migrations/20260301204622_64bd8908-fa0d-4f2c-b120-e7990f38b3b5.sql",
                "e2e-apps/prosper-chat/supabase/assertions/subscription_visibility.sql",
            ),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            labels=("area:db", "kind:rls", "difficulty:medium"),
        ),
        IssueTemplate(
            kind="Prosper chat DB: appointment overlap trigger remains strict",
            targets=(
                "e2e-apps/prosper-chat/supabase/migrations/20260302101500_7f8d9de2-cb2b-4f35-b3b8-6d8a8f519e7e.sql",
                "e2e-apps/prosper-chat/supabase/assertions/appointment_overlap.sql",
            ),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            labels=("area:db", "kind:migration", "difficulty:hard"),
        ),
        IssueTemplate(
            kind="Prosper chat DB: business settings uniqueness and read policy stay aligned",
            targets=(
                "e2e-apps/prosper-chat/supabase/migrations/20260301231107_2211767c-e102-4928-9255-3b2485c9a7da.sql",
                "e2e-apps/prosper-chat/supabase/migrations/20260301232528_b0ffb806-d185-4b4f-9e43-f3d11f7fc6d1.sql",
            ),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            labels=("area:db", "kind:rls", "difficulty:medium"),
        ),
        IssueTemplate(
            kind="Prosper chat DB: business widget bootstrap policy removal stays complete",
            targets=(
                "e2e-apps/prosper-chat/supabase/migrations/20260301191219_12a9fc3b-2784-49fe-bf78-85c589c9c5d6.sql",
                "e2e-apps/prosper-chat/supabase/migrations/20260302101500_7f8d9de2-cb2b-4f35-b3b8-6d8a8f519e7e.sql",
            ),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            labels=("area:db", "kind:rls", "difficulty:medium"),
        ),
        IssueTemplate(
            kind="Prosper chat DB: admin lead visibility policies remain explicit",
            targets=(
                "e2e-apps/prosper-chat/supabase/migrations/20260301194245_274d9402-9bfe-4be6-84e2-0c36a5e6170c.sql",
                "e2e-apps/prosper-chat/supabase/assertions/policies_core.sql",
            ),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            labels=("area:db", "kind:rls", "difficulty:medium"),
        ),
        IssueTemplate(
            kind="Prosper chat DB: bot widget schema and policies stay connected",
            targets=(
                "e2e-apps/prosper-chat/supabase/migrations/20260301222424_81f2b260-db82-49bf-a1b6-30686117ac83.sql",
                "e2e-apps/prosper-chat/supabase/assertions/schema_core.sql",
            ),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            labels=("area:db", "kind:migration", "difficulty:medium"),
        ),
        IssueTemplate(
            kind="Prosper chat DB: owner-managed subscription inserts stay consistent",
            targets=(
                "e2e-apps/prosper-chat/supabase/migrations/20260301215513_a3f9ada2-3230-44bf-a5ef-90d631a3961c.sql",
                "e2e-apps/prosper-chat/supabase/assertions/subscription_visibility.sql",
            ),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            labels=("area:db", "kind:migration", "difficulty:medium"),
        ),
        IssueTemplate(
            kind="Prosper chat DB: anon insert policy business checks stay valid",
            targets=(
                "e2e-apps/prosper-chat/supabase/migrations/20260301190632_b724118b-66cd-45a5-9299-6eb6fe3e9690.sql",
                "e2e-apps/prosper-chat/supabase/assertions/anon_access_controls.sql",
            ),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            labels=("area:db", "kind:rls", "difficulty:hard"),
        ),
        IssueTemplate(
            kind="Prosper chat DB: base schema helper functions remain complete",
            targets=(
                "e2e-apps/prosper-chat/supabase/migrations/20260301190615_15638062-0f7f-4cc7-96f5-79466e4cb26b.sql",
                "e2e-apps/prosper-chat/supabase/assertions/schema_core.sql",
            ),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            labels=("area:db", "kind:migration", "difficulty:hard"),
        ),
    )


def _is_sql_only_prosper_chat_target_set(targets: Sequence[str]) -> bool:
    return bool(targets) and all(_is_prosper_chat_sql_target(target) for target in targets)


def _is_backend_only_prosper_chat_target_set(targets: Sequence[str]) -> bool:
    return bool(targets) and all(_is_prosper_chat_backend_target(target) for target in targets)


def _is_prosper_chat_sql_target(target: str) -> bool:
    normalized = _normalize_path(target)
    return any(normalized.startswith(prefix) for prefix in _PROSPER_CHAT_SQL_PREFIXES)


def _is_prosper_chat_backend_target(target: str) -> bool:
    normalized = _normalize_path(target)
    return normalized.startswith(_PROSPER_CHAT_BACKEND_PREFIX)


def _normalize_path(path: str) -> str:
    return str(path or "").strip().lstrip("./")


def _dedupe_labels(labels: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in labels:
        label = str(raw or "").strip()
        if not label:
            continue
        lowered = label.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(label)
    return deduped
