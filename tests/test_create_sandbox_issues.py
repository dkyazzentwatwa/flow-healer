from __future__ import annotations

import importlib.util
from pathlib import Path


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
