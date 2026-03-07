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
            "add.mjs",
            "add.test.mjs",
        ],
        "go": [
            "go.mod",
            "add/add.go",
            "add/add_test.go",
        ],
        "rust": [
            "Cargo.toml",
            "src/lib.rs",
            "tests/add.rs",
        ],
        "java-maven": [
            "pom.xml",
            "src/main/java/com/flowhealer/Add.java",
            "src/test/java/com/flowhealer/AddTest.java",
        ],
        "java-gradle": [
            "build.gradle",
            "settings.gradle",
            "gradlew",
            "src/main/java/com/flowhealer/Add.java",
            "src/test/java/com/flowhealer/AddTest.java",
        ],
        "ruby": [
            "Gemfile",
            "add.rb",
            "spec/add_spec.rb",
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
        "go": "go",
        "rust": "rust",
        "java-maven": "java_maven",
        "java-gradle": "java_gradle",
        "ruby": "ruby",
    }

    for sandbox, strategy_name in expected.items():
        base = E2E_SMOKE / sandbox
        strategy = get_strategy(strategy_name)
        assert base.exists()
        assert strategy.local_test_cmd, f"{strategy_name} should have a local test command"

    assert get_strategy("java_gradle").local_test_cmd[0] == "./gradlew"
    assert (E2E_SMOKE / "java-gradle" / "gradlew").exists()
