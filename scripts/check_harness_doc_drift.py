#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROADMAP_PATH = REPO_ROOT / "docs" / "plans" / "2026-03-11-harness-roadmap-master-checklist.md"
PHASE_FIVE_HEADER = "## Phase 5: Reliability and Garbage Collection"
OPEN_DECISIONS_HEADER = "## Open Decisions"
_BACKTICK_PATH_RE = re.compile(r"`((?:docs|scripts|tests)/[^`]+)`")
_CHECKBOX_RE = re.compile(r"^- \[(?P<state>[ xX])\] (?P<label>.+)$", re.MULTILINE)
_ALWAYS_PUBLISH_RE = re.compile(
    r"^- \[x\] Console/network logs are always published(?: for app-backed runs)?$",
    re.IGNORECASE | re.MULTILINE,
)

_CHECKED_ITEM_REFS: dict[str, tuple[str, ...]] = {
    "Reliability runbook for harness failures": ("docs/harness-reliability-runbook.md",),
    "Periodic smoke checklist for artifact publishing": ("docs/harness-smoke-checklist.md",),
    "Canary dashboard surface for harness health": (
        "tests/test_service.py",
        "tests/test_web_dashboard.py",
    ),
    "Detect broken repro contracts in issue templates/examples": (
        "scripts/validate_repro_contract_examples.py",
        "docs/harness-repro-contract-examples.json",
        "tests/test_harness_validation_scripts.py",
    ),
    "Detect doc drift between roadmap, checklist, and actual behavior": (
        "scripts/check_harness_doc_drift.py",
        "tests/test_harness_validation_scripts.py",
    ),
}


def _extract_section(text: str, header: str) -> str:
    marker = text.find(header)
    if marker < 0:
        return ""
    remainder = text[marker:]
    next_header = remainder.find("\n## ", len(header))
    if next_header < 0:
        return remainder
    return remainder[:next_header]


def _extract_repo_paths(text: str) -> list[str]:
    return sorted(set(match.group(1) for match in _BACKTICK_PATH_RE.finditer(text)))


def _resolve_log_policy(open_decisions_text: str) -> str:
    if _ALWAYS_PUBLISH_RE.search(open_decisions_text):
        return "always_publish"
    return ""


def build_report(*, roadmap_path: Path = DEFAULT_ROADMAP_PATH) -> dict[str, Any]:
    roadmap_text = roadmap_path.read_text(encoding="utf-8")
    phase_five_text = _extract_section(roadmap_text, PHASE_FIVE_HEADER)
    open_decisions_text = _extract_section(roadmap_text, OPEN_DECISIONS_HEADER)
    referenced_paths = _extract_repo_paths(phase_five_text + "\n" + open_decisions_text)
    missing_paths = [path for path in referenced_paths if not (REPO_ROOT / path).exists()]
    issues: list[str] = []

    for match in _CHECKBOX_RE.finditer(phase_five_text):
        if match.group("state").lower() != "x":
            continue
        label = match.group("label").strip()
        required_refs = _CHECKED_ITEM_REFS.get(label)
        if not required_refs:
            continue
        missing_refs = [path for path in required_refs if path not in roadmap_text]
        if missing_refs:
            issues.append(f"Checked item '{label}' is missing roadmap refs: {', '.join(missing_refs)}")

    resolved_log_policy = _resolve_log_policy(open_decisions_text)
    if open_decisions_text and not resolved_log_policy:
        if "console/network logs" in open_decisions_text.lower():
            issues.append("Console/network log publication policy is still unresolved in the roadmap.")

    return {
        "roadmap_path": str(roadmap_path),
        "passed": not missing_paths and not issues,
        "missing_paths": missing_paths,
        "issues": issues,
        "paths_checked": referenced_paths,
        "resolved_log_policy": resolved_log_policy,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check narrow Phase 5 harness roadmap drift.")
    parser.add_argument(
        "--roadmap-path",
        default=str(DEFAULT_ROADMAP_PATH),
        help="Path to the roadmap/checklist markdown file.",
    )
    args = parser.parse_args()

    report = build_report(roadmap_path=Path(args.roadmap_path).resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
