from __future__ import annotations

import subprocess
from pathlib import Path

from flow_healer.sql_validation import (
    SqlCheck,
    build_sql_check_script,
    database_is_ready,
    database_container_for_project,
    load_sql_checks,
    project_id_for_project_dir,
)


def test_project_id_for_project_dir_reads_supabase_config(tmp_path: Path) -> None:
    config = tmp_path / "supabase" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('project_id = "demo123"\n', encoding="utf-8")

    assert project_id_for_project_dir(tmp_path) == "demo123"


def test_load_sql_checks_resolves_paths(tmp_path: Path) -> None:
    manifest = tmp_path / "supabase" / "assertions" / "manifest.json"
    check_file = tmp_path / "supabase" / "assertions" / "schema.sql"
    check_file.parent.mkdir(parents=True)
    check_file.write_text("select 1;\n", encoding="utf-8")
    manifest.write_text(
        '{"checks":[{"name":"schema","path":"supabase/assertions/schema.sql","role":"anon","jwt_role":"anon"}]}',
        encoding="utf-8",
    )

    checks = load_sql_checks(project_dir=tmp_path, manifest_path=manifest)

    assert checks == [
        SqlCheck(
            name="schema",
            path=check_file.resolve(),
            role="anon",
            jwt_sub="",
            jwt_role="anon",
        )
    ]


def test_load_sql_checks_filters_to_selected_paths(tmp_path: Path) -> None:
    manifest = tmp_path / "supabase" / "assertions" / "manifest.json"
    schema_file = tmp_path / "supabase" / "assertions" / "schema.sql"
    policy_file = tmp_path / "supabase" / "assertions" / "policy.sql"
    schema_file.parent.mkdir(parents=True)
    schema_file.write_text("select 1;\n", encoding="utf-8")
    policy_file.write_text("select 2;\n", encoding="utf-8")
    manifest.write_text(
        (
            '{"checks":['
            '{"name":"schema","path":"supabase/assertions/schema.sql"},'
            '{"name":"policy","path":"supabase/assertions/policy.sql"}'
            "]}"
        ),
        encoding="utf-8",
    )

    checks = load_sql_checks(
        project_dir=tmp_path,
        manifest_path=manifest,
        selected_paths=("supabase/assertions/policy.sql",),
    )

    assert checks == [SqlCheck(name="policy", path=policy_file.resolve())]


def test_load_sql_checks_accepts_repo_relative_selected_paths(tmp_path: Path) -> None:
    manifest = tmp_path / "supabase" / "assertions" / "manifest.json"
    policy_file = tmp_path / "supabase" / "assertions" / "policy.sql"
    policy_file.parent.mkdir(parents=True)
    policy_file.write_text("select 2;\n", encoding="utf-8")
    manifest.write_text(
        '{"checks":[{"name":"policy","path":"supabase/assertions/policy.sql"}]}',
        encoding="utf-8",
    )

    checks = load_sql_checks(
        project_dir=tmp_path,
        manifest_path=manifest,
        selected_paths=("e2e-apps/prosper-chat/supabase/assertions/policy.sql",),
    )

    assert checks == [SqlCheck(name="policy", path=policy_file.resolve())]


def test_load_sql_checks_rejects_unknown_selected_paths(tmp_path: Path) -> None:
    manifest = tmp_path / "supabase" / "assertions" / "manifest.json"
    check_file = tmp_path / "supabase" / "assertions" / "schema.sql"
    check_file.parent.mkdir(parents=True)
    check_file.write_text("select 1;\n", encoding="utf-8")
    manifest.write_text(
        '{"checks":[{"name":"schema","path":"supabase/assertions/schema.sql"}]}',
        encoding="utf-8",
    )

    try:
        load_sql_checks(
            project_dir=tmp_path,
            manifest_path=manifest,
            selected_paths=("supabase/assertions/missing.sql",),
        )
    except ValueError as exc:
        assert "requested check path" in str(exc)
    else:
        raise AssertionError("expected load_sql_checks to reject unknown selected paths")


def test_build_sql_check_script_includes_context_and_rollback(tmp_path: Path) -> None:
    check_file = tmp_path / "check.sql"
    check_file.write_text("SELECT 1;\n", encoding="utf-8")

    script = build_sql_check_script(
        check=SqlCheck(
            name="demo",
            path=check_file,
            role="authenticated",
            jwt_sub="user-123",
            jwt_role="authenticated",
        )
    )

    assert 'SET LOCAL ROLE "authenticated";' in script
    assert "request.jwt.claim.sub" in script
    assert "request.jwt.claim.role" in script
    assert script.strip().endswith("ROLLBACK;")


def test_database_container_for_project_matches_running_name(monkeypatch) -> None:
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="supabase_db_demo123\nother\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert database_container_for_project(project_id="demo123") == "supabase_db_demo123"


def test_database_is_ready_checks_psql_probe(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "--format"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="supabase_db_demo123\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="1\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert database_is_ready(project_id="demo123") is True
    assert any(cmd[:3] == ["docker", "exec", "-i"] for cmd in calls)
