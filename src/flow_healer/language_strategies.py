from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class LanguageStrategy:
    """Describes how to install dependencies and run tests for a given language.

    Attributes
    ----------
    docker_image:
        Docker image to use when running tests in a container.
    docker_install_cmd:
        Shell command(s) to run inside the container before the test command.
        May be empty if no install step is needed.
    docker_test_cmd:
        The test command to run inside the container (already split into args).
    local_test_cmd:
        The test command to run on the host.  Empty list means skip the local
        gate for this language (useful when the toolchain is unlikely to be
        present in the healer's own environment).
    """

    docker_image: str
    docker_install_cmd: str
    docker_test_cmd: list[str] = field(default_factory=list)
    local_test_cmd: list[str] = field(default_factory=list)


# Default strategies per detected language.
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
    ),
    "node": LanguageStrategy(
        docker_image="node:20-slim",
        docker_install_cmd="npm install --prefer-offline 2>/dev/null || npm install",
        docker_test_cmd=["npm", "test", "--", "--passWithNoTests"],
        local_test_cmd=[],  # Node toolchain not guaranteed on healer host
    ),
    "go": LanguageStrategy(
        docker_image="golang:1.22-alpine",
        docker_install_cmd="",
        docker_test_cmd=["go", "test", "./..."],
        local_test_cmd=["go", "test", "./..."],
    ),
    "rust": LanguageStrategy(
        docker_image="rust:1-slim",
        docker_install_cmd="",
        docker_test_cmd=["cargo", "test"],
        local_test_cmd=["cargo", "test"],
    ),
    "java_maven": LanguageStrategy(
        docker_image="maven:3.9-eclipse-temurin-17-slim",
        docker_install_cmd="",
        docker_test_cmd=["mvn", "test", "-q", "--no-transfer-progress"],
        local_test_cmd=[],
    ),
    "java_gradle": LanguageStrategy(
        docker_image="gradle:8-jdk17",
        docker_install_cmd="",
        docker_test_cmd=["./gradlew", "test", "--no-daemon"],
        local_test_cmd=[],
    ),
    "ruby": LanguageStrategy(
        docker_image="ruby:3.2-slim",
        docker_install_cmd="bundle install -j4 --quiet",
        docker_test_cmd=["bundle", "exec", "rspec"],
        local_test_cmd=[],
    ),
    # Fallback when language cannot be determined
    "unknown": LanguageStrategy(
        docker_image="python:3.11-slim",
        docker_install_cmd="python -m pip install --disable-pip-version-check -q pytest",
        docker_test_cmd=["pytest", "-q"],
        local_test_cmd=[],
    ),
}


def get_strategy(
    language: str,
    *,
    docker_image: str = "",
    test_command: str = "",
    install_command: str = "",
) -> LanguageStrategy:
    """Return the :class:`LanguageStrategy` for *language*, with optional overrides.

    Parameters
    ----------
    language:
        The detected or configured language string (e.g. ``"python"``).
    docker_image:
        If non-empty, overrides the strategy's default Docker image.
    test_command:
        If non-empty, space-split and used as both the Docker and local test
        command (e.g. ``"npm run test:ci"``).
    install_command:
        If non-empty, overrides the strategy's Docker install step.
    """
    base = _STRATEGIES.get(language) or _STRATEGIES["unknown"]

    resolved_image = docker_image.strip() or base.docker_image
    resolved_install = install_command.strip() if install_command.strip() else base.docker_install_cmd

    if test_command.strip():
        resolved_test = test_command.strip().split()
        return LanguageStrategy(
            docker_image=resolved_image,
            docker_install_cmd=resolved_install,
            docker_test_cmd=resolved_test,
            local_test_cmd=resolved_test,
        )

    return LanguageStrategy(
        docker_image=resolved_image,
        docker_install_cmd=resolved_install,
        docker_test_cmd=list(base.docker_test_cmd),
        local_test_cmd=list(base.local_test_cmd),
    )
