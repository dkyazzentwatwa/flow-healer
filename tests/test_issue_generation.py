from __future__ import annotations

from flow_healer.issue_generation import (
    JS_FRAMEWORK_FAMILY,
    PYTHON_DATA_ML_FAMILY,
    PYTHON_FRAMEWORK_FAMILY,
    PROSPER_CHAT_DB_FAMILY,
    available_issue_families,
    build_issue_drafts,
    select_validation_command,
)


def test_select_validation_command_prefers_db_for_prosper_chat_sql_targets() -> None:
    command = select_validation_command(
        title="Prosper chat DB task",
        targets=(
            "e2e-apps/prosper-chat/supabase/migrations/20260302101500_7f8d9de2-cb2b-4f35-b3b8-6d8a8f519e7e.sql",
            "e2e-apps/prosper-chat/supabase/assertions/anon_access_controls.sql",
        ),
        default_command="cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh full",
    )

    assert command == "./scripts/healer_validate.sh db"


def test_select_validation_command_keeps_full_for_mixed_prosper_chat_targets() -> None:
    command = select_validation_command(
        title="Prosper chat mixed task",
        targets=(
            "e2e-apps/prosper-chat/src/App.tsx",
            "e2e-apps/prosper-chat/supabase/migrations/20260302101500_7f8d9de2-cb2b-4f35-b3b8-6d8a8f519e7e.sql",
        ),
        default_command="cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh full",
    )

    assert command == "./scripts/healer_validate.sh full"


def test_select_validation_command_prefers_backend_for_prosper_chat_function_targets() -> None:
    command = select_validation_command(
        title="Prosper chat backend task",
        targets=(
            "e2e-apps/prosper-chat/supabase/functions/check-subscription/index.ts",
            "e2e-apps/prosper-chat/supabase/functions/_shared/billing.ts",
        ),
        default_command="cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh full",
    )

    assert command == "./scripts/healer_validate.sh backend"


def test_build_issue_drafts_adds_db_labels_and_validation_for_prosper_chat_family() -> None:
    drafts = build_issue_drafts(
        count=1,
        prefix="Prosper chat DB task",
        ready_label="healer:ready",
        family=PROSPER_CHAT_DB_FAMILY,
    )

    assert len(drafts) == 1
    draft = drafts[0]
    assert "Validation:\n- ./scripts/healer_validate.sh db\n" in draft.body
    assert "e2e-apps/prosper-chat/supabase/" in draft.body
    assert "healer:ready" in draft.labels
    assert "area:db" in draft.labels
    assert any(label.startswith("kind:") for label in draft.labels)


def test_available_issue_families_include_framework_expansions() -> None:
    families = available_issue_families()
    assert JS_FRAMEWORK_FAMILY in families
    assert PYTHON_FRAMEWORK_FAMILY in families
    assert PYTHON_DATA_ML_FAMILY in families


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
