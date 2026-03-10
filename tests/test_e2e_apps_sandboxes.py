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
        "prosper-chat": [
            "package.json",
            "src/main.tsx",
            "src/App.tsx",
            "supabase/config.toml",
            "supabase/assertions/manifest.json",
            "supabase/assertions/schema_core.sql",
            "supabase/functions/chat-widget/index.ts",
            "supabase/migrations/20260301190615_15638062-0f7f-4cc7-96f5-79466e4cb26b.sql",
            "scripts/healer_validate.sh",
        ],
    }

    for sandbox, required_files in expected.items():
        base = E2E_APPS / sandbox
        assert base.is_dir(), f"missing demo app sandbox: {sandbox}"
        for relative in required_files:
            assert (base / relative).exists(), f"{sandbox} missing {relative}"
