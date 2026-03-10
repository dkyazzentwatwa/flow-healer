#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from flow_healer.issue_generation import (  # noqa: E402
    DEFAULT_FAMILY,
    available_issue_families,
    build_issue_drafts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create sandbox-scoped healer-ready GitHub issues.")
    parser.add_argument("count", nargs="?", type=int, default=20)
    parser.add_argument("prefix", nargs="?", default="Sandbox stress task")
    parser.add_argument(
        "--family",
        default=os.getenv("ISSUE_FAMILY", DEFAULT_FAMILY),
        choices=available_issue_families(),
        help="Issue template family to use.",
    )
    parser.add_argument(
        "--ready-label",
        default=os.getenv("READY_LABEL", "healer:ready"),
        help="Primary ready label to attach to created issues.",
    )
    parser.add_argument(
        "--extra-label",
        action="append",
        dest="extra_labels",
        default=[],
        help="Additional label to apply. Can be passed multiple times.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the issue payloads as JSON instead of creating them on GitHub.",
    )
    parser.add_argument(
        "--allow-non-python-js",
        action="store_true",
        help="Allow drafts that target non-Python/JS validation stacks.",
    )
    return parser.parse_args()


def parse_env_extra_labels(cli_labels: list[str]) -> list[str]:
    env_raw = os.getenv("EXTRA_LABELS", "")
    env_labels = [item.strip() for item in env_raw.split(",") if item.strip()]
    return [*env_labels, *cli_labels]


def ensure_gh_available(*, dry_run: bool) -> None:
    if dry_run:
        return
    if shutil.which("gh") is None:
        raise SystemExit("gh CLI is required")


def create_issue(*, title: str, body: str, labels: tuple[str, ...]) -> None:
    cmd = ["gh", "issue", "create", "--title", title, "--body", body]
    for label in labels:
        cmd.extend(["--label", label])
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)


def list_existing_labels() -> set[str]:
    proc = subprocess.run(
        ["gh", "label", "list", "--limit", "500", "--json", "name"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout or "[]")
    return {
        str(item.get("name") or "").strip().lower()
        for item in payload
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }


def ensure_labels_exist(labels: list[str]) -> None:
    existing = list_existing_labels()
    for label in labels:
        normalized = str(label or "").strip()
        if not normalized or normalized.lower() in existing:
            continue
        color, description = label_metadata(normalized)
        subprocess.run(
            [
                "gh",
                "label",
                "create",
                normalized,
                "--color",
                color,
                "--description",
                description,
            ],
            cwd=str(REPO_ROOT),
            check=True,
        )
        existing.add(normalized.lower())


def label_metadata(label: str) -> tuple[str, str]:
    normalized = str(label or "").strip().lower()
    if normalized.startswith("area:db"):
        return ("1d76db", "Database-focused sandbox issue")
    if normalized.startswith("kind:migration"):
        return ("5319e7", "Schema or migration issue")
    if normalized.startswith("kind:rls"):
        return ("0e8a16", "RLS or policy issue")
    if normalized.startswith("difficulty:easy"):
        return ("bfd4f2", "Low-complexity task")
    if normalized.startswith("difficulty:medium"):
        return ("fbca04", "Medium-complexity task")
    if normalized.startswith("difficulty:hard"):
        return ("d93f0b", "High-complexity task")
    return ("ededed", "Flow Healer issue label")


_DISALLOWED_VALIDATION_RE = re.compile(
    r"\b(?:\./gradlew\s+test|mvn\s+test|go\s+test|cargo\s+test|bundle\s+exec\s+rspec|swift\s+test)\b",
    re.IGNORECASE,
)
_ALLOWED_ROOT_RE = re.compile(
    r"(?:e2e-smoke/(?:js|node|py|python)-|e2e-apps/(?:node|python)-|e2e-apps/prosper-chat|e2e-apps/nobi-owl-trader)",
    re.IGNORECASE,
)


def _is_python_js_only_draft(body: str) -> bool:
    text = str(body or "")
    if _DISALLOWED_VALIDATION_RE.search(text):
        return False
    paths = [line.strip()[2:].strip() for line in text.splitlines() if line.strip().startswith("- ")]
    for path in paths:
        if "/" in path and not _ALLOWED_ROOT_RE.search(path):
            return False
    return True


def main() -> int:
    args = parse_args()
    if args.count < 1:
        raise SystemExit(f"count must be a positive integer (got: {args.count})")

    extra_labels = parse_env_extra_labels(args.extra_labels)
    ensure_gh_available(dry_run=args.dry_run)
    drafts = build_issue_drafts(
        count=args.count,
        prefix=args.prefix,
        ready_label=args.ready_label,
        extra_labels=extra_labels,
        family=args.family,
    )
    if not args.allow_non_python_js:
        invalid = [draft.title for draft in drafts if not _is_python_js_only_draft(draft.body)]
        if invalid:
            raise SystemExit(
                "Refusing to create mixed-language drafts without --allow-non-python-js. "
                f"Invalid drafts: {', '.join(invalid)}"
            )

    if args.dry_run:
        payload = [
            {
                "title": draft.title,
                "body": draft.body,
                "labels": list(draft.labels),
            }
            for draft in drafts
        ]
        print(json.dumps(payload, indent=2))
        return 0

    ensure_labels_exist(sorted({label for draft in drafts for label in draft.labels}))
    for index, draft in enumerate(drafts, start=1):
        create_issue(title=draft.title, body=draft.body, labels=draft.labels)
        print(f"created issue {index}/{len(drafts)}: {draft.title}")
    print(f"done: created {len(drafts)} sandbox-scoped issues")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
