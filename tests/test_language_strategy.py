from __future__ import annotations

from flow_healer.language_detector import detect_language, detect_language_details
from flow_healer.language_strategies import (
    SUPPORTED_LANGUAGES,
    ensure_supported_language,
    get_strategy,
    parse_command,
)


def test_detect_language_returns_unknown_when_no_markers(tmp_path) -> None:
    assert detect_language(tmp_path) == "unknown"


def test_detect_language_returns_unknown_for_mixed_top_level_markers(tmp_path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    details = detect_language_details(tmp_path)
    assert details.language == "unknown"
    assert details.ambiguous is True
    assert "package.json" in details.markers
    assert "pyproject.toml" in details.markers


def test_detect_language_prefers_language_with_more_markers(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    details = detect_language_details(tmp_path)

    assert details.language == "python"
    assert details.ambiguous is False


def test_detect_language_recognizes_swift_package_manager_marker(tmp_path) -> None:
    (tmp_path / "Package.swift").write_text("// swift-tools-version: 6.0\n", encoding="utf-8")

    details = detect_language_details(tmp_path)

    assert details.language == "swift"
    assert details.markers == ("Package.swift",)
    assert details.ambiguous is False


def test_parse_command_uses_shell_aware_parsing() -> None:
    parts = parse_command('npm run test:ci -- --reporter "dot list"')
    assert parts == ["npm", "run", "test:ci", "--", "--reporter", "dot list"]


def test_get_strategy_defaults_to_python_for_unknown_language() -> None:
    strategy = get_strategy("not_real")
    assert strategy.docker_image.startswith("python:")
    assert strategy.docker_test_cmd == ["pytest", "-q"]
    assert strategy.supports_targeted_paths is True


def test_all_supported_strategies_have_local_test_cmd() -> None:
    for lang in SUPPORTED_LANGUAGES:
        strategy = get_strategy(lang)
        assert strategy.local_test_cmd, f"{lang} strategy has empty local_test_cmd"


def test_ensure_supported_language_accepts_expanded_reference_languages() -> None:
    assert ensure_supported_language("ruby", source="test fixture") == "ruby"
    assert ensure_supported_language("swift", source="test fixture") == "swift"
    assert ensure_supported_language("go", source="test fixture") == "go"
    assert ensure_supported_language("rust", source="test fixture") == "rust"
    assert ensure_supported_language("java_gradle", source="test fixture") == "java_gradle"


def test_get_strategy_custom_test_command_enables_pytest_targeting() -> None:
    strategy = get_strategy(
        "node",
        test_command='python -m pytest -q',
        docker_image="python:3.12-slim",
    )
    assert strategy.docker_image == "python:3.12-slim"
    assert strategy.docker_test_cmd == ["python", "-m", "pytest", "-q"]
    assert strategy.local_test_cmd == ["python", "-m", "pytest", "-q"]
    assert strategy.supports_targeted_paths is True


def test_get_strategy_uses_expanded_language_defaults() -> None:
    ruby = get_strategy("ruby")
    assert ruby.local_test_cmd == ["bundle", "exec", "rspec"]
    assert ruby.supports_targeted_paths is True
    assert ruby.supports_docker is False

    swift = get_strategy("swift")
    assert swift.local_test_cmd == ["swift", "test"]
    assert swift.supports_docker is False

    go = get_strategy("go")
    assert go.local_test_cmd == ["go", "test", "./..."]
    assert go.supports_docker is False

    rust = get_strategy("rust")
    assert rust.local_test_cmd == ["cargo", "test"]
    assert rust.supports_docker is False

    java = get_strategy("java_gradle")
    assert java.local_test_cmd == ["./gradlew", "test", "--no-daemon"]
    assert java.supports_docker is False


def test_get_strategy_uses_node_framework_defaults() -> None:
    strategy = get_strategy("node", framework="next")
    assert strategy.language == "node"
    assert strategy.framework == "next"
    assert strategy.local_test_cmd == ["npm", "test", "--", "--passWithNoTests"]


def test_get_strategy_uses_python_framework_install_defaults() -> None:
    strategy = get_strategy("python", framework="django")
    assert strategy.language == "python"
    assert strategy.framework == "django"
    assert "django" in strategy.docker_install_cmd
