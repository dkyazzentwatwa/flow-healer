from __future__ import annotations

from flow_healer.language_detector import detect_language, detect_language_details
from flow_healer.language_strategies import get_strategy, parse_command


def test_detect_language_returns_unknown_when_no_markers(tmp_path) -> None:
    assert detect_language(tmp_path) == "unknown"


def test_detect_language_prefers_specific_marker_order(tmp_path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    details = detect_language_details(tmp_path)
    assert details.language == "node"
    assert details.ambiguous is True
    assert "package.json" in details.markers
    assert "pyproject.toml" in details.markers


def test_parse_command_uses_shell_aware_parsing() -> None:
    parts = parse_command('npm run test:ci -- --reporter "dot list"')
    assert parts == ["npm", "run", "test:ci", "--", "--reporter", "dot list"]


def test_get_strategy_defaults_to_python_for_unknown_language() -> None:
    strategy = get_strategy("not_real")
    assert strategy.docker_image.startswith("python:")
    assert strategy.docker_test_cmd == ["pytest", "-q"]
    assert strategy.supports_targeted_paths is True


def test_all_supported_strategies_have_local_test_cmd() -> None:
    supported = ["python", "node", "go", "rust", "java_maven", "java_gradle", "ruby"]
    for lang in supported:
        strategy = get_strategy(lang)
        assert strategy.local_test_cmd, f"{lang} strategy has empty local_test_cmd"


def test_ruby_strategy_upgrades_bundler_before_bundle_install() -> None:
    strategy = get_strategy("ruby")
    assert strategy.docker_install_cmd == "gem install bundler -v 2.5.23 && bundle _2.5.23_ install -j4 --quiet"
    assert strategy.docker_test_cmd == ["bundle", "_2.5.23_", "exec", "rspec"]
    assert strategy.local_test_cmd == ["bundle", "exec", "rspec"]


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
