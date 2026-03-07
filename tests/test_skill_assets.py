from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from flow_healer.store import SQLiteStore


ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        check=False,
        capture_output=True,
        text=True,
    )


def test_preflight_script_help_runs():
    proc = _run([sys.executable, "skills/flow-healer-preflight/scripts/preflight_check.py", "--help"])
    assert proc.returncode == 0
    assert "Flow Healer guarded preflight" in proc.stdout


def test_make_live_smoke_bundle_creates_files(tmp_path):
    out_dir = tmp_path / "bundle"
    proc = _run(
        [
            sys.executable,
            "skills/flow-healer-live-smoke/scripts/make_live_smoke_bundle.py",
            "--repo-path",
            str(ROOT),
            "--repo-slug",
            "owner/repo",
            "--repo-name",
            "live",
            "--output-dir",
            str(out_dir),
            "--template",
            "docs_scaffold",
        ]
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert Path(payload["connector_path"]).exists()
    assert Path(payload["config_path"]).exists()
    assert Path(payload["connector_path"]).stat().st_mode & 0o111


def test_triage_script_classifies_connector_failure(tmp_path):
    db_path = tmp_path / "state.db"
    store = SQLiteStore(db_path)
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="1",
        repo="owner/repo",
        title="Issue 1",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="1",
        state="failed",
        last_failure_class="patch_apply_failed",
        last_failure_reason="error: corrupt patch at line 14",
    )
    store.create_healer_attempt(
        attempt_id="hat_1",
        issue_id="1",
        attempt_no=1,
        state="running",
        prediction_source="coarse_repo_lock",
        predicted_lock_set=["repo:*"],
    )
    store.finish_healer_attempt(
        attempt_id="hat_1",
        state="failed",
        actual_diff_set=[],
        test_summary={},
        verifier_summary={},
        failure_class="patch_apply_failed",
        failure_reason="error: corrupt patch at line 14",
    )
    store.close()

    proc = _run(
        [
            sys.executable,
            "skills/flow-healer-triage/scripts/triage_issue.py",
            "--db-path",
            str(db_path),
            "--issue-id",
            "1",
        ]
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["diagnosis"] == "connector_or_patch_generation"
    assert payload["recommended_skill"] == "flow-healer-connector-debug"
    assert "connector-debug" in payload["default_action"]
    assert payload["graph_position"] == 6
    assert payload["skill_relative_path"].endswith("skills/flow-healer-connector-debug/SKILL.md")
    assert payload["connector_debug_focus"] == "patch_apply"
    assert payload["connector_debug_checks"][0] == "Reproduce patch application with the raw patch output"


def test_followup_inspector_reads_issue_state(tmp_path):
    db_path = tmp_path / "state.db"
    store = SQLiteStore(db_path)
    store.bootstrap()
    store.upsert_healer_issue(
        issue_id="3",
        repo="owner/repo",
        title="Issue 3",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=5,
    )
    store.set_healer_issue_state(
        issue_id="3",
        state="pr_open",
        pr_number=4,
        last_issue_comment_id=123,
        feedback_context="PR comment from @bob: please add a note.",
    )
    store.close()

    proc = _run(
        [
            sys.executable,
            "skills/flow-healer-pr-followup/scripts/inspect_issue_state.py",
            "--db-path",
            str(db_path),
            "--issue-id",
            "3",
        ]
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["issue"]["pr_number"] == 4
    assert payload["issue"]["last_issue_comment_id"] == 123


@pytest.mark.parametrize(
    ("relative_path", "required_snippets"),
    [
        (
            "skills/flow-healer-local-validation/SKILL.md",
            [
                "## Inputs",
                "## Outputs",
                "## Key Output Fields",
                "## Success Criteria",
                "## Failure Handling",
                "## Next Step",
                "`repo_root`",
                "`checks[*].exit_code`",
                "`checks[*].output_tail`",
                "`name`, `category`, or `duration_seconds`",
            ],
        ),
        (
            "skills/flow-healer-preflight/SKILL.md",
            [
                "## Inputs",
                "## Outputs",
                "## Key Output Fields",
                "## Success Criteria",
                "## Failure Handling",
                "## Next Step",
                "`required_checks.gh_auth_ok`",
                "`required_checks.repo_exists`",
                "`required_checks.git_repo`",
                "`required_checks.repo_clean_git`",
                "`required_checks.venv_ok`",
                "`required_checks.docker_ok`",
                "Treat `docker_ok` as required",
            ],
        ),
        (
            "skills/flow-healer-live-smoke/SKILL.md",
            [
                "## Inputs",
                "## Outputs",
                "## Key Output Fields",
                "## Success Criteria",
                "## Failure Handling",
                "## Next Step",
                "`docs_scaffold`",
                "`docs_followup_note`",
                "`issue_id`",
                "`pr_id`",
                "`branch_name`",
                "`attempt_state`",
                "`verifier_summary`",
                "`test_summary`",
                "It does not run `flow-healer start --once` by itself.",
            ],
        ),
        (
            "skills/flow-healer-triage/SKILL.md",
            [
                "## Inputs",
                "## Outputs",
                "## Key Output Fields",
                "## Success Criteria",
                "## Failure Handling",
                "## Next Step",
                "`operator_or_environment`",
                "`repo_fixture_or_setup`",
                "`connector_or_patch_generation`",
                "`product_bug`",
                "`external_service_or_github`",
                "`flow-healer-connector-debug`",
            ],
        ),
        (
            "skills/flow-healer-pr-followup/SKILL.md",
            [
                "## Inputs",
                "## Outputs",
                "## Key Output Fields",
                "## Success Criteria",
                "## Failure Handling",
                "## Next Step",
                "`issue.pr_number`",
                "`issue.last_issue_comment_id`",
                "`issue.feedback_context`",
                "`issue.state`",
                "`attempts[*].state`",
                "## Safe Resume Checklist",
                "The issue is still active.",
                "The PR is still relevant.",
                "New external feedback exists.",
                "No active running attempt exists.",
                "Stored branch or worktree metadata still matches reality.",
            ],
        ),
        (
            "skills/flow-healer-connector-debug/SKILL.md",
            [
                "# Flow Healer Connector Debug",
                "Use this skill when `flow-healer-triage` reports `connector_or_patch_generation`.",
                "Connector command resolution",
                "Diff fence validity",
                "Empty diff detection",
                "Verifier JSON validity",
                "Patch-apply outcome",
                "Validate connector command resolution",
                "Rerun the connector against a fixed prompt fixture",
                "Detect empty diff output and malformed diff fences",
                "Validate any verifier payload as JSON",
                "Compare proposer and verifier contracts",
            ],
        ),
    ],
)
def test_skill_docs_encode_the_skills_upgrade_contract(relative_path: str, required_snippets: list[str]) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    for snippet in required_snippets:
        assert snippet in text
