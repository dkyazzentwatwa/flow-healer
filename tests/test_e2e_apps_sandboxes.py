from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E2E_APPS = ROOT / "e2e-apps"


def test_all_demo_app_sandboxes_exist() -> None:
    expected = {
        "node-next": [
            "package.json",
            "app/layout.js",
            "app/page.js",
            "app/api/todos/route.js",
            "lib/todo-service.js",
            "tests/todo-service.test.js",
        ],
        "python-fastapi": [
            "pyproject.toml",
            "app/api.py",
            "app/service.py",
            "app/repository.py",
            "tests/test_domain_service.py",
            "tests/test_api_contract.py",
        ],
        "swift-todo": [
            "Package.swift",
            "Sources/TodoCore/TodoService.swift",
            "Sources/TodoCLI/main.swift",
            "Sources/TodoCLI/CompletionRenderer.swift",
            "Tests/TodoCoreTests/TodoServiceTests.swift",
            "Tests/TodoCLITests/TodoCLITests.swift",
        ],
    }

    for sandbox, required_files in expected.items():
        base = E2E_APPS / sandbox
        assert base.is_dir(), f"missing demo app sandbox: {sandbox}"
        for relative in required_files:
            assert (base / relative).exists(), f"{sandbox} missing {relative}"
