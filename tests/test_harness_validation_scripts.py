from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_script_module(filename: str, module_name: str):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_validate_repro_contract_examples_passes_repo_manifest() -> None:
    module = _load_script_module("validate_repro_contract_examples.py", "validate_repro_contract_examples")

    report = module.build_report()

    assert report["failed_examples"] == 0
    assert report["total_examples"] >= 3
    assert any(example["source"].endswith("healer-js-framework.yml") for example in report["examples"])


def test_validate_repro_contract_examples_accepts_expected_invalid_examples(tmp_path) -> None:
    module = _load_script_module("validate_repro_contract_examples.py", "validate_repro_contract_examples")
    source = tmp_path / "example.md"
    source.write_text("placeholder\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "contract_mode": "strict",
                "parse_confidence_threshold": 0.3,
                "examples": [
                    {
                        "name": "missing-validation-example",
                        "source": str(source),
                        "source_kind": "inline_body",
                        "title": "Broken issue contract",
                        "body": "Required code outputs:\n- e2e-smoke/node/src/add.js\n",
                        "expected_valid": False,
                        "expected_reason_codes": ["missing_validation"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = module.build_report(manifest_path=manifest)

    assert report["failed_examples"] == 0
    assert report["examples"][0]["is_valid"] is False
    assert report["examples"][0]["reason_codes"] == ["missing_validation"]


def test_validate_repro_contract_examples_use_outcome_assertions_without_restart_dependency() -> None:
    module = _load_script_module("validate_repro_contract_examples.py", "validate_repro_contract_examples")

    report = module.build_report()
    example = next(
        item for item in report["examples"] if item["name"] == "browser-allow-success-outcome-assertions"
    )
    manifest = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "harness-repro-contract-examples.json"
        ).read_text(encoding="utf-8")
    )
    body = next(
        entry["body"]
        for entry in manifest["examples"]
        if entry["name"] == "browser-allow-success-outcome-assertions"
    )

    assert example["passed"] is True
    assert "click button.restart" not in body
    assert "expect_url /game" in body
    assert "expect_any_text Start game || Current turn: X" in body


def test_check_harness_doc_drift_reports_resolved_log_policy() -> None:
    module = _load_script_module("check_harness_doc_drift.py", "check_harness_doc_drift")

    report = module.build_report()

    assert report["passed"] is True
    assert report["missing_paths"] == []
    assert report["issues"] == []
    assert report["resolved_log_policy"] == "always_publish"


def test_check_harness_doc_drift_fails_when_referenced_doc_is_missing(tmp_path) -> None:
    module = _load_script_module("check_harness_doc_drift.py", "check_harness_doc_drift")
    roadmap = tmp_path / "roadmap.md"
    roadmap.write_text(
        (
            "## Phase 5: Reliability and Garbage Collection\n\n"
            "- Operator docs now live in `docs/harness-reliability-runbook.md` and `docs/missing-smoke-checklist.md`.\n"
            "- [x] Reliability runbook for harness failures\n"
            "- [x] Periodic smoke checklist for artifact publishing\n"
            "- [x] Canary dashboard surface for harness health\n"
        ),
        encoding="utf-8",
    )

    report = module.build_report(roadmap_path=roadmap)

    assert report["passed"] is False
    assert any(path.endswith("docs/missing-smoke-checklist.md") for path in report["missing_paths"])


def test_check_harness_doc_drift_requires_refs_for_checked_items(tmp_path) -> None:
    module = _load_script_module("check_harness_doc_drift.py", "check_harness_doc_drift")
    roadmap = tmp_path / "roadmap.md"
    roadmap.write_text(
        (
            "## Phase 5: Reliability and Garbage Collection\n\n"
            "- [x] Detect broken repro contracts in issue templates/examples\n"
            "- [x] Detect doc drift between roadmap, checklist, and actual behavior\n"
            "- [x] Canary dashboard surface for harness health\n"
        ),
        encoding="utf-8",
    )

    report = module.build_report(roadmap_path=roadmap)

    assert report["passed"] is False
    assert any("Detect broken repro contracts" in issue for issue in report["issues"])
