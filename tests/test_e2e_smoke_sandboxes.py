from __future__ import annotations

from pathlib import Path

from flow_healer.language_strategies import get_strategy

ROOT = Path(__file__).resolve().parents[1]
E2E_SMOKE = ROOT / "e2e-smoke"


def test_all_supported_language_sandboxes_exist() -> None:
    expected = {
        "python": [
            "pyproject.toml",
            "smoke_math.py",
            "tests/test_smoke_math.py",
        ],
        "node": [
            "package.json",
            "src/add.js",
            "test/add.test.js",
        ],
        "js-next": [
            "package.json",
            "src/add.js",
            "tests/add.test.js",
        ],
        "js-vue-vite": [
            "package.json",
            "pnpm-lock.yaml",
            "src/add.js",
            "tests/add.test.js",
        ],
        "js-nuxt": [
            "package.json",
            "yarn.lock",
            "src/add.js",
            "tests/add.test.js",
        ],
        "js-angular": [
            "package.json",
            "bun.lockb",
            "src/add.js",
            "tests/add.test.js",
        ],
        "js-sveltekit": [
            "package.json",
            "src/add.js",
            "tests/add.test.js",
        ],
        "js-express": [
            "package.json",
            "src/add.js",
            "tests/add.test.js",
        ],
        "js-nest": [
            "package.json",
            "pnpm-workspace.yaml",
            "src/add.js",
            "tests/add.test.js",
        ],
        "js-remix": [
            "package.json",
            "app/utils/add.server.js",
            "tests/add.test.js",
        ],
        "js-astro": [
            "package.json",
            "src/utils/add.js",
            "tests/add.test.js",
        ],
        "js-solidstart": [
            "package.json",
            "src/lib/add.js",
            "tests/add.test.js",
        ],
        "js-qwik": [
            "package.json",
            "src/utils/add.ts",
            "tests/add.test.ts",
        ],
        "js-hono": [
            "package.json",
            "src/add.js",
            "tests/add.test.js",
        ],
        "js-koa": [
            "package.json",
            "src/add.js",
            "tests/add.test.js",
        ],
        "js-adonis": [
            "package.json",
            "app/services/add.ts",
            "tests/add.spec.ts",
        ],
        "js-redwoodsdk": [
            "package.json",
            "web/src/lib/add.ts",
            "web/tests/add.test.ts",
        ],
        "js-lit": [
            "package.json",
            "src/add.js",
            "tests/add.test.js",
        ],
        "js-alpine-vite": [
            "package.json",
            "src/add.js",
            "tests/add.test.js",
        ],
        "py-fastapi": [
            "pyproject.toml",
            "app/add.py",
            "tests/test_add.py",
        ],
        "py-django": [
            "pyproject.toml",
            "app/add.py",
            "tests/test_add.py",
        ],
        "py-flask": [
            "pyproject.toml",
            "app/add.py",
            "tests/test_add.py",
        ],
        "py-data-pandas": [
            "pyproject.toml",
            "app/add.py",
            "tests/test_add.py",
        ],
        "py-ml-sklearn": [
            "pyproject.toml",
            "app/add.py",
            "tests/test_add.py",
        ],
        "swift": [
            "Package.swift",
            "Sources/FlowHealerAdd/Add.swift",
            "Tests/FlowHealerAddTests/AddTests.swift",
        ],
    }

    for sandbox, required_files in expected.items():
        base = E2E_SMOKE / sandbox
        assert base.is_dir(), f"missing sandbox directory: {sandbox}"
        for relative in required_files:
            assert (base / relative).exists(), f"{sandbox} missing {relative}"


def test_sandbox_layout_matches_supported_language_strategies() -> None:
    expected = {
        "python": "python",
        "node": "node",
        "swift": "swift",
    }

    for sandbox, strategy_name in expected.items():
        base = E2E_SMOKE / sandbox
        strategy = get_strategy(strategy_name)
        assert base.exists()
        assert strategy.local_test_cmd, f"{strategy_name} should have a local test command"
