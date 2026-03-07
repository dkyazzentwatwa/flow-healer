from __future__ import annotations

import shlex
from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class LanguageStrategy:
    docker_image: str
    docker_install_cmd: str
    docker_test_cmd: list[str] = field(default_factory=list)
    local_test_cmd: list[str] = field(default_factory=list)
    supports_targeted_paths: bool = False


_STRATEGIES: dict[str, LanguageStrategy] = {
    "python": LanguageStrategy(
        docker_image="python:3.11-slim",
        docker_install_cmd=(
            "python -m pip install --disable-pip-version-check -q pytest && "
            "if [ -f pyproject.toml ] || [ -f setup.py ] || [ -f setup.cfg ]; then "
            "python -m pip install --disable-pip-version-check -q -e .; fi"
        ),
        docker_test_cmd=["pytest", "-q"],
        local_test_cmd=["pytest", "-q"],
        supports_targeted_paths=True,
    ),
    "node": LanguageStrategy(
        docker_image="node:20-slim",
        docker_install_cmd="npm install --prefer-offline 2>/dev/null || npm install",
        docker_test_cmd=["npm", "test", "--", "--passWithNoTests"],
        local_test_cmd=["npm", "test", "--", "--passWithNoTests"],
        supports_targeted_paths=False,
    ),
    "go": LanguageStrategy(
        docker_image="golang:1.22-alpine",
        docker_install_cmd="",
        docker_test_cmd=["go", "test", "./..."],
        local_test_cmd=["go", "test", "./..."],
        supports_targeted_paths=False,
    ),
    "rust": LanguageStrategy(
        docker_image="rust:1-slim",
        docker_install_cmd="",
        docker_test_cmd=["cargo", "test"],
        local_test_cmd=["cargo", "test"],
        supports_targeted_paths=False,
    ),
    "java_maven": LanguageStrategy(
        docker_image="maven:3.9-eclipse-temurin-17",
        docker_install_cmd="",
        docker_test_cmd=["mvn", "test", "-q", "--no-transfer-progress"],
        local_test_cmd=["mvn", "test", "-q", "--no-transfer-progress"],
        supports_targeted_paths=False,
    ),
    "java_gradle": LanguageStrategy(
        docker_image="gradle:8-jdk17",
        docker_install_cmd="",
        docker_test_cmd=["./gradlew", "test", "--no-daemon"],
        local_test_cmd=["./gradlew", "test", "--no-daemon"],
        supports_targeted_paths=False,
    ),
    "ruby": LanguageStrategy(
        docker_image="ruby:3.2-slim",
        docker_install_cmd="bundle install -j4 --quiet",
        docker_test_cmd=["bundle", "exec", "rspec"],
        local_test_cmd=["bundle", "exec", "rspec"],
        supports_targeted_paths=True,
    ),
    # Conservative fallback preserves the historical Python execution path.
    "unknown": LanguageStrategy(
        docker_image="python:3.11-slim",
        docker_install_cmd=(
            "python -m pip install --disable-pip-version-check -q pytest && "
            "if [ -f pyproject.toml ] || [ -f setup.py ] || [ -f setup.cfg ]; then "
            "python -m pip install --disable-pip-version-check -q -e .; fi"
        ),
        docker_test_cmd=["pytest", "-q"],
        local_test_cmd=["pytest", "-q"],
        supports_targeted_paths=True,
    ),
}


def parse_command(command: str) -> list[str]:
    raw = str(command or "").strip()
    if not raw:
        return []
    try:
        return shlex.split(raw)
    except ValueError:
        return raw.split()


def get_strategy(
    language: str,
    *,
    docker_image: str = "",
    test_command: str = "",
    install_command: str = "",
) -> LanguageStrategy:
    base = _STRATEGIES.get(str(language or "").strip()) or _STRATEGIES["unknown"]

    resolved_image = docker_image.strip() or base.docker_image
    resolved_install = install_command.strip() if install_command.strip() else base.docker_install_cmd
    custom_test = parse_command(test_command)

    if custom_test:
        return LanguageStrategy(
            docker_image=resolved_image,
            docker_install_cmd=resolved_install,
            docker_test_cmd=custom_test,
            local_test_cmd=custom_test,
            supports_targeted_paths=_supports_targeted_paths(custom_test),
        )

    return LanguageStrategy(
        docker_image=resolved_image,
        docker_install_cmd=resolved_install,
        docker_test_cmd=list(base.docker_test_cmd),
        local_test_cmd=list(base.local_test_cmd),
        supports_targeted_paths=base.supports_targeted_paths,
    )


def _supports_targeted_paths(command: list[str]) -> bool:
    if not command:
        return False
    first = command[0]
    if first in {"pytest", "py.test", "rspec"}:
        return True
    if first == "python" and "pytest" in command:
        return True
    return False
