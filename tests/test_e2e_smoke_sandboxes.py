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
