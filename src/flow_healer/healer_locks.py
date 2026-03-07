from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class LockPrediction:
    keys: list[str]
    source: str


_PATH_TOKEN_PATTERN = re.compile(r"\S+")
_ROOT_FILE_SUFFIXES = {
    "cfg",
    "conf",
    "css",
    "env",
    "html",
    "ini",
    "js",
    "json",
    "jsx",
    "lock",
    "md",
    "py",
    "rst",
    "sh",
    "toml",
    "ts",
    "tsx",
    "txt",
    "yaml",
    "yml",
}


def predict_lock_set(*, issue_text: str, max_paths: int = 24) -> LockPrediction:
    """Deterministic lock prediction from issue text and error snippets."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in _extract_path_candidates(issue_text):
        candidate = _normalize_path(raw)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
        if len(normalized) >= max_paths:
            break

    if not normalized:
        return LockPrediction(keys=["repo:*"], source="coarse_repo_lock")

    if len(normalized) > 10:
        coarse = sorted({_to_directory_lock(p) for p in normalized})
        return LockPrediction(keys=coarse, source="directory_escalation")

    return LockPrediction(keys=[f"path:{p}" for p in sorted(normalized)], source="path_level")


def canonicalize_lock_keys(keys: list[str]) -> list[str]:
    return sorted({(key or "").strip().lower() for key in keys if (key or "").strip()})


def lock_granularity(lock_key: str) -> str:
    if lock_key.startswith("path:"):
        return "path"
    if lock_key.startswith("dir:"):
        return "dir"
    if lock_key.startswith("module:"):
        return "module"
    return "repo"


def diff_paths_to_lock_keys(paths: list[str], *, coarse_threshold: int = 12) -> list[str]:
    normalized = sorted({_normalize_path(path) for path in paths if _normalize_path(path)})
    if not normalized:
        return ["repo:*"]
    if len(normalized) > coarse_threshold:
        return sorted({_to_directory_lock(path) for path in normalized})
    return [f"path:{path}" for path in normalized]


def lock_keys_conflict(left: str, right: str) -> bool:
    left_scope = _parse_lock_scope(left)
    right_scope = _parse_lock_scope(right)
    if left_scope is None or right_scope is None:
        return False
    if left_scope.kind == "repo" or right_scope.kind == "repo":
        return True
    if left_scope.kind == "path":
        return _scope_contains_path(right_scope, left_scope.target)
    if right_scope.kind == "path":
        return _scope_contains_path(left_scope, right_scope.target)
    return _paths_overlap(left_scope.target, right_scope.target)


def _extract_path_candidates(issue_text: str) -> list[str]:
    candidates: list[str] = []
    for match in _PATH_TOKEN_PATTERN.finditer(issue_text or ""):
        raw = match.group(0).strip()
        if not raw or "://" in raw or "@" in raw:
            continue
        candidate = raw[5:] if raw.lower().startswith("path:") else raw
        candidate = candidate.strip("`'\"()[]{}<>,:;")
        if _looks_like_repo_path(candidate):
            candidates.append(candidate)
    return candidates


def _normalize_path(path: str) -> str:
    cleaned = (path or "").strip().replace("\\", "/")
    cleaned = cleaned.lstrip("./")
    cleaned = os.path.normpath(cleaned).replace("\\", "/")
    if cleaned.startswith("../"):
        return ""
    if cleaned in {".", ""}:
        return ""
    return cleaned


def _to_directory_lock(path: str) -> str:
    parts = path.split("/")
    if len(parts) <= 1:
        return f"module:{parts[0]}"
    if len(parts) == 2:
        return f"dir:{parts[0]}"
    return f"dir:{'/'.join(parts[:2])}"


def _looks_like_repo_path(path: str) -> bool:
    normalized = _normalize_path(path)
    if not normalized:
        return False
    name = normalized.rsplit("/", 1)[-1]
    if "/" in normalized:
        return any(char.isalpha() for char in normalized)
    if name.startswith("."):
        return len(name) > 1 and any(char.isalpha() for char in name)
    stem, dot, suffix = name.rpartition(".")
    if not dot or not stem or suffix.lower() not in _ROOT_FILE_SUFFIXES:
        return False
    return any(char.isalpha() for char in stem)


@dataclass(slots=True, frozen=True)
class _LockScope:
    kind: str
    target: str


def _parse_lock_scope(lock_key: str) -> _LockScope | None:
    canonical = canonicalize_lock_keys([lock_key])
    if not canonical:
        return None
    key = canonical[0]
    if key == "repo:*":
        return _LockScope(kind="repo", target="*")
    if ":" not in key:
        return None
    kind, raw_target = key.split(":", 1)
    target = _normalize_path(raw_target)
    if kind not in {"path", "dir", "module"} or not target:
        return None
    return _LockScope(kind=kind, target=target)


def _scope_contains_path(scope: _LockScope, path: str) -> bool:
    if scope.kind == "repo":
        return True
    if scope.kind == "path":
        return scope.target == path
    return _is_same_or_parent(scope.target, path)


def _paths_overlap(left: str, right: str) -> bool:
    return _is_same_or_parent(left, right) or _is_same_or_parent(right, left)


def _is_same_or_parent(parent: str, child: str) -> bool:
    return child == parent or child.startswith(f"{parent}/")
