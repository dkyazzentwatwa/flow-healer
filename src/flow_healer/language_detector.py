from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class LanguageDetection:
    language: str
    markers: tuple[str, ...]
    ambiguous: bool = False


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
    scores: dict[str, int] = {}
    for markers, language in _LANGUAGE_MARKERS:
        for marker in markers:
            if (root / marker).exists():
                hits.append((language, marker))
                scores[language] = scores.get(language, 0) + 1

    if not hits:
        return LanguageDetection(language="unknown", markers=(), ambiguous=False)

    markers = tuple(marker for _, marker in hits)
    best_score = max(scores.values())
    top_languages = sorted(language for language, score in scores.items() if score == best_score)
    ambiguous = len(top_languages) > 1
    return LanguageDetection(
        language=top_languages[0] if not ambiguous else "unknown",
        markers=markers,
        ambiguous=ambiguous,
    )
