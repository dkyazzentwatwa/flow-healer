from __future__ import annotations

from pathlib import Path

# Ordered by specificity: more specific markers take priority.
# Each entry is (list_of_marker_files, language_string).
# The first match wins.
_LANGUAGE_MARKERS: list[tuple[list[str], str]] = [
    (["go.mod"],                                            "go"),
    (["Cargo.toml"],                                        "rust"),
    (["pom.xml"],                                           "java_maven"),
    (["build.gradle", "build.gradle.kts"],                  "java_gradle"),
    (["Gemfile"],                                           "ruby"),
    (["package.json"],                                      "node"),
    (["pyproject.toml", "setup.py", "setup.cfg"],           "python"),
    (["requirements.txt"],                                  "python"),
]


def detect_language(repo_path: Path) -> str:
    """Return the detected language/ecosystem for *repo_path*.

    Inspects well-known marker files in the repo root.  Returns one of:
    ``go``, ``rust``, ``java_maven``, ``java_gradle``, ``ruby``, ``node``,
    ``python``, or ``unknown``.
    """
    root = Path(repo_path)
    for markers, language in _LANGUAGE_MARKERS:
        if any((root / m).exists() for m in markers):
            return language
    return "unknown"
