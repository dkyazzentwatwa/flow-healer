from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
