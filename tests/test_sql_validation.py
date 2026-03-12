from __future__ import annotations

import subprocess
from pathlib import Path

from flow_healer.sql_validation import (
    SqlCheck,
    build_sql_check_script,
    database_is_ready,
    database_container_is_paused,
    database_container_for_project,
    ensure_local_supabase_stack,
    pause_local_database_container,
    resume_local_database_container,
    load_sql_checks,
    run_sql_checks,
    project_id_for_project_dir,
    reset_local_database,
    wait_for_database_ready,
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


def test_load_sql_checks_rejects_manifest_paths_outside_repo_root(tmp_path: Path) -> None:
    manifest = tmp_path / "supabase" / "assertions" / "manifest.json"
    outside_file = tmp_path / "outside.sql"
    manifest.parent.mkdir(parents=True)
    outside_file.write_text("select 1;\n", encoding="utf-8")
    manifest.write_text(
        '{"checks":[{"name":"escape","path":"../outside.sql"}]}',
        encoding="utf-8",
    )

    try:
        load_sql_checks(project_dir=tmp_path, manifest_path=manifest)
    except ValueError as exc:
        assert "outside the project directory" in str(exc)
    else:
        raise AssertionError("expected load_sql_checks to reject manifest paths outside the repo root")


def test_load_sql_checks_allows_ad_hoc_selected_paths_not_in_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "supabase" / "assertions" / "manifest.json"
    schema_file = tmp_path / "supabase" / "assertions" / "schema.sql"
    custom_file = tmp_path / "supabase" / "assertions" / "custom.sql"
    schema_file.parent.mkdir(parents=True)
    schema_file.write_text("select 1;\n", encoding="utf-8")
    custom_file.write_text("select 2;\n", encoding="utf-8")
    manifest.write_text(
        '{"checks":[{"name":"schema","path":"supabase/assertions/schema.sql"}]}',
        encoding="utf-8",
    )

    checks = load_sql_checks(
        project_dir=tmp_path,
        manifest_path=manifest,
        selected_paths=("supabase/assertions/custom.sql",),
    )

    assert checks == [SqlCheck(name="custom", path=custom_file.resolve())]


def test_load_sql_checks_allows_repo_relative_ad_hoc_selected_paths_not_in_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "supabase" / "assertions" / "manifest.json"
    schema_file = tmp_path / "supabase" / "assertions" / "schema.sql"
    custom_file = tmp_path / "supabase" / "assertions" / "bot_widget_integrity.sql"
    schema_file.parent.mkdir(parents=True)
    schema_file.write_text("select 1;\n", encoding="utf-8")
    custom_file.write_text("select 2;\n", encoding="utf-8")
    manifest.write_text(
        '{"checks":[{"name":"schema","path":"supabase/assertions/schema.sql"}]}',
        encoding="utf-8",
    )

    checks = load_sql_checks(
        project_dir=tmp_path,
        manifest_path=manifest,
        selected_paths=("e2e-apps/prosper-chat/supabase/assertions/bot_widget_integrity.sql",),
    )

    assert checks == [SqlCheck(name="bot_widget_integrity", path=custom_file.resolve())]


def test_load_sql_checks_rejects_missing_ad_hoc_selected_paths(tmp_path: Path) -> None:
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
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("expected load_sql_checks to reject unknown selected paths")


def test_load_sql_checks_rejects_ad_hoc_selected_paths_outside_repo_root(tmp_path: Path) -> None:
    manifest = tmp_path / "supabase" / "assertions" / "manifest.json"
    check_file = tmp_path / "supabase" / "assertions" / "schema.sql"
    outside_file = tmp_path / "outside.sql"
    check_file.parent.mkdir(parents=True)
    check_file.write_text("select 1;\n", encoding="utf-8")
    outside_file.write_text("select 2;\n", encoding="utf-8")
    manifest.write_text(
        '{"checks":[{"name":"schema","path":"supabase/assertions/schema.sql"}]}',
        encoding="utf-8",
    )

    try:
        load_sql_checks(
            project_dir=tmp_path,
            manifest_path=manifest,
            selected_paths=("../outside.sql",),
        )
    except ValueError as exc:
        assert "outside the project directory" in str(exc)
    else:
        raise AssertionError("expected load_sql_checks to reject ad hoc paths outside the repo root")


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


def test_database_container_is_paused_reads_docker_state(monkeypatch) -> None:
    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["docker", "ps", "--format"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="supabase_db_demo123\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="true\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert database_container_is_paused(project_id="demo123") is True


def test_resume_local_database_container_unpauses_and_waits(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "--format"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="supabase_db_demo123\n", stderr="")
        if cmd[:3] == ["docker", "inspect", "-f"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="true\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("flow_healer.sql_validation.wait_for_database_ready", lambda **kwargs: True)

    assert resume_local_database_container(project_id="demo123") is True
    assert ["docker", "unpause", "supabase_db_demo123"] in calls


def test_pause_local_database_container_pauses_when_enabled(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv("FLOW_HEALER_SQL_AUTO_PAUSE_SUPABASE", "1")
    monkeypatch.setattr("flow_healer.sql_validation.database_container_is_paused", lambda *, project_id: False)
    monkeypatch.setattr("flow_healer.sql_validation.database_container_for_project", lambda *, project_id: "supabase_db_demo123")

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert pause_local_database_container(project_id="demo123") is True
    assert ["docker", "pause", "supabase_db_demo123"] in calls


def test_run_sql_checks_auto_pauses_after_work(monkeypatch, tmp_path: Path) -> None:
    paused: list[str] = []
    resumed: list[str] = []
    monkeypatch.setenv("FLOW_HEALER_SQL_AUTO_PAUSE_SUPABASE", "1")
    check_file = tmp_path / "supabase" / "assertions" / "schema.sql"
    check_file.parent.mkdir(parents=True)
    check_file.write_text("select 1;\n", encoding="utf-8")

    monkeypatch.setattr("flow_healer.sql_validation.ensure_local_supabase_stack", lambda **kwargs: None)
    monkeypatch.setattr("flow_healer.sql_validation.project_id_for_project_dir", lambda _project_dir: "demo123")
    monkeypatch.setattr("flow_healer.sql_validation.resume_local_database_container", lambda *, project_id: resumed.append(project_id) or True)
    monkeypatch.setattr("flow_healer.sql_validation.pause_local_database_container", lambda *, project_id: paused.append(project_id) or True)
    monkeypatch.setattr("flow_healer.sql_validation.database_container_for_project", lambda *, project_id: "supabase_db_demo123")
    monkeypatch.setattr("flow_healer.sql_validation.record_docker_activity", lambda **kwargs: None)
    monkeypatch.setattr(
        "flow_healer.sql_validation.load_sql_checks",
        lambda **kwargs: [SqlCheck(name="schema", path=check_file.resolve())],
    )
    monkeypatch.setattr("flow_healer.sql_validation._run_sql_check", lambda **kwargs: None)

    run_sql_checks(
        project_dir=tmp_path,
        manifest_path=tmp_path / "supabase" / "assertions" / "manifest.json",
        reset=False,
    )

    assert resumed == ["demo123"]
    assert paused == ["demo123"]


def test_wait_for_database_ready_polls_until_success(monkeypatch) -> None:
    outcomes = iter([False, False, True])
    sleeps: list[float] = []

    monkeypatch.setattr("flow_healer.sql_validation.database_is_ready", lambda *, project_id: next(outcomes))
    monkeypatch.setattr("flow_healer.sql_validation.time.sleep", lambda seconds: sleeps.append(seconds))

    assert wait_for_database_ready(project_id="demo123", timeout_seconds=5.0, poll_interval_seconds=0.25) is True
    assert sleeps == [0.25, 0.25]


def test_reset_local_database_raises_when_reset_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(
            cmd,
            1,
            stdout="Restarting containers...\n",
            stderr="Error status 502: An invalid response was received from the upstream server",
        ),
    )
    try:
        reset_local_database(project_dir=tmp_path, project_id="demo123")
    except RuntimeError as exc:
        assert "supabase db reset failed" in str(exc)
        assert "Error status 502" in str(exc)
    else:
        raise AssertionError("expected reset_local_database to fail when supabase db reset exits non-zero")


def test_ensure_local_supabase_stack_skips_start_when_database_probe_is_ready(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["supabase", "status"]:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unhealthy")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr("flow_healer.sql_validation.ensure_docker_runtime_running", lambda **kwargs: None)
    monkeypatch.setattr("flow_healer.sql_validation.record_docker_activity", lambda **kwargs: None)
    monkeypatch.setattr("flow_healer.sql_validation._ensure_command_available", lambda command: None)
    monkeypatch.setattr("flow_healer.sql_validation.project_id_for_project_dir", lambda _project_dir: "demo123")
    monkeypatch.setattr("flow_healer.sql_validation.resume_local_database_container", lambda *, project_id: False)
    monkeypatch.setattr("flow_healer.sql_validation.wait_for_database_ready", lambda **kwargs: True)
    monkeypatch.setattr(subprocess, "run", fake_run)

    ensure_local_supabase_stack(project_dir=tmp_path)

    assert calls == [["supabase", "status"]]


def test_ensure_local_supabase_stack_starts_when_status_and_probe_fail(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    ready_checks = iter([False, True])

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["supabase", "status"]:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unhealthy")
        if cmd == ["supabase", "start"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="started", stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr("flow_healer.sql_validation.ensure_docker_runtime_running", lambda **kwargs: None)
    monkeypatch.setattr("flow_healer.sql_validation.record_docker_activity", lambda **kwargs: None)
    monkeypatch.setattr("flow_healer.sql_validation._ensure_command_available", lambda command: None)
    monkeypatch.setattr("flow_healer.sql_validation.project_id_for_project_dir", lambda _project_dir: "demo123")
    monkeypatch.setattr("flow_healer.sql_validation.resume_local_database_container", lambda *, project_id: False)
    monkeypatch.setattr(
        "flow_healer.sql_validation.wait_for_database_ready",
        lambda **kwargs: next(ready_checks),
    )
    monkeypatch.setattr(subprocess, "run", fake_run)

    ensure_local_supabase_stack(project_dir=tmp_path)

    assert calls == [["supabase", "status"], ["supabase", "start"]]


def test_ensure_local_supabase_stack_attempts_resume_before_status(monkeypatch, tmp_path: Path) -> None:
    resumed: list[str] = []
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["supabase", "status"]:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="paused")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr("flow_healer.sql_validation.ensure_docker_runtime_running", lambda **kwargs: None)
    monkeypatch.setattr("flow_healer.sql_validation.record_docker_activity", lambda **kwargs: None)
    monkeypatch.setattr("flow_healer.sql_validation._ensure_command_available", lambda command: None)
    monkeypatch.setattr("flow_healer.sql_validation.project_id_for_project_dir", lambda _project_dir: "demo123")
    monkeypatch.setattr(
        "flow_healer.sql_validation.resume_local_database_container",
        lambda *, project_id: resumed.append(project_id) or True,
    )
    monkeypatch.setattr("flow_healer.sql_validation.wait_for_database_ready", lambda **kwargs: True)
    monkeypatch.setattr(subprocess, "run", fake_run)

    ensure_local_supabase_stack(project_dir=tmp_path)

    assert resumed == ["demo123"]
    assert calls == [["supabase", "status"]]
