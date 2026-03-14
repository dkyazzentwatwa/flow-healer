from __future__ import annotations

from pathlib import Path

from flow_healer.issue_generation import (
    DEFAULT_FAMILY,
    HARD_NON_PROSPER_FAMILY,
    JS_FRAMEWORK_FAMILY,
    MEGA_FINAL_WAVE_1_FAMILY,
    MEGA_FINAL_WAVE_2_FAMILY,
    PROD_EVAL_HYBRID_HEAVY_FAMILY,
    PYTHON_DATA_ML_FAMILY,
    PYTHON_FRAMEWORK_FAMILY,
    PROSPER_CHAT_DB_FAMILY,
    available_issue_families,
    build_issue_drafts,
    render_issue_body,
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


def test_render_issue_body_includes_execution_root_and_runtime_profile_for_browser_backed_app() -> None:
    body = render_issue_body(
        ("e2e-apps/node-next/app/page.js",),
        "cd e2e-apps/node-next && npm test -- --passWithNoTests",
    )

    assert "Execution root:\n- e2e-apps/node-next\n" in body
    assert "Runtime profile: node-next-web\n" in body
    assert "Validation:\n- cd e2e-apps/node-next && npm test -- --passWithNoTests\n" in body


def test_render_issue_body_includes_runtime_contract_for_ruby_browser_app() -> None:
    body = render_issue_body(
        ("e2e-apps/ruby-rails-web/app/controllers/sessions_controller.rb",),
        "cd e2e-apps/ruby-rails-web && bundle exec rspec",
    )

    assert "Execution root:\n- e2e-apps/ruby-rails-web\n" in body
    assert "Runtime profile: ruby-rails-web\n" in body
    assert "Validation:\n- cd e2e-apps/ruby-rails-web && bundle exec rspec\n" in body


def test_render_issue_body_includes_runtime_contract_for_java_browser_app() -> None:
    body = render_issue_body(
        ("e2e-apps/java-spring-web/src/main/java/example/web/LoginController.java",),
        "cd e2e-apps/java-spring-web && ./gradlew test --no-daemon",
    )

    assert "Execution root:\n- e2e-apps/java-spring-web\n" in body
    assert "Runtime profile: java-spring-web\n" in body
    assert "Validation:\n- cd e2e-apps/java-spring-web && ./gradlew test --no-daemon\n" in body


def test_available_issue_families_include_framework_expansions() -> None:
    families = available_issue_families()
    assert HARD_NON_PROSPER_FAMILY in families
    assert JS_FRAMEWORK_FAMILY in families
    assert PYTHON_FRAMEWORK_FAMILY in families
    assert PYTHON_DATA_ML_FAMILY in families
    assert MEGA_FINAL_WAVE_1_FAMILY in families
    assert MEGA_FINAL_WAVE_2_FAMILY in families
    assert PROD_EVAL_HYBRID_HEAVY_FAMILY in families


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


def test_build_issue_drafts_supports_prod_eval_hybrid_heavy_family() -> None:
    drafts = build_issue_drafts(
        count=10,
        prefix="Prod eval hybrid-heavy",
        ready_label="healer:ready",
        extra_labels=("campaign:prod-eval",),
        family=PROD_EVAL_HYBRID_HEAVY_FAMILY,
    )

    assert len(drafts) == 10
    assert all("healer:ready" in draft.labels for draft in drafts)
    assert all("campaign:prod-eval" in draft.labels for draft in drafts)
    assert sum("eval:control" in draft.labels for draft in drafts) == 2
    assert sum("eval:hybrid" in draft.labels for draft in drafts) == 6
    assert sum("eval:messy" in draft.labels for draft in drafts) == 2

    hybrid = next(draft for draft in drafts if "eval:hybrid" in draft.labels)
    assert "Observed:" in hybrid.body
    assert "Expected:" in hybrid.body
    assert "Required code outputs:" in hybrid.body
    assert "Validation:\n- cd " in hybrid.body

    messy = next(draft for draft in drafts if "eval:messy" in draft.labels)
    assert "Observed:" not in messy.body
    assert "Validation:\n- " in messy.body
    assert "Required code outputs:" in messy.body


def test_build_issue_drafts_supports_hard_non_prosper_family() -> None:
    drafts = build_issue_drafts(
        count=10,
        prefix="Hard batch",
        ready_label="healer:ready",
        extra_labels=("campaign:hard-non-prosper",),
        family=HARD_NON_PROSPER_FAMILY,
    )

    assert len(drafts) == 10
    assert all("healer:ready" in draft.labels for draft in drafts)
    assert all("campaign:hard-non-prosper" in draft.labels for draft in drafts)
    assert all("difficulty:hard" in draft.labels for draft in drafts)
    assert all("prosper" not in draft.title.lower() for draft in drafts)
    assert all("prosper" not in draft.body.lower() for draft in drafts)

    execution_roots: set[str] = set()
    for draft in drafts:
        spec = compile_task_spec(issue_title=draft.title, issue_body=draft.body)
        execution_roots.add(spec.execution_root)

    assert "e2e-apps/nobi-owl-trader" in execution_roots
    assert "e2e-apps/node-next" in execution_roots
    assert "e2e-apps/python-fastapi" in execution_roots
    assert any(root.startswith("e2e-smoke/") for root in execution_roots)


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


def test_validate_issue_drafts_accepts_prod_eval_hybrid_heavy_catalog() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    drafts = build_issue_drafts(
        count=10,
        prefix="Prod eval hybrid-heavy",
        ready_label="healer:ready",
        extra_labels=("campaign:prod-eval",),
        family=PROD_EVAL_HYBRID_HEAVY_FAMILY,
    )

    validate_issue_drafts(drafts, repo_root=repo_root)


def test_validate_issue_drafts_accepts_hard_non_prosper_catalog() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    drafts = build_issue_drafts(
        count=10,
        prefix="Hard batch",
        ready_label="healer:ready",
        extra_labels=("campaign:hard-non-prosper",),
        family=HARD_NON_PROSPER_FAMILY,
    )

    validate_issue_drafts(drafts, repo_root=repo_root)


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


def test_validate_issue_drafts_rejects_browser_backed_draft_missing_explicit_runtime_contract() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    draft = build_issue_drafts(
        count=1,
        prefix="Broken node-next app draft",
        ready_label="healer:ready",
        family=DEFAULT_FAMILY,
    )[0].__class__(
        title="Broken node-next app draft",
        body=(
            "Required code outputs:\n"
            "- e2e-apps/node-next/app/page.js\n\n"
            "Validation:\n"
            "- cd e2e-apps/node-next && npm test -- --passWithNoTests\n"
        ),
        labels=("healer:ready",),
    )

    try:
        validate_issue_drafts([draft], repo_root=repo_root)
    except ValueError as exc:
        assert "runtime contract" in str(exc).lower()
    else:
        raise AssertionError("expected validation failure for missing browser-backed runtime contract")


def test_validate_issue_drafts_rejects_unfocused_validation_command() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    draft = build_issue_drafts(
        count=1,
        prefix="Broken node draft",
        ready_label="healer:ready",
        family=DEFAULT_FAMILY,
    )[0].__class__(
        title="Broken node draft",
        body=(
            "Required code outputs:\n"
            "- e2e-smoke/node/src/add.js\n\n"
            "Execution root:\n"
            "- e2e-smoke/node\n\n"
            "Validation:\n"
            "- npm test -- --passWithNoTests\n"
        ),
        labels=("healer:ready",),
    )

    try:
        validate_issue_drafts([draft], repo_root=repo_root)
    except ValueError as exc:
        assert "validation command must be rooted" in str(exc).lower()
    else:
        raise AssertionError("expected validation failure for unfocused validation command")


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


def test_prod_eval_hybrid_heavy_catalog_round_trips_through_task_spec_parser() -> None:
    drafts = build_issue_drafts(
        count=10,
        prefix="Parser check prod eval",
        ready_label="healer:ready",
        family=PROD_EVAL_HYBRID_HEAVY_FAMILY,
    )

    for draft in drafts:
        spec = compile_task_spec(issue_title=draft.title, issue_body=draft.body)
        assert spec.execution_root.startswith(("e2e-smoke/", "e2e-apps/"))
        assert spec.validation_commands
        assert spec.output_targets


def test_hard_non_prosper_catalog_round_trips_through_task_spec_parser() -> None:
    drafts = build_issue_drafts(
        count=10,
        prefix="Parser check hard batch",
        ready_label="healer:ready",
        family=HARD_NON_PROSPER_FAMILY,
    )

    for draft in drafts:
        spec = compile_task_spec(issue_title=draft.title, issue_body=draft.body)
        assert spec.execution_root.startswith(("e2e-smoke/", "e2e-apps/"))
        assert "prosper" not in spec.execution_root.lower()
        assert spec.validation_commands
        assert spec.output_targets


def test_browser_backed_generated_draft_round_trips_runtime_profile() -> None:
    drafts = build_issue_drafts(
        count=30,
        prefix="Parser check browser backed",
        ready_label="healer:ready",
        family=MEGA_FINAL_WAVE_1_FAMILY,
    )

    expected_profiles = {
        "e2e-apps/node-next": "node-next-web",
        "e2e-apps/ruby-rails-web": "ruby-rails-web",
        "e2e-apps/java-spring-web": "java-spring-web",
    }

    for execution_root, runtime_profile in expected_profiles.items():
        draft = next(draft for draft in drafts if execution_root in draft.body)
        spec = compile_task_spec(issue_title=draft.title, issue_body=draft.body)

        assert spec.execution_root == execution_root
        assert spec.runtime_profile == runtime_profile


def test_browser_backed_generated_drafts_round_trip_runtime_profiles_across_active_roots() -> None:
    drafts = build_issue_drafts(
        count=30,
        prefix="Parser check browser backed roots",
        ready_label="healer:ready",
        family=MEGA_FINAL_WAVE_1_FAMILY,
    )

    expected_profiles = {
        "e2e-apps/node-next": "node-next-web",
        "e2e-apps/ruby-rails-web": "ruby-rails-web",
        "e2e-apps/java-spring-web": "java-spring-web",
    }
    seen_roots: set[str] = set()

    for draft in drafts:
        spec = compile_task_spec(issue_title=draft.title, issue_body=draft.body)
        expected_runtime_profile = expected_profiles.get(spec.execution_root)
        if not expected_runtime_profile:
            continue
        seen_roots.add(spec.execution_root)
        assert spec.runtime_profile == expected_runtime_profile

    assert seen_roots == set(expected_profiles)
