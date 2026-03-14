from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "create_sandbox_issues.py"
    spec = importlib.util.spec_from_file_location("create_sandbox_issues", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_is_python_js_only_draft_accepts_js_issue_contract() -> None:
    module = _load_module()
    body = (
        "Required code outputs:\n"
        "- e2e-smoke/js-remix/app/utils/add.server.js\n\n"
        "Validation:\n"
        "- cd e2e-smoke/js-remix && npm test -- --passWithNoTests\n"
    )

    assert module._is_python_js_only_draft(body) is True


def test_is_python_js_only_draft_rejects_non_js_python_validator() -> None:
    module = _load_module()
    body = (
        "Required code outputs:\n"
        "- e2e-smoke/java-spring/src/main/java/example/AddService.java\n\n"
        "Validation:\n"
        "- cd e2e-smoke/java-spring && ./gradlew test --no-daemon\n"
    )

    assert module._is_python_js_only_draft(body) is False


def test_is_python_js_only_draft_accepts_generic_node_and_python_roots() -> None:
    module = _load_module()
    node_body = (
        "Required code outputs:\n"
        "- e2e-smoke/node/src/add.js\n\n"
        "Validation:\n"
        "- cd e2e-smoke/node && npm test -- --passWithNoTests\n"
    )
    python_body = (
        "Required code outputs:\n"
        "- e2e-smoke/python/smoke_math.py\n\n"
        "Validation:\n"
        "- cd e2e-smoke/python && pytest -q\n"
    )

    assert module._is_python_js_only_draft(node_body) is True
    assert module._is_python_js_only_draft(python_body) is True


def test_is_python_js_only_draft_accepts_node_app_runtime_contract_lines() -> None:
    module = _load_module()
    body = (
        "Required code outputs:\n"
        "- e2e-apps/node-next/app/page.js\n\n"
        "Execution root:\n"
        "- e2e-apps/node-next\n\n"
        "Runtime profile: node-next-web\n\n"
        "Validation:\n"
        "- cd e2e-apps/node-next && npm test -- --passWithNoTests\n"
    )

    assert module._is_python_js_only_draft(body) is True


def test_is_python_js_only_draft_ignores_non_contract_bullets_with_paths() -> None:
    module = _load_module()
    body = (
        "Observed:\n"
        "- manual repro mentioned /tmp/runtime-note.txt but not as a code target\n\n"
        "Required code outputs:\n"
        "- e2e-smoke/node/src/add.js\n\n"
        "Validation:\n"
        "- cd e2e-smoke/node && npm test -- --passWithNoTests\n"
    )

    assert module._is_python_js_only_draft(body) is True


def test_validate_drafts_or_die_accepts_mega_final_wave() -> None:
    module = _load_module()
    drafts = module.build_issue_drafts(
        count=30,
        prefix="Mega final sandbox wave 1",
        ready_label="healer:ready",
        extra_labels=("campaign:mega-final", "wave:1"),
        family="mega-final-wave-1",
    )

    module.validate_drafts_or_die(drafts)


def test_validate_drafts_or_die_accepts_prod_eval_hybrid_heavy_wave() -> None:
    module = _load_module()
    drafts = module.build_issue_drafts(
        count=10,
        prefix="Prod eval hybrid-heavy",
        ready_label="healer:ready",
        extra_labels=("campaign:prod-eval",),
        family="prod-eval-hybrid-heavy",
    )

    module.validate_drafts_or_die(drafts)


def test_validate_drafts_or_die_accepts_hard_non_prosper_wave() -> None:
    module = _load_module()
    drafts = module.build_issue_drafts(
        count=10,
        prefix="Hard non-Prosper",
        ready_label="healer:ready",
        extra_labels=("campaign:hard-non-prosper",),
        family="hard-non-prosper",
    )

    assert all(module._is_python_js_only_draft(draft.body) for draft in drafts)
    module.validate_drafts_or_die(drafts)


def test_validate_drafts_or_die_rejects_missing_target() -> None:
    module = _load_module()
    draft = module.build_issue_drafts(
        count=1,
        prefix="Broken wave",
        ready_label="healer:ready",
        family="default",
    )[0]
    broken = SimpleNamespace(
        title=draft.title,
        body=(
            "Required code outputs:\n"
            "- e2e-apps/python-fastapi/app/missing.py\n\n"
            "Validation:\n"
            "- cd e2e-apps/python-fastapi && pytest -q\n"
        ),
        labels=draft.labels,
    )

    try:
        module.validate_drafts_or_die([broken])
    except SystemExit as exc:
        assert "missing target" in str(exc).lower()
    else:
        raise AssertionError("expected SystemExit for invalid draft")
