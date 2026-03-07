from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class LanguageDetection:
    language: str
    markers: tuple[str, ...]
    ambiguous: bool = False


# Ordered by specificity: first match is the default when markers are mixed.
_LANGUAGE_MARKERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("package.json",), "node"),
    (("Package.swift",), "swift"),
    (("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"), "python"),
    (("go.mod",), "go"),
    (("Cargo.toml",), "rust"),
    (("pom.xml",), "java_maven"),
    (("build.gradle", "build.gradle.kts"), "java_gradle"),
    (("Gemfile",), "ruby"),
)


def detect_language(repo_path: Path) -> str:
    return detect_language_details(repo_path).language


def detect_language_details(repo_path: Path) -> LanguageDetection:
    root = Path(repo_path)
    hits: list[tuple[str, str]] = []
    for markers, language in _LANGUAGE_MARKERS:
        for marker in markers:
            if (root / marker).exists():
                hits.append((language, marker))
                break

    if not hits:
        return LanguageDetection(language="unknown", markers=(), ambiguous=False)

    first_language = hits[0][0]
    unique_languages = {language for language, _ in hits}
    markers = tuple(marker for _, marker in hits)
    return LanguageDetection(
        language=first_language,
        markers=markers,
        ambiguous=len(unique_languages) > 1,
    )
