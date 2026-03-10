from __future__ import annotations

import shlex
from dataclasses import dataclass, field


SUPPORTED_LANGUAGES: tuple[str, ...] = ("python", "node")
REMOVED_LANGUAGES: tuple[str, ...] = ("go", "rust", "java_maven", "java_gradle", "ruby", "swift")
SUPPORTED_LANGUAGE_SET = frozenset(SUPPORTED_LANGUAGES)
REMOVED_LANGUAGE_SET = frozenset(REMOVED_LANGUAGES)


@dataclass(slots=True, frozen=True)
class LanguageStrategy:
    docker_image: str
    docker_install_cmd: str
    docker_test_cmd: list[str] = field(default_factory=list)
    local_test_cmd: list[str] = field(default_factory=list)
    supports_targeted_paths: bool = False
    supports_docker: bool = True


class UnsupportedLanguageError(ValueError):
    pass


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
_EMPTY_STRATEGY = LanguageStrategy(
    docker_image="",
    docker_install_cmd="",
    docker_test_cmd=[],
    local_test_cmd=[],
    supports_targeted_paths=False,
    supports_docker=False,
)


def parse_command(command: str) -> list[str]:
    raw = str(command or "").strip()
    if not raw:
        return []
    try:
        return shlex.split(raw)
    except ValueError:
        return raw.split()


def normalize_language(language: str) -> str:
    return str(language or "").strip().lower()


def is_supported_language(language: str) -> bool:
    return normalize_language(language) in SUPPORTED_LANGUAGE_SET


def is_removed_language(language: str) -> bool:
    return normalize_language(language) in REMOVED_LANGUAGE_SET


def ensure_supported_language(language: str, *, source: str = "configuration") -> str:
    normalized = normalize_language(language)
    if not normalized or normalized == "unknown":
        return normalized
    if is_supported_language(normalized):
        return normalized
    if is_removed_language(normalized):
        raise UnsupportedLanguageError(
            f"Unsupported language '{normalized}' from {source}. "
            "Flow Healer supports only python and node."
        )
    return normalized


def get_strategy(
    language: str,
    *,
    docker_image: str = "",
    test_command: str = "",
    install_command: str = "",
) -> LanguageStrategy:
    normalized = str(language or "").strip()
    base = _EMPTY_STRATEGY if not normalized else (_STRATEGIES.get(normalized) or _STRATEGIES["unknown"])

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
            supports_docker=base.supports_docker,
        )

    return LanguageStrategy(
        docker_image=resolved_image,
        docker_install_cmd=resolved_install,
        docker_test_cmd=list(base.docker_test_cmd),
        local_test_cmd=list(base.local_test_cmd),
        supports_targeted_paths=base.supports_targeted_paths,
        supports_docker=base.supports_docker,
    )


def _supports_targeted_paths(command: list[str]) -> bool:
    if not command:
        return False
    first = command[0]
    if first in {"pytest", "py.test", "rspec"}:
        return True
    if first.startswith("python") and "pytest" in command:
        return True
    return False
