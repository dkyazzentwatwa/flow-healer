from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .docker_runtime import ensure_docker_runtime_running, record_docker_activity


@dataclass(slots=True, frozen=True)
class SqlCheck:
    name: str
    path: Path
    role: str = "postgres"
    jwt_sub: str = ""
    jwt_role: str = ""


def load_sql_checks(
    *,
    project_dir: Path,
    manifest_path: Path,
    selected_paths: tuple[str, ...] = (),
) -> list[SqlCheck]:
    project_root = project_dir.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("SQL assertion manifest must be a JSON object.")
    raw_checks = manifest.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        raise ValueError("SQL assertion manifest must define a non-empty checks list.")
    normalized_selected_paths = {
        normalized
        for path in selected_paths
        if (normalized := _normalize_manifest_relative_path(path))
    }
    checks: list[SqlCheck] = []
    matched_selected_paths: set[str] = set()
    for index, raw in enumerate(raw_checks, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"SQL assertion check #{index} must be an object.")
        name = str(raw.get("name") or "").strip()
        relative_path = str(raw.get("path") or "").strip()
        if not name or not relative_path:
            raise ValueError(f"SQL assertion check #{index} is missing name or path.")
        normalized_relative_path = _normalize_manifest_relative_path(relative_path)
        matched_for_check = {
            selected_path
            for selected_path in normalized_selected_paths
            if _selected_path_matches_manifest_path(
                selected_path=selected_path,
                manifest_path=normalized_relative_path,
            )
        }
        if normalized_selected_paths and not matched_for_check:
            continue
        check_path = _resolve_project_relative_path(project_root=project_root, relative_path=relative_path)
        checks.append(
            SqlCheck(
                name=name,
                path=check_path,
                role=str(raw.get("role") or "postgres").strip() or "postgres",
                jwt_sub=str(raw.get("jwt_sub") or "").strip(),
                jwt_role=str(raw.get("jwt_role") or "").strip(),
            )
        )
        matched_selected_paths.update(matched_for_check or {normalized_relative_path})
    if normalized_selected_paths:
        missing = sorted(normalized_selected_paths - matched_selected_paths)
        if missing:
            checks.extend(_ad_hoc_sql_checks(project_dir=project_root, selected_paths=tuple(missing)))
        if not checks:
            raise ValueError("SQL assertion manifest did not match any requested check paths.")
    return checks


def project_id_for_project_dir(project_dir: Path) -> str:
    config_path = project_dir / "supabase" / "config.toml"
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    project_id = str(data.get("project_id") or "").strip()
    if not project_id:
        raise ValueError(f"Missing project_id in {config_path}")
    return project_id


def ensure_local_supabase_stack(*, project_dir: Path) -> None:
    ensure_docker_runtime_running(reason="sql_validation")
    record_docker_activity(reason="sql_validation")
    _ensure_command_available("docker")
    _ensure_command_available("supabase")
    project_id = project_id_for_project_dir(project_dir)
    resume_local_database_container(project_id=project_id)
    status = subprocess.run(
        ["supabase", "status"],
        cwd=str(project_dir),
        check=False,
        capture_output=True,
        text=True,
    )
    if status.returncode == 0:
        wait_for_database_ready(project_id=project_id)
        return
    # `supabase status` can report an unhealthy stack even when the local Postgres
    # container is already accepting connections. For DB-only validation we can
    # proceed as soon as the database probe succeeds.
    if wait_for_database_ready(project_id=project_id, timeout_seconds=5.0, poll_interval_seconds=1.0):
        return
    subprocess.run(
        ["supabase", "start"],
        cwd=str(project_dir),
        check=True,
        capture_output=True,
        text=True,
    )
    wait_for_database_ready(project_id=project_id)


def reset_local_database(*, project_dir: Path, project_id: str) -> None:
    record_docker_activity(reason="sql_reset")
    proc = subprocess.run(
        ["supabase", "db", "reset", "--local", "--yes"],
        cwd=str(project_dir),
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        wait_for_database_ready(project_id=project_id)
        return
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    raise RuntimeError(f"supabase db reset failed:\n{output}")


def database_container_for_project(*, project_id: str) -> str:
    expected = f"supabase_db_{project_id}"
    proc = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    names = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    if expected in names:
        return expected
    raise RuntimeError(f"Could not find running Supabase database container for project_id={project_id}")


def database_is_ready(*, project_id: str) -> bool:
    try:
        container = database_container_for_project(project_id=project_id)
    except RuntimeError:
        return False
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-X",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-At",
            "-c",
            "select 1;",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and (proc.stdout or "").strip() == "1"


def database_container_is_paused(*, project_id: str) -> bool:
    container = database_container_for_project(project_id=project_id)
    proc = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Paused}}", container],
        check=True,
        capture_output=True,
        text=True,
    )
    return (proc.stdout or "").strip().lower() == "true"


def resume_local_database_container(*, project_id: str) -> bool:
    try:
        if not database_container_is_paused(project_id=project_id):
            return False
    except RuntimeError:
        return False
    container = database_container_for_project(project_id=project_id)
    subprocess.run(
        ["docker", "unpause", container],
        check=True,
        capture_output=True,
        text=True,
    )
    wait_for_database_ready(project_id=project_id)
    return True


def pause_local_database_container(*, project_id: str) -> bool:
    if not _sql_auto_pause_enabled():
        return False
    try:
        if database_container_is_paused(project_id=project_id):
            return False
    except RuntimeError:
        return False
    container = database_container_for_project(project_id=project_id)
    subprocess.run(
        ["docker", "pause", container],
        check=True,
        capture_output=True,
        text=True,
    )
    return True


def wait_for_database_ready(
    *,
    project_id: str,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 1.0,
) -> bool:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        if database_is_ready(project_id=project_id):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(max(0.1, poll_interval_seconds))


def run_sql_checks(
    *,
    project_dir: Path,
    manifest_path: Path,
    reset: bool = True,
    selected_paths: tuple[str, ...] = (),
) -> None:
    record_docker_activity(reason="sql_checks")
    ensure_local_supabase_stack(project_dir=project_dir)
    project_id = project_id_for_project_dir(project_dir)
    resume_local_database_container(project_id=project_id)
    try:
        if reset:
            reset_local_database(project_dir=project_dir, project_id=project_id)
        container = database_container_for_project(project_id=project_id)
        checks = load_sql_checks(
            project_dir=project_dir,
            manifest_path=manifest_path,
            selected_paths=selected_paths,
        )
        for check in checks:
            record_docker_activity(reason="sql_check")
            _run_sql_check(container=container, check=check)
    finally:
        pause_local_database_container(project_id=project_id)


def _run_sql_check(*, container: str, check: SqlCheck) -> None:
    sql = build_sql_check_script(check=check)
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-X",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
        ],
        input=sql,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        raise RuntimeError(f"SQL assertion failed for {check.name}:\n{output}")


def build_sql_check_script(*, check: SqlCheck) -> str:
    role = _quote_identifier(check.role)
    statements = [
        "BEGIN;",
        f"SET LOCAL ROLE {role};",
    ]
    if check.jwt_sub:
        statements.append(
            f"SELECT set_config('request.jwt.claim.sub', {_quote_literal(check.jwt_sub)}, true);"
        )
    if check.jwt_role:
        statements.append(
            f"SELECT set_config('request.jwt.claim.role', {_quote_literal(check.jwt_role)}, true);"
        )
    body = check.path.read_text(encoding="utf-8").strip()
    statements.append(body)
    statements.append("ROLLBACK;")
    return "\n".join(statements) + "\n"


def _quote_identifier(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError("SQL role identifier cannot be empty.")
    return '"' + candidate.replace('"', '""') + '"'


def _sql_auto_pause_enabled() -> bool:
    raw = str(os.getenv("FLOW_HEALER_SQL_AUTO_PAUSE_SUPABASE", "1")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _quote_literal(value: str) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def _ensure_command_available(command: str) -> None:
    proc = subprocess.run(
        ["bash", "-lc", f"command -v {command} >/dev/null 2>&1"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"required command missing: {command}")


def _normalize_manifest_relative_path(path: str) -> str:
    value = str(path or "").strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def _selected_path_matches_manifest_path(*, selected_path: str, manifest_path: str) -> bool:
    if selected_path == manifest_path:
        return True
    return selected_path.endswith(f"/{manifest_path}")


def _resolve_project_relative_path(*, project_root: Path, relative_path: str) -> Path:
    root = project_root.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"Requested SQL assertion path is outside the project directory: {relative_path}"
        ) from exc
    return candidate


def _ad_hoc_sql_checks(*, project_dir: Path, selected_paths: tuple[str, ...]) -> list[SqlCheck]:
    checks: list[SqlCheck] = []
    for selected_path in selected_paths:
        check_path = _resolve_selected_check_path(project_root=project_dir, selected_path=selected_path)
        if not check_path.is_file():
            raise ValueError(f"Requested SQL assertion path does not exist: {selected_path}")
        checks.append(
            SqlCheck(
                name=check_path.stem,
                path=check_path,
            )
        )
    return checks


def _resolve_selected_check_path(*, project_root: Path, selected_path: str) -> Path:
    normalized = _normalize_manifest_relative_path(selected_path)
    direct = _resolve_project_relative_path(project_root=project_root, relative_path=normalized)
    if direct.is_file():
        return direct

    parts = PurePosixPath(normalized).parts
    for index in range(1, len(parts)):
        suffix = PurePosixPath(*parts[index:]).as_posix()
        candidate = _resolve_project_relative_path(project_root=project_root, relative_path=suffix)
        if candidate.is_file():
            return candidate
    return direct


def _bool_from_env(name: str) -> bool:
    value = str(os.getenv(name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _check_paths_from_env() -> tuple[str, ...]:
    raw = str(os.getenv("FLOW_HEALER_SQL_CHECK_PATHS_JSON") or "").strip()
    if not raw:
        return ()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("FLOW_HEALER_SQL_CHECK_PATHS_JSON must be valid JSON.") from exc
    if not isinstance(payload, list):
        raise ValueError("FLOW_HEALER_SQL_CHECK_PATHS_JSON must decode to a list of paths.")
    return tuple(
        normalized
        for item in payload
        if (normalized := _normalize_manifest_relative_path(str(item or "")))
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run reusable SQL assertions against a local Supabase project.")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--manifest", default="supabase/assertions/manifest.json")
    parser.add_argument("--skip-reset", action="store_true")
    parser.add_argument("--check-path", action="append", default=[])
    args = parser.parse_args()

    project_dir = Path(args.project_dir).expanduser().resolve()
    manifest_path = (project_dir / args.manifest).resolve()
    selected_paths = tuple(
        normalized
        for item in [*args.check_path, *_check_paths_from_env()]
        if (normalized := _normalize_manifest_relative_path(item))
    )
    run_sql_checks(
        project_dir=project_dir,
        manifest_path=manifest_path,
        reset=not bool(args.skip_reset or _bool_from_env("FLOW_HEALER_SQL_SKIP_RESET")),
        selected_paths=selected_paths,
    )


if __name__ == "__main__":
    main()
