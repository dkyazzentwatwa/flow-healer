from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, Sequence

from .healer_task_spec import compile_task_spec


_PROSPER_CHAT_ROOT = "e2e-apps/prosper-chat"
_PROSPER_CHAT_SQL_PREFIXES = (
    f"{_PROSPER_CHAT_ROOT}/supabase/migrations/",
    f"{_PROSPER_CHAT_ROOT}/supabase/assertions/",
)
_PROSPER_CHAT_BACKEND_PREFIX = f"{_PROSPER_CHAT_ROOT}/supabase/functions/"
_PROSPER_CHAT_DB_COMMAND = f"cd {_PROSPER_CHAT_ROOT} && ./scripts/healer_validate.sh db"
_PROSPER_CHAT_BACKEND_COMMAND = f"cd {_PROSPER_CHAT_ROOT} && ./scripts/healer_validate.sh backend"
_PROSPER_CHAT_FULL_COMMAND = f"cd {_PROSPER_CHAT_ROOT} && ./scripts/healer_validate.sh full"
_SQL_TITLE_HINTS = ("migration", "rls", "policy", "constraint", "trigger", "function", "sql")
_RUNTIME_PROFILE_BY_ROOT = {
    "e2e-apps/node-next": "node-next-web",
    "e2e-apps/ruby-rails-web": "ruby-rails-web",
    "e2e-apps/java-spring-web": "java-spring-web",
}


@dataclass(frozen=True, slots=True)
class IssueTemplate:
    kind: str
    targets: tuple[str, ...]
    validation_command: str
    body: str = ""
    labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IssueDraft:
    title: str
    body: str
    labels: tuple[str, ...]


DEFAULT_FAMILY = "default"
PROSPER_CHAT_DB_FAMILY = "prosper-chat-db"
JS_FRAMEWORK_FAMILY = "js-frameworks"
PYTHON_FRAMEWORK_FAMILY = "python-frameworks"
PYTHON_DATA_ML_FAMILY = "python-data-ml"
MEGA_FINAL_WAVE_1_FAMILY = "mega-final-wave-1"
MEGA_FINAL_WAVE_2_FAMILY = "mega-final-wave-2"
PROD_EVAL_HYBRID_HEAVY_FAMILY = "prod-eval-hybrid-heavy"
HARD_NON_PROSPER_FAMILY = "hard-non-prosper"


def available_issue_families() -> tuple[str, ...]:
    return (
        DEFAULT_FAMILY,
        PROSPER_CHAT_DB_FAMILY,
        JS_FRAMEWORK_FAMILY,
        PYTHON_FRAMEWORK_FAMILY,
        PYTHON_DATA_ML_FAMILY,
        MEGA_FINAL_WAVE_1_FAMILY,
        MEGA_FINAL_WAVE_2_FAMILY,
        PROD_EVAL_HYBRID_HEAVY_FAMILY,
        HARD_NON_PROSPER_FAMILY,
    )


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
        body = template.body or render_issue_body(template.targets, validation)
        labels = tuple(_dedupe_labels([*shared_labels, *template.labels]))
        drafts.append(IssueDraft(title=title, body=body, labels=labels))
    return drafts


def render_issue_body(targets: Sequence[str], validation_command: str) -> str:
    return "\n".join(_contract_section_lines(targets=targets, validation=validation_command)) + "\n"


def get_issue_templates(family: str) -> tuple[IssueTemplate, ...]:
    normalized_family = str(family or DEFAULT_FAMILY).strip().lower() or DEFAULT_FAMILY
    if normalized_family == DEFAULT_FAMILY:
        return _default_templates()
    if normalized_family == PROSPER_CHAT_DB_FAMILY:
        return _prosper_chat_db_templates()
    if normalized_family == JS_FRAMEWORK_FAMILY:
        return _js_framework_templates()
    if normalized_family == PYTHON_FRAMEWORK_FAMILY:
        return _python_framework_templates()
    if normalized_family == PYTHON_DATA_ML_FAMILY:
        return _python_data_ml_templates()
    if normalized_family == MEGA_FINAL_WAVE_1_FAMILY:
        return _mega_final_wave_1_templates()
    if normalized_family == MEGA_FINAL_WAVE_2_FAMILY:
        return _mega_final_wave_2_templates()
    if normalized_family == PROD_EVAL_HYBRID_HEAVY_FAMILY:
        return _prod_eval_hybrid_heavy_templates()
    if normalized_family == HARD_NON_PROSPER_FAMILY:
        return _hard_non_prosper_templates()
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


def _js_framework_templates() -> tuple[IssueTemplate, ...]:
    return (
        IssueTemplate(
            kind="JS framework regression: Next.js service behavior",
            targets=(
                "e2e-smoke/js-next/src/add.js",
                "e2e-smoke/js-next/tests/add.test.js",
            ),
            validation_command="cd e2e-smoke/js-next && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: Vue (Vite) composable behavior",
            targets=(
                "e2e-smoke/js-vue-vite/src/add.js",
                "e2e-smoke/js-vue-vite/tests/add.test.js",
            ),
            validation_command="cd e2e-smoke/js-vue-vite && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: Nuxt server helper behavior",
            targets=(
                "e2e-smoke/js-nuxt/src/add.js",
                "e2e-smoke/js-nuxt/tests/add.test.js",
            ),
            validation_command="cd e2e-smoke/js-nuxt && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: Angular utility behavior",
            targets=(
                "e2e-smoke/js-angular/src/add.js",
                "e2e-smoke/js-angular/tests/add.test.js",
            ),
            validation_command="cd e2e-smoke/js-angular && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: SvelteKit module behavior",
            targets=(
                "e2e-smoke/js-sveltekit/src/add.js",
                "e2e-smoke/js-sveltekit/tests/add.test.js",
            ),
            validation_command="cd e2e-smoke/js-sveltekit && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: Express route helper behavior",
            targets=(
                "e2e-smoke/js-express/src/add.js",
                "e2e-smoke/js-express/tests/add.test.js",
            ),
            validation_command="cd e2e-smoke/js-express && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: Nest provider behavior",
            targets=(
                "e2e-smoke/js-nest/src/add.js",
                "e2e-smoke/js-nest/tests/add.test.js",
            ),
            validation_command="cd e2e-smoke/js-nest && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: Remix server helper behavior",
            targets=(
                "e2e-smoke/js-remix/app/utils/add.server.js",
                "e2e-smoke/js-remix/tests/add.test.js",
            ),
            validation_command="cd e2e-smoke/js-remix && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: Astro component helper behavior",
            targets=(
                "e2e-smoke/js-astro/src/utils/add.js",
                "e2e-smoke/js-astro/tests/add.test.js",
            ),
            validation_command="cd e2e-smoke/js-astro && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: SolidStart route helper behavior",
            targets=(
                "e2e-smoke/js-solidstart/src/lib/add.js",
                "e2e-smoke/js-solidstart/tests/add.test.js",
            ),
            validation_command="cd e2e-smoke/js-solidstart && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: Qwik utility behavior",
            targets=(
                "e2e-smoke/js-qwik/src/utils/add.ts",
                "e2e-smoke/js-qwik/tests/add.test.ts",
            ),
            validation_command="cd e2e-smoke/js-qwik && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: Hono handler behavior",
            targets=(
                "e2e-smoke/js-hono/src/add.js",
                "e2e-smoke/js-hono/tests/add.test.js",
            ),
            validation_command="cd e2e-smoke/js-hono && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: Koa middleware helper behavior",
            targets=(
                "e2e-smoke/js-koa/src/add.js",
                "e2e-smoke/js-koa/tests/add.test.js",
            ),
            validation_command="cd e2e-smoke/js-koa && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: Adonis service helper behavior",
            targets=(
                "e2e-smoke/js-adonis/app/services/add.ts",
                "e2e-smoke/js-adonis/tests/add.spec.ts",
            ),
            validation_command="cd e2e-smoke/js-adonis && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: RedwoodSDK helper behavior",
            targets=(
                "e2e-smoke/js-redwoodsdk/web/src/lib/add.ts",
                "e2e-smoke/js-redwoodsdk/web/tests/add.test.ts",
            ),
            validation_command="cd e2e-smoke/js-redwoodsdk && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: Lit component helper behavior",
            targets=(
                "e2e-smoke/js-lit/src/add.js",
                "e2e-smoke/js-lit/tests/add.test.js",
            ),
            validation_command="cd e2e-smoke/js-lit && npm test -- --passWithNoTests",
        ),
        IssueTemplate(
            kind="JS framework regression: Alpine Vite helper behavior",
            targets=(
                "e2e-smoke/js-alpine-vite/src/add.js",
                "e2e-smoke/js-alpine-vite/tests/add.test.js",
            ),
            validation_command="cd e2e-smoke/js-alpine-vite && npm test -- --passWithNoTests",
        ),
    )


def _python_framework_templates() -> tuple[IssueTemplate, ...]:
    return (
        IssueTemplate(
            kind="Python framework regression: FastAPI service behavior",
            targets=(
                "e2e-smoke/py-fastapi/app/add.py",
                "e2e-smoke/py-fastapi/tests/test_add.py",
            ),
            validation_command="cd e2e-smoke/py-fastapi && pytest -q",
        ),
        IssueTemplate(
            kind="Python framework regression: Django utility behavior",
            targets=(
                "e2e-smoke/py-django/app/add.py",
                "e2e-smoke/py-django/tests/test_add.py",
            ),
            validation_command="cd e2e-smoke/py-django && python -m pytest -q",
        ),
        IssueTemplate(
            kind="Python framework regression: Flask service behavior",
            targets=(
                "e2e-smoke/py-flask/app/add.py",
                "e2e-smoke/py-flask/tests/test_add.py",
            ),
            validation_command="cd e2e-smoke/py-flask && pytest -q",
        ),
    )


def _python_data_ml_templates() -> tuple[IssueTemplate, ...]:
    return (
        IssueTemplate(
            kind="Python data regression: pandas transform behavior",
            targets=(
                "e2e-smoke/py-data-pandas/app/add.py",
                "e2e-smoke/py-data-pandas/tests/test_add.py",
            ),
            validation_command="cd e2e-smoke/py-data-pandas && pytest -q",
        ),
        IssueTemplate(
            kind="Python ML regression: sklearn helper behavior",
            targets=(
                "e2e-smoke/py-ml-sklearn/app/add.py",
                "e2e-smoke/py-ml-sklearn/tests/test_add.py",
            ),
            validation_command="cd e2e-smoke/py-ml-sklearn && pytest -q",
        ),
    )


def validate_issue_drafts(drafts: Sequence[IssueDraft], *, repo_root: Path) -> None:
    normalized_root = Path(repo_root).expanduser().resolve()
    seen_titles: set[str] = set()
    seen_targets: set[tuple[str, ...]] = set()
    for draft in drafts:
        title = str(draft.title or "").strip()
        if not title:
            raise ValueError("Draft validation failed: empty title")
        lowered_title = title.lower()
        if lowered_title in seen_titles:
            raise ValueError(f"Draft validation failed: duplicate title: {title}")
        seen_titles.add(lowered_title)

        spec = compile_task_spec(issue_title=title, issue_body=draft.body)
        if not spec.output_targets:
            raise ValueError(f"Draft validation failed: no parsed output targets for {title}")
        if not spec.validation_commands:
            raise ValueError(f"Draft validation failed: no parsed validation command for {title}")
        if not spec.execution_root.startswith(("e2e-smoke/", "e2e-apps/")):
            raise ValueError(
                f"Draft validation failed: unsupported execution root '{spec.execution_root}' for {title}"
            )
        if not _has_focused_validation_command(
            execution_root=spec.execution_root,
            validation_commands=spec.validation_commands,
        ):
            raise ValueError(
                f"Draft validation failed: validation command must be rooted to '{spec.execution_root}' for {title}"
            )
        required_runtime_profile = _RUNTIME_PROFILE_BY_ROOT.get(spec.execution_root, "")
        if required_runtime_profile and (
            not _body_has_explicit_contract_field(draft.body, "Execution root")
            or not _body_has_explicit_contract_field(draft.body, "Runtime profile")
            or str(spec.runtime_profile or "").strip() != required_runtime_profile
        ):
            raise ValueError(
                f"Draft validation failed: missing browser-backed runtime contract for {title} "
                f"(expected execution root + runtime profile {required_runtime_profile})"
            )
        normalized_targets = tuple(_normalize_path(target) for target in spec.output_targets)
        if normalized_targets in seen_targets:
            raise ValueError(f"Draft validation failed: duplicate target set for {title}")
        seen_targets.add(normalized_targets)
        for target in normalized_targets:
            if not (normalized_root / target).exists():
                raise ValueError(f"Draft validation failed: missing target path for {title}: {target}")
        if tuple(_dedupe_labels(draft.labels)) != tuple(draft.labels):
            raise ValueError(f"Draft validation failed: duplicate labels for {title}")


def _mega_final_wave_1_templates() -> tuple[IssueTemplate, ...]:
    return (
        _template(
            kind="Mega final smoke: Node baseline add flow",
            targets=("e2e-smoke/node/src/add.js", "e2e-smoke/node/test/add.test.js"),
            validation_command="cd e2e-smoke/node && npm test -- --passWithNoTests",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Python baseline smoke math",
            targets=("e2e-smoke/python/smoke_math.py", "e2e-smoke/python/tests/test_smoke_math.py"),
            validation_command="cd e2e-smoke/python && pytest -q",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Next.js service behavior",
            targets=("e2e-smoke/js-next/src/add.js", "e2e-smoke/js-next/tests/add.test.js"),
            validation_command="cd e2e-smoke/js-next && npm test -- --passWithNoTests",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Vue Vite composable behavior",
            targets=("e2e-smoke/js-vue-vite/src/add.js", "e2e-smoke/js-vue-vite/tests/add.test.js"),
            validation_command="cd e2e-smoke/js-vue-vite && npm test -- --passWithNoTests",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Remix server helper behavior",
            targets=("e2e-smoke/js-remix/app/utils/add.server.js", "e2e-smoke/js-remix/tests/add.test.js"),
            validation_command="cd e2e-smoke/js-remix && npm test -- --passWithNoTests",
            difficulty="medium",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Astro component helper behavior",
            targets=("e2e-smoke/js-astro/src/utils/add.js", "e2e-smoke/js-astro/tests/add.test.js"),
            validation_command="cd e2e-smoke/js-astro && npm test -- --passWithNoTests",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: SolidStart route helper behavior",
            targets=("e2e-smoke/js-solidstart/src/lib/add.js", "e2e-smoke/js-solidstart/tests/add.test.js"),
            validation_command="cd e2e-smoke/js-solidstart && npm test -- --passWithNoTests",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Hono handler behavior",
            targets=("e2e-smoke/js-hono/src/add.js", "e2e-smoke/js-hono/tests/add.test.js"),
            validation_command="cd e2e-smoke/js-hono && npm test -- --passWithNoTests",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Adonis service helper behavior",
            targets=("e2e-smoke/js-adonis/app/services/add.ts", "e2e-smoke/js-adonis/tests/add.spec.ts"),
            validation_command="cd e2e-smoke/js-adonis && npm test -- --passWithNoTests",
            difficulty="medium",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: FastAPI service behavior",
            targets=("e2e-smoke/py-fastapi/app/add.py", "e2e-smoke/py-fastapi/tests/test_add.py"),
            validation_command="cd e2e-smoke/py-fastapi && pytest -q",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Django utility behavior",
            targets=("e2e-smoke/py-django/app/add.py", "e2e-smoke/py-django/tests/test_add.py"),
            validation_command="cd e2e-smoke/py-django && python -m pytest -q",
            difficulty="medium",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Flask service behavior",
            targets=("e2e-smoke/py-flask/app/add.py", "e2e-smoke/py-flask/tests/test_add.py"),
            validation_command="cd e2e-smoke/py-flask && pytest -q",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: pandas transform behavior",
            targets=("e2e-smoke/py-data-pandas/app/add.py", "e2e-smoke/py-data-pandas/tests/test_add.py"),
            validation_command="cd e2e-smoke/py-data-pandas && pytest -q",
            difficulty="medium",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final app: Node Next todo route and service contract",
            targets=(
                "e2e-apps/node-next/app/api/todos/route.js",
                "e2e-apps/node-next/lib/todo-service.js",
                "e2e-apps/node-next/tests/todo-service.test.js",
            ),
            validation_command="cd e2e-apps/node-next && npm test -- --passWithNoTests",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Node Next export service contract",
            targets=("e2e-apps/node-next/lib/export-service.js", "e2e-apps/node-next/tests/export-service.test.js"),
            validation_command="cd e2e-apps/node-next && npm test -- --passWithNoTests",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Node Next auth session normalization",
            targets=(
                "e2e-apps/node-next/app/api/auth/session/route.js",
                "e2e-apps/node-next/tests/auth-session-route.test.js",
            ),
            validation_command="cd e2e-apps/node-next && npm test -- --passWithNoTests",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Python FastAPI API contract",
            targets=("e2e-apps/python-fastapi/app/api.py", "e2e-apps/python-fastapi/tests/test_api_contract.py"),
            validation_command="cd e2e-apps/python-fastapi && pytest -q",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Python FastAPI domain service",
            targets=("e2e-apps/python-fastapi/app/service.py", "e2e-apps/python-fastapi/tests/test_domain_service.py"),
            validation_command="cd e2e-apps/python-fastapi && pytest -q",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Python FastAPI importer behavior",
            targets=("e2e-apps/python-fastapi/app/importer.py", "e2e-apps/python-fastapi/tests/test_importer.py"),
            validation_command="cd e2e-apps/python-fastapi && pytest -q",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Ruby Rails session flow",
            targets=(
                "e2e-apps/ruby-rails-web/app/controllers/sessions_controller.rb",
                "e2e-apps/ruby-rails-web/spec/requests/health_spec.rb",
            ),
            validation_command="cd e2e-apps/ruby-rails-web && bundle exec rspec",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Ruby Rails dashboard flow",
            targets=(
                "e2e-apps/ruby-rails-web/app/controllers/dashboard_controller.rb",
                "e2e-apps/ruby-rails-web/config/routes.rb",
            ),
            validation_command="cd e2e-apps/ruby-rails-web && bundle exec rspec",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Java Spring login flow",
            targets=(
                "e2e-apps/java-spring-web/src/main/java/example/web/LoginController.java",
                "e2e-apps/java-spring-web/src/test/java/example/web/HealthControllerTest.java",
            ),
            validation_command="cd e2e-apps/java-spring-web && ./gradlew test --no-daemon",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Java Spring dashboard flow",
            targets=(
                "e2e-apps/java-spring-web/src/main/java/example/web/DashboardController.java",
                "e2e-apps/java-spring-web/src/main/java/example/web/HealthController.java",
            ),
            validation_command="cd e2e-apps/java-spring-web && ./gradlew test --no-daemon",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Prosper class merge utilities",
            targets=("e2e-apps/prosper-chat/src/lib/utils.ts", "e2e-apps/prosper-chat/src/test/utils.test.ts"),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final backend: Prosper chat widget token helpers",
            targets=(
                "e2e-apps/prosper-chat/supabase/functions/chat-widget/index.ts",
                "e2e-apps/prosper-chat/supabase/functions/_shared/widgetToken.ts",
            ),
            validation_command=_PROSPER_CHAT_BACKEND_COMMAND,
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final backend: Prosper appointment slot flows",
            targets=(
                "e2e-apps/prosper-chat/supabase/functions/check-availability/index.ts",
                "e2e-apps/prosper-chat/supabase/functions/book-appointment/index.ts",
            ),
            validation_command=_PROSPER_CHAT_BACKEND_COMMAND,
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Prosper transcript normalization",
            targets=("e2e-apps/prosper-chat/src/lib/transcript.ts", "e2e-apps/prosper-chat/src/test/transcript.test.ts"),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Prosper plan billing summary",
            targets=("e2e-apps/prosper-chat/src/lib/plans.ts", "e2e-apps/prosper-chat/src/test/plans.test.ts"),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Prosper industry template normalization",
            targets=(
                "e2e-apps/prosper-chat/src/data/industryTemplates.ts",
                "e2e-apps/prosper-chat/src/test/industry-templates.test.ts",
            ),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Prosper widget state hydration",
            targets=(
                "e2e-apps/prosper-chat/src/contexts/widget-state.ts",
                "e2e-apps/prosper-chat/src/test/widget-state.test.ts",
            ),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final backend: Prosper usage billing normalization",
            targets=(
                "e2e-apps/prosper-chat/supabase/functions/_shared/usage-billing.ts",
                "e2e-apps/prosper-chat/supabase/functions/tests/usage-billing.test.ts",
            ),
            validation_command=_PROSPER_CHAT_BACKEND_COMMAND,
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final db: Prosper schema core inventory",
            targets=(
                "e2e-apps/prosper-chat/supabase/assertions/schema_core.sql",
                "e2e-apps/prosper-chat/supabase/assertions/manifest.json",
            ),
            validation_command=_PROSPER_CHAT_DB_COMMAND,
            difficulty="easy",
            source="e2e-apps",
            extra_labels=("area:db", "kind:migration"),
        ),
        _template(
            kind="Mega final db: Prosper policy core audit",
            targets=(
                "e2e-apps/prosper-chat/supabase/assertions/policies_core.sql",
                "e2e-apps/prosper-chat/supabase/assertions/manifest.json",
            ),
            validation_command=_PROSPER_CHAT_DB_COMMAND,
            difficulty="easy",
            source="e2e-apps",
            extra_labels=("area:db", "kind:rls"),
        ),
        _template(
            kind="Mega final app: Nobi trade model persistence",
            targets=("e2e-apps/nobi-owl-trader/api/models.py", "e2e-apps/nobi-owl-trader/tests/test_models.py"),
            validation_command="cd e2e-apps/nobi-owl-trader && pytest -q",
            difficulty="easy",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Nobi database bootstrap",
            targets=("e2e-apps/nobi-owl-trader/api/database.py", "e2e-apps/nobi-owl-trader/tests/test_database.py"),
            validation_command="cd e2e-apps/nobi-owl-trader && pytest -q",
            difficulty="easy",
            source="e2e-apps",
        ),
    )


def _mega_final_wave_2_templates() -> tuple[IssueTemplate, ...]:
    return (
        _template(
            kind="Mega final smoke: Python baseline add module",
            targets=("e2e-smoke/python/app/add.py", "e2e-smoke/python/tests/test_add.py"),
            validation_command="cd e2e-smoke/python && pytest -q",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Nuxt server helper behavior",
            targets=("e2e-smoke/js-nuxt/src/add.js", "e2e-smoke/js-nuxt/tests/add.test.js"),
            validation_command="cd e2e-smoke/js-nuxt && npm test -- --passWithNoTests",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Angular utility behavior",
            targets=("e2e-smoke/js-angular/src/add.js", "e2e-smoke/js-angular/tests/add.test.js"),
            validation_command="cd e2e-smoke/js-angular && npm test -- --passWithNoTests",
            difficulty="medium",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: SvelteKit module behavior",
            targets=("e2e-smoke/js-sveltekit/src/add.js", "e2e-smoke/js-sveltekit/tests/add.test.js"),
            validation_command="cd e2e-smoke/js-sveltekit && npm test -- --passWithNoTests",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Express route helper behavior",
            targets=("e2e-smoke/js-express/src/add.js", "e2e-smoke/js-express/tests/add.test.js"),
            validation_command="cd e2e-smoke/js-express && npm test -- --passWithNoTests",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Nest provider behavior",
            targets=("e2e-smoke/js-nest/src/add.js", "e2e-smoke/js-nest/tests/add.test.js"),
            validation_command="cd e2e-smoke/js-nest && npm test -- --passWithNoTests",
            difficulty="medium",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Qwik utility behavior",
            targets=("e2e-smoke/js-qwik/src/utils/add.ts", "e2e-smoke/js-qwik/tests/add.test.ts"),
            validation_command="cd e2e-smoke/js-qwik && npm test -- --passWithNoTests",
            difficulty="medium",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Koa middleware helper behavior",
            targets=("e2e-smoke/js-koa/src/add.js", "e2e-smoke/js-koa/tests/add.test.js"),
            validation_command="cd e2e-smoke/js-koa && npm test -- --passWithNoTests",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: RedwoodSDK helper behavior",
            targets=("e2e-smoke/js-redwoodsdk/web/src/lib/add.ts", "e2e-smoke/js-redwoodsdk/web/tests/add.test.ts"),
            validation_command="cd e2e-smoke/js-redwoodsdk && npm test -- --passWithNoTests",
            difficulty="medium",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Lit component helper behavior",
            targets=("e2e-smoke/js-lit/src/add.js", "e2e-smoke/js-lit/tests/add.test.js"),
            validation_command="cd e2e-smoke/js-lit && npm test -- --passWithNoTests",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: Alpine Vite helper behavior",
            targets=("e2e-smoke/js-alpine-vite/src/add.js", "e2e-smoke/js-alpine-vite/tests/add.test.js"),
            validation_command="cd e2e-smoke/js-alpine-vite && npm test -- --passWithNoTests",
            difficulty="easy",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final smoke: sklearn helper behavior",
            targets=("e2e-smoke/py-ml-sklearn/app/add.py", "e2e-smoke/py-ml-sklearn/tests/test_add.py"),
            validation_command="cd e2e-smoke/py-ml-sklearn && pytest -q",
            difficulty="medium",
            source="e2e-smoke",
        ),
        _template(
            kind="Mega final app: Node Next todo contract recheck",
            targets=(
                "e2e-apps/node-next/app/api/todos/route.js",
                "e2e-apps/node-next/lib/todo-service.js",
                "e2e-apps/node-next/tests/todo-service.test.js",
            ),
            validation_command="cd e2e-apps/node-next && npm test -- --passWithNoTests",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Node Next notification digest stability",
            targets=(
                "e2e-apps/node-next/lib/notification-digest.js",
                "e2e-apps/node-next/tests/notification-digest.test.js",
            ),
            validation_command="cd e2e-apps/node-next && npm test -- --passWithNoTests",
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Python FastAPI repository detach semantics",
            targets=(
                "e2e-apps/python-fastapi/app/repository.py",
                "e2e-apps/python-fastapi/tests/test_domain_service.py",
            ),
            validation_command="cd e2e-apps/python-fastapi && pytest -q",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Python FastAPI reporting summary",
            targets=(
                "e2e-apps/python-fastapi/app/reporting.py",
                "e2e-apps/python-fastapi/tests/test_reporting.py",
            ),
            validation_command="cd e2e-apps/python-fastapi && pytest -q",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Python FastAPI token refresh flow",
            targets=(
                "e2e-apps/python-fastapi/app/token_service.py",
                "e2e-apps/python-fastapi/tests/test_token_service.py",
            ),
            validation_command="cd e2e-apps/python-fastapi && pytest -q",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final backend: Prosper checkout flow",
            targets=(
                "e2e-apps/prosper-chat/supabase/functions/create-checkout/index.ts",
                "e2e-apps/prosper-chat/supabase/functions/_shared/billing.ts",
            ),
            validation_command=_PROSPER_CHAT_BACKEND_COMMAND,
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final backend: Prosper customer portal flow",
            targets=(
                "e2e-apps/prosper-chat/supabase/functions/customer-portal/index.ts",
                "e2e-apps/prosper-chat/supabase/functions/_shared/billing.ts",
            ),
            validation_command=_PROSPER_CHAT_BACKEND_COMMAND,
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final backend: Prosper subscription billing helpers",
            targets=(
                "e2e-apps/prosper-chat/supabase/functions/check-subscription/index.ts",
                "e2e-apps/prosper-chat/supabase/functions/_shared/billing.ts",
            ),
            validation_command=_PROSPER_CHAT_BACKEND_COMMAND,
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final db: Prosper anon access enforcement",
            targets=(
                "e2e-apps/prosper-chat/supabase/migrations/20260302101500_7f8d9de2-cb2b-4f35-b3b8-6d8a8f519e7e.sql",
                "e2e-apps/prosper-chat/supabase/assertions/anon_access_controls.sql",
            ),
            validation_command=_PROSPER_CHAT_DB_COMMAND,
            difficulty="hard",
            source="e2e-apps",
            extra_labels=("area:db", "kind:rls"),
        ),
        _template(
            kind="Mega final db: Prosper subscription visibility",
            targets=(
                "e2e-apps/prosper-chat/supabase/migrations/20260301204622_64bd8908-fa0d-4f2c-b120-e7990f38b3b5.sql",
                "e2e-apps/prosper-chat/supabase/assertions/subscription_visibility.sql",
            ),
            validation_command=_PROSPER_CHAT_DB_COMMAND,
            difficulty="hard",
            source="e2e-apps",
            extra_labels=("area:db", "kind:rls"),
        ),
        _template(
            kind="Mega final db: Prosper appointment overlap",
            targets=(
                "e2e-apps/prosper-chat/supabase/migrations/20260302101500_7f8d9de2-cb2b-4f35-b3b8-6d8a8f519e7e.sql",
                "e2e-apps/prosper-chat/supabase/assertions/appointment_overlap.sql",
            ),
            validation_command=_PROSPER_CHAT_DB_COMMAND,
            difficulty="hard",
            source="e2e-apps",
            extra_labels=("area:db", "kind:migration"),
        ),
        _template(
            kind="Mega final db: Prosper bot widget integrity",
            targets=(
                "e2e-apps/prosper-chat/supabase/migrations/20260301222424_81f2b260-db82-49bf-a1b6-30686117ac83.sql",
                "e2e-apps/prosper-chat/supabase/assertions/bot_widget_integrity.sql",
            ),
            validation_command=_PROSPER_CHAT_DB_COMMAND,
            difficulty="hard",
            source="e2e-apps",
            extra_labels=("area:db", "kind:migration"),
        ),
        _template(
            kind="Mega final app: Nobi risk guardrails",
            targets=("e2e-apps/nobi-owl-trader/api/risk.py", "e2e-apps/nobi-owl-trader/tests/test_risk.py"),
            validation_command="cd e2e-apps/nobi-owl-trader && pytest -q",
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Nobi portfolio engine",
            targets=("e2e-apps/nobi-owl-trader/api/portfolio.py", "e2e-apps/nobi-owl-trader/tests/test_portfolio.py"),
            validation_command="cd e2e-apps/nobi-owl-trader && pytest -q",
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Nobi portfolio routes",
            targets=(
                "e2e-apps/nobi-owl-trader/api/routes/portfolio.py",
                "e2e-apps/nobi-owl-trader/tests/test_routes_portfolio.py",
            ),
            validation_command="cd e2e-apps/nobi-owl-trader && pytest -q",
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Nobi backtest exporter",
            targets=(
                "e2e-apps/nobi-owl-trader/api/backtest/exporter.py",
                "e2e-apps/nobi-owl-trader/tests/test_exporter.py",
            ),
            validation_command="cd e2e-apps/nobi-owl-trader && pytest -q",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Nobi strategy signal thresholds",
            targets=(
                "e2e-apps/nobi-owl-trader/api/strategy/signals.py",
                "e2e-apps/nobi-owl-trader/tests/test_signals.py",
            ),
            validation_command="cd e2e-apps/nobi-owl-trader && pytest -q",
            difficulty="medium",
            source="e2e-apps",
        ),
        _template(
            kind="Mega final app: Nobi API entry routes",
            targets=("e2e-apps/nobi-owl-trader/api/main.py", "e2e-apps/nobi-owl-trader/tests/test_routes_portfolio.py"),
            validation_command="cd e2e-apps/nobi-owl-trader && pytest -q",
            difficulty="hard",
            source="e2e-apps",
        ),
    )


def _template(
    *,
    kind: str,
    targets: tuple[str, ...],
    validation_command: str,
    difficulty: str,
    source: str,
    body: str = "",
    extra_labels: Sequence[str] = (),
) -> IssueTemplate:
    return IssueTemplate(
        kind=kind,
        targets=targets,
        validation_command=validation_command,
        body=body,
        labels=tuple(_dedupe_labels((f"difficulty:{difficulty}", f"source:{source}", *extra_labels))),
    )


def _hybrid_body(*, summary: str, observed: Sequence[str], expected: Sequence[str], targets: Sequence[str], validation: str) -> str:
    lines = [summary.strip(), "", "Observed:"]
    lines.extend(f"- {item}" for item in observed)
    lines.extend(["", "Expected:"])
    lines.extend(f"- {item}" for item in expected)
    lines.extend(["", *_contract_section_lines(targets=targets, validation=validation)])
    return "\n".join(lines) + "\n"


def _messy_body(*, intro_lines: Sequence[str], targets: Sequence[str], validation: str) -> str:
    lines = [*intro_lines, "", *_contract_section_lines(targets=targets, validation=validation)]
    return "\n".join(lines) + "\n"


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


def _contract_section_lines(*, targets: Sequence[str], validation: str) -> list[str]:
    lines = ["Required code outputs:"]
    lines.extend(f"- {target}" for target in targets)
    execution_root, runtime_profile = _contract_execution_metadata(targets=targets, validation=validation)
    if execution_root:
        lines.extend(["", "Execution root:", f"- {execution_root}"])
    if runtime_profile:
        lines.extend(["", f"Runtime profile: {runtime_profile}"])
    lines.extend(["", "Validation:", f"- {validation}"])
    return lines


def _contract_execution_metadata(*, targets: Sequence[str], validation: str) -> tuple[str, str]:
    draft_body = (
        "Required code outputs:\n"
        + "\n".join(f"- {target}" for target in targets)
        + "\n\nValidation:\n"
        + f"- {validation}\n"
    )
    spec = compile_task_spec(issue_title="", issue_body=draft_body)
    execution_root = str(spec.execution_root or "").strip()
    runtime_profile = _RUNTIME_PROFILE_BY_ROOT.get(execution_root, "")
    return execution_root, runtime_profile


def _prod_eval_hybrid_heavy_templates() -> tuple[IssueTemplate, ...]:
    return (
        _template(
            kind="Control: Nobi API entry routes contract",
            targets=("e2e-apps/nobi-owl-trader/api/main.py", "e2e-apps/nobi-owl-trader/tests/test_routes_portfolio.py"),
            validation_command="cd e2e-apps/nobi-owl-trader && pytest -q",
            difficulty="hard",
            source="e2e-apps",
            extra_labels=("eval:control",),
        ),
        _template(
            kind="Control: Node Next todo route and service contract",
            targets=(
                "e2e-apps/node-next/app/api/todos/route.js",
                "e2e-apps/node-next/lib/todo-service.js",
                "e2e-apps/node-next/tests/todo-service.test.js",
            ),
            validation_command="cd e2e-apps/node-next && npm test -- --passWithNoTests",
            difficulty="medium",
            source="e2e-apps",
            extra_labels=("eval:control",),
        ),
        _template(
            kind="Hybrid: Portfolio endpoint returns incomplete holdings summary",
            targets=("e2e-apps/nobi-owl-trader/api/routes/portfolio.py", "e2e-apps/nobi-owl-trader/tests/test_routes_portfolio.py"),
            validation_command="cd e2e-apps/nobi-owl-trader && pytest -q",
            body=_hybrid_body(
                summary=(
                    "The portfolio endpoint started returning an incomplete holdings summary after the latest route cleanup. "
                    "This looks isolated to the portfolio route behavior, not the model layer."
                ),
                observed=(
                    "The portfolio response omits part of the expected holdings summary for active accounts.",
                    "The regression shows up through the route contract rather than lower-level model persistence tests.",
                ),
                expected=(
                    "The route should keep returning the complete portfolio summary expected by the existing API tests.",
                    "The fix should stay scoped to the portfolio route behavior and its route-level test coverage.",
                ),
                targets=("e2e-apps/nobi-owl-trader/api/routes/portfolio.py", "e2e-apps/nobi-owl-trader/tests/test_routes_portfolio.py"),
                validation="cd e2e-apps/nobi-owl-trader && pytest -q",
            ),
            difficulty="hard",
            source="e2e-apps",
            extra_labels=("eval:hybrid",),
        ),
        _template(
            kind="Hybrid: Create todo API accepts invalid payload without a 400",
            targets=(
                "e2e-apps/node-next/app/api/todos/route.js",
                "e2e-apps/node-next/tests/todo-service.test.js",
            ),
            validation_command="cd e2e-apps/node-next && npm test -- --passWithNoTests",
            body=_hybrid_body(
                summary=(
                    "We have a regression where the create-todo API is too permissive on malformed payloads. "
                    "The bug report from the app side is that obviously invalid submissions are not getting rejected cleanly."
                ),
                observed=(
                    "Requests with invalid todo payloads are being accepted instead of failing fast.",
                    "The route behavior is the important surface here, and the fix should not spill into unrelated notification or export paths.",
                ),
                expected=(
                    "Invalid payloads should produce the route behavior covered by the existing todo tests.",
                    "Keep the scope tight to the todo route contract and its targeted test coverage.",
                ),
                targets=(
                    "e2e-apps/node-next/app/api/todos/route.js",
                    "e2e-apps/node-next/tests/todo-service.test.js",
                ),
                validation="cd e2e-apps/node-next && npm test -- --passWithNoTests",
            ),
            difficulty="medium",
            source="e2e-apps",
            extra_labels=("eval:hybrid",),
        ),
        _template(
            kind="Hybrid: Django add helper regressed on numeric strings",
            targets=("e2e-smoke/py-django/app/add.py", "e2e-smoke/py-django/tests/test_add.py"),
            validation_command="cd e2e-smoke/py-django && python -m pytest -q",
            body=_hybrid_body(
                summary=(
                    "The Django smoke helper appears to have regressed on numeric string handling. "
                    "The complaint is that values which used to combine cleanly now behave inconsistently at the app boundary."
                ),
                observed=(
                    "Numeric string inputs are not staying compatible with the established add-helper behavior.",
                    "The regression should be fixable inside the Django smoke sandbox without changing import-path behavior.",
                ),
                expected=(
                    "Restore the existing add-helper behavior for stringable numeric inputs.",
                    "Keep the test focused on the sandbox’s normal package-loading path.",
                ),
                targets=("e2e-smoke/py-django/app/add.py", "e2e-smoke/py-django/tests/test_add.py"),
                validation="cd e2e-smoke/py-django && python -m pytest -q",
            ),
            difficulty="medium",
            source="e2e-smoke",
            extra_labels=("eval:hybrid",),
        ),
        _template(
            kind="Hybrid: FastAPI health response lost service metadata",
            targets=("e2e-apps/python-fastapi/app/api.py", "e2e-apps/python-fastapi/tests/test_api_contract.py"),
            validation_command="cd e2e-apps/python-fastapi && pytest -q",
            body=_hybrid_body(
                summary=(
                    "A recent API cleanup appears to have dropped part of the service metadata from the FastAPI response contract. "
                    "This should be treated as an API contract regression rather than a repository-layer change."
                ),
                observed=(
                    "The response shape no longer matches the expected contract covered by the FastAPI API tests.",
                    "The failure is on the API-facing surface, not the importer or token service paths.",
                ),
                expected=(
                    "Restore the metadata expected by the existing API contract tests.",
                    "Keep the change limited to the API contract surface and its direct test.",
                ),
                targets=("e2e-apps/python-fastapi/app/api.py", "e2e-apps/python-fastapi/tests/test_api_contract.py"),
                validation="cd e2e-apps/python-fastapi && pytest -q",
            ),
            difficulty="medium",
            source="e2e-apps",
            extra_labels=("eval:hybrid",),
        ),
        _template(
            kind="Hybrid: Prosper transcript normalization should preserve speaker labels",
            targets=("e2e-apps/prosper-chat/src/lib/transcript.ts", "e2e-apps/prosper-chat/src/test/transcript.test.ts"),
            validation_command=_PROSPER_CHAT_FULL_COMMAND,
            body=_hybrid_body(
                summary=(
                    "Transcript cleanup is over-normalizing some content and dropping speaker-label semantics we still need. "
                    "This should remain a transcript-only repair, not a broader frontend rewrite."
                ),
                observed=(
                    "Speaker labels are getting flattened or rewritten more aggressively than intended.",
                    "The issue is scoped to transcript normalization behavior and its targeted test lane.",
                ),
                expected=(
                    "Preserve the current speaker-label semantics unless the transcript fixture clearly requires a change.",
                    "Keep the fix confined to the named transcript files.",
                ),
                targets=("e2e-apps/prosper-chat/src/lib/transcript.ts", "e2e-apps/prosper-chat/src/test/transcript.test.ts"),
                validation=_PROSPER_CHAT_FULL_COMMAND,
            ),
            difficulty="medium",
            source="e2e-apps",
            extra_labels=("eval:hybrid",),
        ),
        _template(
            kind="Hybrid: Notification digest should not cross-send colliding ids",
            targets=("e2e-apps/node-next/lib/notification-digest.js", "e2e-apps/node-next/tests/notification-digest.test.js"),
            validation_command="cd e2e-apps/node-next && npm test -- --passWithNoTests",
            body=_hybrid_body(
                summary=(
                    "We saw a digest edge case where colliding notification ids across recipients can bleed into the wrong recipient send flow. "
                    "This one is meant to exercise realistic human wording around a scoped Node utility regression."
                ),
                observed=(
                    "Digest flushing can mark or include notifications for the wrong recipient when ids collide.",
                    "The regression belongs in the notification digest helper and its direct test coverage.",
                ),
                expected=(
                    "Flush behavior should stay recipient-scoped even when ids collide.",
                    "Keep the change local to the digest helper and targeted test file.",
                ),
                targets=("e2e-apps/node-next/lib/notification-digest.js", "e2e-apps/node-next/tests/notification-digest.test.js"),
                validation="cd e2e-apps/node-next && npm test -- --passWithNoTests",
            ),
            difficulty="hard",
            source="e2e-apps",
            extra_labels=("eval:hybrid",),
        ),
        _template(
            kind="Messy: pandas helper fix should stay pandas-specific",
            targets=("e2e-smoke/py-data-pandas/app/add.py", "e2e-smoke/py-data-pandas/tests/test_add.py"),
            validation_command="cd e2e-smoke/py-data-pandas && pytest -q",
            body=_messy_body(
                intro_lines=(
                    "The pandas smoke helper still feels off after the last repair.",
                    "This should stay pandas-specific and should not broaden generic add semantics for unrelated object types.",
                    "Use the existing pandas test as the source of truth and keep the patch narrow.",
                ),
                targets=("e2e-smoke/py-data-pandas/app/add.py", "e2e-smoke/py-data-pandas/tests/test_add.py"),
                validation="cd e2e-smoke/py-data-pandas && pytest -q",
            ),
            difficulty="medium",
            source="e2e-smoke",
            extra_labels=("eval:messy",),
        ),
        _template(
            kind="Messy: Nobi portfolio engine weirdness after the latest cleanup",
            targets=("e2e-apps/nobi-owl-trader/api/portfolio.py", "e2e-apps/nobi-owl-trader/tests/test_portfolio.py"),
            validation_command="cd e2e-apps/nobi-owl-trader && pytest -q",
            body=_messy_body(
                intro_lines=(
                    "This one is intentionally a little messier.",
                    "After the latest cleanup the Nobi portfolio behavior feels off again and the engine-level coverage is the part we care about here.",
                    "Please keep the fix tight and avoid wandering into unrelated model or backtest behavior.",
                ),
                targets=("e2e-apps/nobi-owl-trader/api/portfolio.py", "e2e-apps/nobi-owl-trader/tests/test_portfolio.py"),
                validation="cd e2e-apps/nobi-owl-trader && pytest -q",
            ),
            difficulty="hard",
            source="e2e-apps",
            extra_labels=("eval:messy",),
        ),
        _template(
            kind="Messy: Todo route is acting broken when title is empty",
            targets=(
                "e2e-apps/node-next/app/api/todos/route.js",
                "e2e-apps/node-next/tests/todo-service.test.js",
            ),
            validation_command="cd e2e-apps/node-next && npm test -- --passWithNoTests",
            body=_messy_body(
                intro_lines=(
                    "Something is still off in the Node Next todo route when the title is empty.",
                    "Treat this as the same create-todo surface, not a reason to touch notification-digest or export behavior.",
                    "The existing todo tests should stay the source of truth here.",
                ),
                targets=(
                    "e2e-apps/node-next/app/api/todos/route.js",
                    "e2e-apps/node-next/tests/todo-service.test.js",
                ),
                validation="cd e2e-apps/node-next && npm test -- --passWithNoTests",
            ),
            difficulty="medium",
            source="e2e-apps",
            extra_labels=("eval:messy",),
        ),
    )


def _hard_non_prosper_templates() -> tuple[IssueTemplate, ...]:
    return (
        _template(
            kind="Hard app: Nobi API entry routes contract",
            targets=("e2e-apps/nobi-owl-trader/api/main.py", "e2e-apps/nobi-owl-trader/tests/test_routes_portfolio.py"),
            validation_command="cd e2e-apps/nobi-owl-trader && pytest -q",
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Hard app: Nobi risk guardrails",
            targets=("e2e-apps/nobi-owl-trader/api/risk.py", "e2e-apps/nobi-owl-trader/tests/test_risk.py"),
            validation_command="cd e2e-apps/nobi-owl-trader && pytest -q",
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Hard app: Nobi portfolio engine weirdness",
            targets=("e2e-apps/nobi-owl-trader/api/portfolio.py", "e2e-apps/nobi-owl-trader/tests/test_portfolio.py"),
            validation_command="cd e2e-apps/nobi-owl-trader && pytest -q",
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Hard app: Node Next notification digest stability",
            targets=("e2e-apps/node-next/lib/notification-digest.js", "e2e-apps/node-next/tests/notification-digest.test.js"),
            validation_command="cd e2e-apps/node-next && npm test -- --passWithNoTests",
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Hard app: Node Next todo route contract under invalid payloads",
            targets=(
                "e2e-apps/node-next/app/api/todos/route.js",
                "e2e-apps/node-next/lib/todo-service.js",
                "e2e-apps/node-next/tests/todo-service.test.js",
            ),
            validation_command="cd e2e-apps/node-next && npm test -- --passWithNoTests",
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Hard app: FastAPI API contract metadata restoration",
            targets=("e2e-apps/python-fastapi/app/api.py", "e2e-apps/python-fastapi/tests/test_api_contract.py"),
            validation_command="cd e2e-apps/python-fastapi && pytest -q",
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Hard app: FastAPI token refresh flow",
            targets=(
                "e2e-apps/python-fastapi/app/token_service.py",
                "e2e-apps/python-fastapi/tests/test_token_service.py",
            ),
            validation_command="cd e2e-apps/python-fastapi && pytest -q",
            difficulty="hard",
            source="e2e-apps",
        ),
        _template(
            kind="Hard smoke: Django numeric string compatibility",
            targets=("e2e-smoke/py-django/app/add.py", "e2e-smoke/py-django/tests/test_add.py"),
            validation_command="cd e2e-smoke/py-django && python -m pytest -q",
            difficulty="hard",
            source="e2e-smoke",
        ),
        _template(
            kind="Hard smoke: pandas helper stays pandas-specific",
            targets=("e2e-smoke/py-data-pandas/app/add.py", "e2e-smoke/py-data-pandas/tests/test_add.py"),
            validation_command="cd e2e-smoke/py-data-pandas && pytest -q",
            difficulty="hard",
            source="e2e-smoke",
        ),
        _template(
            kind="Hard smoke: Qwik utility behavior",
            targets=("e2e-smoke/js-qwik/src/utils/add.ts", "e2e-smoke/js-qwik/tests/add.test.ts"),
            validation_command="cd e2e-smoke/js-qwik && npm test -- --passWithNoTests",
            difficulty="hard",
            source="e2e-smoke",
        ),
    )


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


def _body_has_explicit_contract_field(body: str, label: str) -> bool:
    pattern = re.compile(rf"^\s*{re.escape(label)}\s*:", re.IGNORECASE | re.MULTILINE)
    return pattern.search(str(body or "")) is not None


def _has_focused_validation_command(*, execution_root: str, validation_commands: Sequence[str]) -> bool:
    normalized_root = str(execution_root or "").strip().strip("/")
    if not normalized_root:
        return False
    expected_prefix = f"cd {normalized_root} &&"
    for command in validation_commands:
        normalized_command = " ".join(str(command or "").split())
        if normalized_command.startswith(expected_prefix):
            return True
    return False
