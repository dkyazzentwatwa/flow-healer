from __future__ import annotations

from pathlib import Path

from flow_healer.issue_generation import (
    DEFAULT_FAMILY,
    JS_FRAMEWORK_FAMILY,
    MEGA_FINAL_WAVE_1_FAMILY,
    MEGA_FINAL_WAVE_2_FAMILY,
    PYTHON_DATA_ML_FAMILY,
    PYTHON_FRAMEWORK_FAMILY,
    PROSPER_CHAT_DB_FAMILY,
    available_issue_families,
    build_issue_drafts,
    select_validation_command,
    validate_issue_drafts,
)
from flow_healer.healer_task_spec import compile_task_spec


def test_select_validation_command_prefers_db_for_prosper_chat_sql_targets() -> None:
    command = select_validation_command(
        title="Prosper chat DB task",
        targets=(
            "e2e-apps/prosper-chat/supabase/migrations/20260302101500_7f8d9de2-cb2b-4f35-b3b8-6d8a8f519e7e.sql",
            "e2e-apps/prosper-chat/supabase/assertions/anon_access_controls.sql",
        ),
        default_command="cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh full",
    )

    assert command == "cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh db"


def test_select_validation_command_keeps_full_for_mixed_prosper_chat_targets() -> None:
    command = select_validation_command(
        title="Prosper chat mixed task",
        targets=(
            "e2e-apps/prosper-chat/src/App.tsx",
            "e2e-apps/prosper-chat/supabase/migrations/20260302101500_7f8d9de2-cb2b-4f35-b3b8-6d8a8f519e7e.sql",
        ),
        default_command="cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh full",
    )

    assert command == "cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh full"


def test_select_validation_command_prefers_backend_for_prosper_chat_function_targets() -> None:
    command = select_validation_command(
        title="Prosper chat backend task",
        targets=(
            "e2e-apps/prosper-chat/supabase/functions/check-subscription/index.ts",
            "e2e-apps/prosper-chat/supabase/functions/_shared/billing.ts",
        ),
        default_command="cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh full",
    )

    assert command == "cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh backend"


def test_build_issue_drafts_adds_db_labels_and_validation_for_prosper_chat_family() -> None:
    drafts = build_issue_drafts(
        count=1,
        prefix="Prosper chat DB task",
        ready_label="healer:ready",
        family=PROSPER_CHAT_DB_FAMILY,
    )

    assert len(drafts) == 1
    draft = drafts[0]
    assert "Validation:\n- cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh db\n" in draft.body
    assert "e2e-apps/prosper-chat/supabase/" in draft.body
    assert "healer:ready" in draft.labels
    assert "area:db" in draft.labels
    assert any(label.startswith("kind:") for label in draft.labels)


def test_available_issue_families_include_framework_expansions() -> None:
    families = available_issue_families()
    assert JS_FRAMEWORK_FAMILY in families
    assert PYTHON_FRAMEWORK_FAMILY in families
    assert PYTHON_DATA_ML_FAMILY in families
    assert MEGA_FINAL_WAVE_1_FAMILY in families
    assert MEGA_FINAL_WAVE_2_FAMILY in families


def test_build_issue_drafts_supports_js_framework_family() -> None:
    drafts = build_issue_drafts(
        count=1,
        prefix="JS framework task",
        ready_label="healer:ready",
        family=JS_FRAMEWORK_FAMILY,
    )

    assert len(drafts) == 1
    assert "e2e-smoke/js-" in drafts[0].body
    assert "Validation:\n- cd e2e-smoke/js-" in drafts[0].body


def test_build_issue_drafts_supports_python_framework_family() -> None:
    drafts = build_issue_drafts(
        count=1,
        prefix="Python framework task",
        ready_label="healer:ready",
        family=PYTHON_FRAMEWORK_FAMILY,
    )

    assert len(drafts) == 1
    assert "e2e-smoke/py-" in drafts[0].body
    assert "Validation:\n- cd e2e-smoke/py-" in drafts[0].body


def test_build_issue_drafts_uses_module_pytest_for_django_smoke() -> None:
    drafts = build_issue_drafts(
        count=3,
        prefix="Python framework task",
        ready_label="healer:ready",
        family=PYTHON_FRAMEWORK_FAMILY,
    )

    django_draft = next(draft for draft in drafts if "e2e-smoke/py-django/" in draft.body)
    assert "Validation:\n- cd e2e-smoke/py-django && python -m pytest -q\n" in django_draft.body


def test_build_issue_drafts_supports_mega_final_wave_families() -> None:
    wave_1 = build_issue_drafts(
        count=30,
        prefix="Mega final sandbox wave 1",
        ready_label="healer:ready",
        extra_labels=("campaign:mega-final", "wave:1"),
        family=MEGA_FINAL_WAVE_1_FAMILY,
    )
    wave_2 = build_issue_drafts(
        count=30,
        prefix="Mega final sandbox wave 2",
        ready_label="healer:ready",
        extra_labels=("campaign:mega-final", "wave:2"),
        family=MEGA_FINAL_WAVE_2_FAMILY,
    )

    assert len(wave_1) == 30
    assert len(wave_2) == 30
    assert len({draft.title for draft in [*wave_1, *wave_2]}) == 60
    assert all("healer:ready" in draft.labels for draft in [*wave_1, *wave_2])
    assert all("campaign:mega-final" in draft.labels for draft in [*wave_1, *wave_2])
    assert all(any(label.startswith("difficulty:") for label in draft.labels) for draft in [*wave_1, *wave_2])
    assert all("Validation:\n- cd " in draft.body for draft in [*wave_1, *wave_2])


def test_validate_issue_drafts_accepts_mega_final_catalog() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    wave_1 = build_issue_drafts(
        count=30,
        prefix="Mega final sandbox wave 1",
        ready_label="healer:ready",
        extra_labels=("campaign:mega-final", "wave:1"),
        family=MEGA_FINAL_WAVE_1_FAMILY,
    )
    wave_2 = build_issue_drafts(
        count=30,
        prefix="Mega final sandbox wave 2",
        ready_label="healer:ready",
        extra_labels=("campaign:mega-final", "wave:2"),
        family=MEGA_FINAL_WAVE_2_FAMILY,
    )

    validate_issue_drafts(wave_1, repo_root=repo_root)
    validate_issue_drafts(wave_2, repo_root=repo_root)


def test_validate_issue_drafts_rejects_missing_target_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    drafts = build_issue_drafts(
        count=1,
        prefix="Broken wave",
        ready_label="healer:ready",
        family=DEFAULT_FAMILY,
    )
    broken = drafts[0].__class__(
        title=drafts[0].title,
        body=(
            "Required code outputs:\n"
            "- e2e-smoke/node/src/does-not-exist.js\n\n"
            "Validation:\n"
            "- cd e2e-smoke/node && npm test -- --passWithNoTests\n"
        ),
        labels=drafts[0].labels,
    )

    try:
        validate_issue_drafts([broken], repo_root=repo_root)
    except ValueError as exc:
        assert "missing target" in str(exc).lower()
    else:
        raise AssertionError("expected validation failure for missing target")


def test_mega_final_catalog_round_trips_through_task_spec_parser() -> None:
    for family in (MEGA_FINAL_WAVE_1_FAMILY, MEGA_FINAL_WAVE_2_FAMILY):
        drafts = build_issue_drafts(
            count=30,
            prefix=f"Parser check {family}",
            ready_label="healer:ready",
            family=family,
        )
        for draft in drafts:
            spec = compile_task_spec(issue_title=draft.title, issue_body=draft.body)
            assert spec.execution_root.startswith(("e2e-smoke/", "e2e-apps/"))
            assert spec.validation_commands
            assert spec.output_targets
