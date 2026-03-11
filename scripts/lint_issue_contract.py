#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flow_healer.healer_loop import AutonomousHealerLoop
from flow_healer.healer_task_spec import compile_task_spec, lint_issue_contract


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint a Flow Healer issue contract and emit remediation guidance.")
    parser.add_argument("--title", required=True, help="Issue title to lint.")
    parser.add_argument("--body-file", required=True, help="Path to a file containing the issue body.")
    parser.add_argument("--contract-mode", default="strict", choices=("strict", "lenient"))
    parser.add_argument("--parse-confidence-threshold", type=float, default=0.3)
    parser.add_argument("--json-output", default="", help="Optional path to write machine-readable lint output.")
    parser.add_argument("--comment-output", default="", help="Optional path to write remediation comment markdown.")
    args = parser.parse_args()

    issue_body = Path(args.body_file).read_text(encoding="utf-8")
    task_spec = compile_task_spec(issue_title=args.title, issue_body=issue_body)
    lint = lint_issue_contract(
        issue_title=args.title,
        issue_body=issue_body,
        task_spec=task_spec,
        contract_mode=args.contract_mode,
        parse_confidence_threshold=args.parse_confidence_threshold,
    )
    remediation_comment = ""
    if not lint.is_valid:
        remediation_comment = (
            "<!-- flow-healer-contract-lint -->\n\n"
            + AutonomousHealerLoop._build_needs_clarification_comment(
                list(lint.reason_codes),
                task_spec=task_spec,
            )
        )

    payload = {
        "is_valid": lint.is_valid,
        "reason_codes": list(lint.reason_codes),
        "suggested_execution_root": lint.suggested_execution_root,
        "task_spec": {
            "task_kind": task_spec.task_kind,
            "output_targets": list(task_spec.output_targets),
            "validation_commands": list(task_spec.validation_commands),
            "execution_root": task_spec.execution_root,
            "parse_confidence": task_spec.parse_confidence,
            "validation_profile": task_spec.validation_profile,
        },
        "remediation_comment": remediation_comment,
    }

    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.json_output:
        Path(args.json_output).write_text(rendered + "\n", encoding="utf-8")
    if args.comment_output:
        Path(args.comment_output).write_text(remediation_comment, encoding="utf-8")
    print(rendered)
    return 0 if lint.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
