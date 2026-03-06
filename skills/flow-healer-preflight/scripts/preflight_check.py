#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        check=False,
        capture_output=True,
        text=True,
    )


def _gh_auth_ok() -> tuple[bool, str]:
    proc = _run(["gh", "auth", "status"])
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return proc.returncode == 0, output


def _git_default_branch(repo_path: Path) -> str:
    proc = _run(["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "origin/HEAD"])
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip().replace("origin/", "", 1)


def _gh_json(cmd: list[str]) -> Any:
    proc = _run(cmd)
    if proc.returncode != 0:
        return []
    try:
        return json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []


def _state_counts(db_path: Path) -> dict[str, int]:
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "select state, count(*) from healer_issues group by state order by state"
        ).fetchall()
        return {str(state): int(count) for state, count in rows}
    finally:
        conn.close()


def build_report(*, repo_path: Path, repo_slug: str, db_path: Path | None) -> dict[str, Any]:
    gh_ok, gh_output = _gh_auth_ok()
    repo_path = repo_path.expanduser().resolve()
    git_proc = _run(["git", "-C", str(repo_path), "rev-parse", "--is-inside-work-tree"])
    dirty_proc = _run(["git", "-C", str(repo_path), "status", "--porcelain"])
    current_branch = _run(["git", "-C", str(repo_path), "branch", "--show-current"]).stdout.strip()
    remote_url = _run(["git", "-C", str(repo_path), "remote", "get-url", "origin"]).stdout.strip()
    open_issues = _gh_json(
        ["gh", "issue", "list", "--repo", repo_slug, "--limit", "20", "--json", "number,title,state"]
    ) if repo_slug else []
    open_prs = _gh_json(
        ["gh", "pr", "list", "--repo", repo_slug, "--limit", "20", "--json", "number,title,state,headRefName"]
    ) if repo_slug else []

    report = {
        "repo_path": str(repo_path),
        "repo_slug": repo_slug,
        "required_checks": {
            "gh_auth_ok": gh_ok,
            "repo_exists": repo_path.exists(),
            "git_repo": git_proc.returncode == 0,
            "repo_clean_git": dirty_proc.returncode == 0 and not (dirty_proc.stdout or "").strip(),
            "venv_ok": (repo_path / ".venv" / "bin" / "python").exists(),
            "docker_ok": shutil.which("docker") is not None,
        },
        "context": {
            "current_branch": current_branch,
            "default_branch": _git_default_branch(repo_path),
            "origin_url": remote_url,
            "open_issue_count": len(open_issues) if isinstance(open_issues, list) else 0,
            "open_pr_count": len(open_prs) if isinstance(open_prs, list) else 0,
            "state_db_path": str(db_path) if db_path is not None else "",
            "state_counts": _state_counts(db_path) if db_path is not None else {},
        },
        "samples": {
            "issues": open_issues[:5] if isinstance(open_issues, list) else [],
            "prs": open_prs[:5] if isinstance(open_prs, list) else [],
        },
        "notes": {
            "gh_auth_output_tail": gh_output[-1200:],
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Flow Healer guarded preflight check")
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--repo-slug", default="")
    parser.add_argument("--db-path")
    args = parser.parse_args()

    db_path = Path(args.db_path).expanduser().resolve() if args.db_path else None
    report = build_report(
        repo_path=Path(args.repo_path),
        repo_slug=str(args.repo_slug or "").strip(),
        db_path=db_path,
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if all(report["required_checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
