from __future__ import annotations

import shlex
from dataclasses import dataclass, field


SUPPORTED_LANGUAGES: tuple[str, ...] = ("python", "node", "swift", "go", "rust", "java_gradle", "ruby")
REMOVED_LANGUAGES: tuple[str, ...] = ("java_maven",)
SUPPORTED_LANGUAGE_SET = frozenset(SUPPORTED_LANGUAGES)
REMOVED_LANGUAGE_SET = frozenset(REMOVED_LANGUAGES)


@dataclass(slots=True, frozen=True)
class LanguageStrategy:
    language: str
    framework: str
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
        language="python",
        framework="generic",
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
        language="node",
        framework="generic",
        docker_image="node:20-slim",
        docker_install_cmd="npm install --prefer-offline 2>/dev/null || npm install",
        docker_test_cmd=["npm", "test", "--", "--passWithNoTests"],
        local_test_cmd=["npm", "test", "--", "--passWithNoTests"],
        supports_targeted_paths=False,
    ),
    "swift": LanguageStrategy(
        language="swift",
        framework="generic",
        docker_image="",
        docker_install_cmd="",
        docker_test_cmd=[],
        local_test_cmd=["swift", "test"],
        supports_targeted_paths=False,
        supports_docker=False,
    ),
    "go": LanguageStrategy(
        language="go",
        framework="generic",
        docker_image="",
        docker_install_cmd="",
        docker_test_cmd=[],
        local_test_cmd=["go", "test", "./..."],
        supports_targeted_paths=False,
        supports_docker=False,
    ),
    "rust": LanguageStrategy(
        language="rust",
        framework="generic",
        docker_image="",
        docker_install_cmd="",
        docker_test_cmd=[],
        local_test_cmd=["cargo", "test"],
        supports_targeted_paths=False,
        supports_docker=False,
    ),
    "java_gradle": LanguageStrategy(
        language="java_gradle",
        framework="generic",
        docker_image="",
        docker_install_cmd="",
        docker_test_cmd=[],
        local_test_cmd=["./gradlew", "test", "--no-daemon"],
        supports_targeted_paths=False,
        supports_docker=False,
    ),
    "ruby": LanguageStrategy(
        language="ruby",
        framework="generic",
        docker_image="",
        docker_install_cmd="",
        docker_test_cmd=[],
        local_test_cmd=["bundle", "exec", "rspec"],
        supports_targeted_paths=True,
        supports_docker=False,
    ),
    # Conservative fallback preserves the historical Python execution path.
    "unknown": LanguageStrategy(
        language="unknown",
        framework="generic",
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
    language="",
    framework="",
    docker_image="",
    docker_install_cmd="",
    docker_test_cmd=[],
    local_test_cmd=[],
    supports_targeted_paths=False,
    supports_docker=False,
)

_NODE_FRAMEWORK_INSTALL: dict[str, str] = {
    "next": "npm install --prefer-offline 2>/dev/null || npm install",
    "vue_vite": "npm install --prefer-offline 2>/dev/null || npm install",
    "nuxt": "npm install --prefer-offline 2>/dev/null || npm install",
    "angular": "npm install --prefer-offline 2>/dev/null || npm install",
    "sveltekit": "npm install --prefer-offline 2>/dev/null || npm install",
    "express": "npm install --prefer-offline 2>/dev/null || npm install",
    "nest": "npm install --prefer-offline 2>/dev/null || npm install",
}

_NODE_FRAMEWORK_TEST: dict[str, list[str]] = {
    "next": ["npm", "test", "--", "--passWithNoTests"],
    "vue_vite": ["npm", "test", "--", "--passWithNoTests"],
    "nuxt": ["npm", "test", "--", "--passWithNoTests"],
    "angular": ["npm", "test", "--", "--passWithNoTests"],
    "sveltekit": ["npm", "test", "--", "--passWithNoTests"],
    "express": ["npm", "test", "--", "--passWithNoTests"],
    "nest": ["npm", "test", "--", "--passWithNoTests"],
}

_PY_FRAMEWORK_INSTALL: dict[str, str] = {
    "fastapi": (
        "python -m pip install --disable-pip-version-check -q pytest && "
        "python -m pip install --disable-pip-version-check -q fastapi uvicorn"
    ),
    "django": (
        "python -m pip install --disable-pip-version-check -q pytest && "
        "python -m pip install --disable-pip-version-check -q django"
    ),
    "flask": (
        "python -m pip install --disable-pip-version-check -q pytest && "
        "python -m pip install --disable-pip-version-check -q flask"
    ),
    "pandas": (
        "python -m pip install --disable-pip-version-check -q pytest && "
        "python -m pip install --disable-pip-version-check -q pandas"
    ),
    "sklearn": (
        "python -m pip install --disable-pip-version-check -q pytest && "
        "python -m pip install --disable-pip-version-check -q scikit-learn"
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
            f"Flow Healer supports {', '.join(SUPPORTED_LANGUAGES)}."
        )
    return normalized


def get_strategy(
    language: str,
    *,
    framework: str = "",
    docker_image: str = "",
    test_command: str = "",
    install_command: str = "",
) -> LanguageStrategy:
    normalized = str(language or "").strip()
    normalized_framework = str(framework or "").strip().lower()
    base = _EMPTY_STRATEGY if not normalized else (_STRATEGIES.get(normalized) or _STRATEGIES["unknown"])

    resolved_image = docker_image.strip() or base.docker_image
    resolved_install = install_command.strip() if install_command.strip() else _default_install_for_framework(
        language=normalized,
        framework=normalized_framework,
        fallback=base.docker_install_cmd,
    )
    custom_test = parse_command(test_command)
    default_test = _default_test_for_framework(
        language=normalized,
        framework=normalized_framework,
        fallback=list(base.local_test_cmd),
    )

    if custom_test:
        return LanguageStrategy(
            language=normalized or base.language,
            framework=normalized_framework or base.framework,
            docker_image=resolved_image,
            docker_install_cmd=resolved_install,
            docker_test_cmd=custom_test,
            local_test_cmd=custom_test,
            supports_targeted_paths=_supports_targeted_paths(custom_test),
            supports_docker=base.supports_docker,
        )

    return LanguageStrategy(
        language=normalized or base.language,
        framework=normalized_framework or base.framework,
        docker_image=resolved_image,
        docker_install_cmd=resolved_install,
        docker_test_cmd=list(default_test),
        local_test_cmd=list(default_test),
        supports_targeted_paths=base.supports_targeted_paths or _supports_targeted_paths(default_test),
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


def _default_install_for_framework(*, language: str, framework: str, fallback: str) -> str:
    if language == "node" and framework in _NODE_FRAMEWORK_INSTALL:
        return _NODE_FRAMEWORK_INSTALL[framework]
    if language == "python" and framework in _PY_FRAMEWORK_INSTALL:
        return _PY_FRAMEWORK_INSTALL[framework]
    return fallback


def _default_test_for_framework(*, language: str, framework: str, fallback: list[str]) -> list[str]:
    if language == "node" and framework in _NODE_FRAMEWORK_TEST:
        return list(_NODE_FRAMEWORK_TEST[framework])
    return fallback
