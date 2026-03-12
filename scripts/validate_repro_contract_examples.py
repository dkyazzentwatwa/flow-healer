#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from flow_healer.healer_task_spec import compile_task_spec, lint_issue_contract

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = REPO_ROOT / "docs" / "harness-repro-contract-examples.json"


def _load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _issue_form_value(field: dict[str, Any], field_values: dict[str, str]) -> str:
    attributes = field.get("attributes", {}) or {}
    label = str(attributes.get("label", "")).strip()
    field_id = str(field.get("id", "")).strip()
    for key in (field_id, label):
        if key and key in field_values:
            return str(field_values[key]).rstrip()
    options = attributes.get("options") or ()
    if options:
        return str(options[0]).rstrip()
    placeholder = attributes.get("placeholder")
    if placeholder:
        return str(placeholder).strip("\n")
    value = attributes.get("value")
    if value:
        return str(value).rstrip()
    return ""


def _render_issue_form_body(source_path: Path, field_values: dict[str, str]) -> str:
    raw = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    lines: list[str] = []
    for field in raw.get("body", []) or ():
        if not isinstance(field, dict):
            continue
        attributes = field.get("attributes", {}) or {}
        label = str(attributes.get("label", field.get("id", ""))).strip()
        if not label:
            continue
        value = _issue_form_value(field, field_values)
        if not value:
            continue
        if "\n" in value or value.lstrip().startswith(("-", "*")):
            lines.append(f"{label}:")
            lines.extend(value.splitlines())
        else:
            lines.append(f"{label}: {value}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_body(entry: dict[str, Any], source_path: Path) -> str:
    source_kind = str(entry.get("source_kind", "inline_body")).strip()
    if source_kind == "github_issue_form":
        return _render_issue_form_body(source_path, dict(entry.get("field_values", {}) or {}))
    body = entry.get("body")
    if body is None:
        raise ValueError(f"Example {entry.get('name', '<unnamed>')} is missing a body.")
    return str(body).rstrip() + "\n"


def build_report(*, manifest_path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    contract_mode = str(manifest.get("contract_mode", "strict")).strip() or "strict"
    parse_confidence_threshold = float(manifest.get("parse_confidence_threshold", 0.3))
    missing_sources: list[str] = []
    examples_report: list[dict[str, Any]] = []
    failed_examples = 0

    for entry in manifest.get("examples", []) or ():
        source = str(entry.get("source", "")).strip()
        source_path = REPO_ROOT / source
        if not source or not source_path.exists():
            if source:
                missing_sources.append(source)
            failed_examples += 1
            examples_report.append(
                {
                    "name": entry.get("name", ""),
                    "source": source,
                    "passed": False,
                    "error": "missing_source",
                }
            )
            continue

        issue_title = str(entry.get("title", "")).strip()
        issue_body = _render_body(entry, source_path)
        task_spec = compile_task_spec(issue_title=issue_title, issue_body=issue_body)
        lint = lint_issue_contract(
            issue_title=issue_title,
            issue_body=issue_body,
            task_spec=task_spec,
            contract_mode=contract_mode,
            parse_confidence_threshold=parse_confidence_threshold,
        )

        expected_valid = bool(entry.get("expected_valid", True))
        expected_reason_codes = tuple(str(code) for code in entry.get("expected_reason_codes", []) or ())
        matches_validity = lint.is_valid is expected_valid
        matches_reason_codes = True
        if not expected_valid and expected_reason_codes:
            matches_reason_codes = tuple(lint.reason_codes) == expected_reason_codes
        passed = matches_validity and matches_reason_codes
        if not passed:
            failed_examples += 1

        examples_report.append(
            {
                "name": str(entry.get("name", "")).strip(),
                "source": source,
                "source_kind": str(entry.get("source_kind", "inline_body")).strip(),
                "title": issue_title,
                "passed": passed,
                "expected_valid": expected_valid,
                "is_valid": lint.is_valid,
                "reason_codes": list(lint.reason_codes),
                "execution_root": task_spec.execution_root,
                "validation_commands": list(task_spec.validation_commands),
                "output_targets": list(task_spec.output_targets),
                "parse_confidence": task_spec.parse_confidence,
            }
        )

    try:
        manifest_label = str(manifest_path.relative_to(REPO_ROOT))
    except ValueError:
        manifest_label = str(manifest_path)

    return {
        "manifest_path": manifest_label,
        "contract_mode": contract_mode,
        "parse_confidence_threshold": parse_confidence_threshold,
        "total_examples": len(examples_report),
        "failed_examples": failed_examples,
        "missing_sources": sorted(set(missing_sources)),
        "examples": examples_report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate repo-tracked issue-contract examples.")
    parser.add_argument(
        "--manifest-path",
        default=str(DEFAULT_MANIFEST_PATH),
        help="Path to the repo-tracked example manifest.",
    )
    args = parser.parse_args()

    report = build_report(manifest_path=Path(args.manifest_path).resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["failed_examples"] == 0 and not report["missing_sources"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
