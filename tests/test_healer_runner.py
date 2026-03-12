import subprocess
import sys
import hashlib
from pathlib import Path

from flow_healer.app_harness import AppHarnessBootResult
from flow_healer.browser_harness import BrowserJourneyResult
from flow_healer.healer_runner import (
    HealerRunner,
    ResolvedExecution,
    _apply_unified_diff_patch,
    _build_proposer_prompt,
    _build_retry_prompt,
    _validate_artifact_outputs,
    _build_docker_test_script,
    _changed_paths,
    _gate_runners_for_mode,
    _looks_like_unified_diff,
    _normalize_test_gate_mode,
    _run_test_gates,
    _run_explicit_validation_commands,
    _run_tests_in_docker,
    _run_tests_locally,
    _run_connector_turn,
    _stage_workspace_changes,
    _task_execution_instructions,
)
from flow_healer.protocols import ConnectorTurnResult
from flow_healer.language_strategies import LanguageStrategy, get_strategy
from flow_healer.healer_task_spec import HealerTaskSpec, compile_task_spec


def test_build_docker_test_script_bootstraps_pytest_and_package_install():
    script = _build_docker_test_script(["pytest", "-q", "tests/test_demo_math.py"])

    assert "python -m pip install --disable-pip-version-check -q pytest" in script
    assert "python -m pip install --disable-pip-version-check -q -e ." in script
    assert '"pytest" "-q" "tests/test_demo_math.py"' in script


def test_build_docker_test_script_skips_editable_install_when_no_python_project():
    script = _build_docker_test_script(["pytest", "-q"])

    assert "if [ -f pyproject.toml ] || [ -f setup.py ] || [ -f setup.cfg ]" in script
    assert script.endswith('"pytest" "-q"')


def test_normalize_test_gate_mode_defaults_to_local_then_docker():
    assert _normalize_test_gate_mode("") == "local_then_docker"
    assert _normalize_test_gate_mode("weird") == "local_then_docker"
    assert _normalize_test_gate_mode("local-then-docker") == "local_then_docker"


def test_gate_runners_for_mode_local_then_docker():
    assert [name for name, _ in _gate_runners_for_mode("local_then_docker")] == ["local", "docker"]


def test_run_test_gates_runs_local_then_docker(monkeypatch):
    calls: list[tuple[str, list[str]]] = []

    def fake_local(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        calls.append(("local", command))
        return {"exit_code": 0, "output_tail": "local ok", "gate_status": "passed", "gate_reason": ""}

    def fake_docker(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        calls.append(("docker", command))
        return {"exit_code": 0, "output_tail": "docker ok", "gate_status": "passed", "gate_reason": ""}

    monkeypatch.setattr("flow_healer.healer_runner._run_tests_locally", fake_local)
    monkeypatch.setattr("flow_healer.healer_runner._run_tests_in_docker", fake_docker)

    summary = _run_test_gates(
        Path("."),
        targeted_tests=["tests/test_demo.py"],
        timeout_seconds=30,
        mode="local_then_docker",
        resolved_execution=ResolvedExecution(
            language_detected="python",
            language_effective="python",
            execution_root="",
            execution_root_source="repo",
            execution_path=Path("."),
            strategy=get_strategy("python"),
        ),
        local_gate_policy="auto",
    )

    assert calls == [
        ("local", ["pytest", "-q", "tests/test_demo.py"]),
        ("docker", ["pytest", "-q", "tests/test_demo.py"]),
        ("local", ["pytest", "-q"]),
        ("docker", ["pytest", "-q"]),
    ]
    assert summary["local_targeted_exit_code"] == 0
    assert summary["docker_full_exit_code"] == 0
    assert summary["failed_tests"] == 0
    assert summary["validation_lane"] == "fast_then_full"
    assert summary["promotion_state"] == "promotion_ready"
    assert summary["phase_states"] == {
        "fast_pass": True,
        "full_pass": True,
        "promotion_ready": True,
        "merge_blocked": False,
    }


def test_run_test_gates_marks_full_only_lane_when_no_targeted_tests(monkeypatch, tmp_path):
    calls: list[tuple[str, list[str]]] = []

    def fake_local(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        calls.append(("local", command))
        return {"exit_code": 0, "output_tail": "local ok", "gate_status": "passed", "gate_reason": ""}

    monkeypatch.setattr("flow_healer.healer_runner._run_tests_locally", fake_local)

    summary = _run_test_gates(
        tmp_path,
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_only",
        resolved_execution=ResolvedExecution(
            language_detected="python",
            language_effective="python",
            execution_root="",
            execution_root_source="repo",
            execution_path=tmp_path,
            strategy=get_strategy("python"),
        ),
        local_gate_policy="auto",
    )

    assert calls == [("local", ["pytest", "-q"])]
    assert summary["validation_lane"] == "full_only"
    assert summary["promotion_state"] == "promotion_ready"
    assert summary["phase_states"] == {
        "fast_pass": False,
        "full_pass": True,
        "promotion_ready": True,
        "merge_blocked": False,
    }


def test_run_test_gates_marks_merge_blocked_when_fast_pass_fails(monkeypatch, tmp_path):
    calls: list[tuple[str, list[str]]] = []

    def fake_local(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        calls.append(("local", command))
        if command[-1] == "tests/test_demo.py":
            return {"exit_code": 1, "output_tail": "targeted failed", "gate_status": "failed", "gate_reason": ""}
        return {"exit_code": 0, "output_tail": "full ok", "gate_status": "passed", "gate_reason": ""}

    monkeypatch.setattr("flow_healer.healer_runner._run_tests_locally", fake_local)

    summary = _run_test_gates(
        tmp_path,
        targeted_tests=["tests/test_demo.py"],
        timeout_seconds=30,
        mode="local_only",
        resolved_execution=ResolvedExecution(
            language_detected="python",
            language_effective="python",
            execution_root="",
            execution_root_source="repo",
            execution_path=tmp_path,
            strategy=get_strategy("python"),
        ),
        local_gate_policy="auto",
    )

    assert calls == [
        ("local", ["pytest", "-q", "tests/test_demo.py"]),
        ("local", ["pytest", "-q"]),
    ]
    assert summary["failed_tests"] == 1
    assert summary["validation_lane"] == "fast_then_full"
    assert summary["promotion_state"] == "merge_blocked"
    assert summary["phase_states"] == {
        "fast_pass": False,
        "full_pass": True,
        "promotion_ready": False,
        "merge_blocked": True,
    }


def test_run_test_gates_prefers_explicit_validation_commands(monkeypatch, tmp_path):
    calls: list[tuple[str, object]] = []

    def fake_explicit(workspace: Path, commands: tuple[str, ...], timeout_seconds: int):
        calls.append(("explicit", commands))
        return {"exit_code": 0, "output_tail": "explicit ok", "gate_status": "passed", "gate_reason": ""}

    def fake_local(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        calls.append(("local", command))
        return {"exit_code": 0, "output_tail": "local ok", "gate_status": "passed", "gate_reason": ""}

    def fake_docker(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        calls.append(("docker", command))
        return {"exit_code": 0, "output_tail": "docker ok", "gate_status": "passed", "gate_reason": ""}

    monkeypatch.setattr("flow_healer.healer_runner._run_explicit_validation_commands", fake_explicit)
    monkeypatch.setattr("flow_healer.healer_runner._run_tests_locally", fake_local)
    monkeypatch.setattr("flow_healer.healer_runner._run_tests_in_docker", fake_docker)

    summary = _run_test_gates(
        tmp_path,
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_then_docker",
        resolved_execution=ResolvedExecution(
            language_detected="node",
            language_effective="node",
            execution_root="e2e-apps/prosper-chat",
            execution_root_source="issue",
            execution_path=tmp_path,
            strategy=get_strategy("node"),
        ),
        validation_commands=("cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh full",),
        local_gate_policy="auto",
    )

    assert calls == [("explicit", ("./scripts/healer_validate.sh full",))]
    assert summary["local_full_status"] == "passed"
    assert summary["docker_full_status"] == "skipped"
    assert summary["docker_full_reason"] == "explicit_validation_commands"
    assert summary["validation_commands"] == ["./scripts/healer_validate.sh full"]


def test_run_test_gates_normalizes_prosper_chat_frontend_validation_alias(monkeypatch, tmp_path):
    calls: list[tuple[str, object]] = []

    def fake_explicit(workspace: Path, commands: tuple[str, ...], timeout_seconds: int):
        calls.append(("explicit", commands))
        return {"exit_code": 0, "output_tail": "explicit ok", "gate_status": "passed", "gate_reason": ""}

    monkeypatch.setattr("flow_healer.healer_runner._run_explicit_validation_commands", fake_explicit)

    summary = _run_test_gates(
        tmp_path,
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_then_docker",
        resolved_execution=ResolvedExecution(
            language_detected="node",
            language_effective="node",
            execution_root="e2e-apps/prosper-chat",
            execution_root_source="issue",
            execution_path=tmp_path,
            strategy=get_strategy("node"),
        ),
        validation_commands=("cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh frontend",),
        local_gate_policy="auto",
    )

    assert calls == [("explicit", ("./scripts/healer_validate.sh web",))]
    assert summary["local_full_status"] == "passed"
    assert summary["validation_commands"] == ["./scripts/healer_validate.sh web"]


def test_run_test_gates_expands_sql_issue_validation_to_targeted_then_full(monkeypatch, tmp_path):
    calls: list[tuple[str, object]] = []

    def fake_explicit(workspace: Path, commands: tuple[str, ...], timeout_seconds: int):
        calls.append(("explicit", commands))
        return {"exit_code": 0, "output_tail": "explicit ok", "gate_status": "passed", "gate_reason": ""}

    monkeypatch.setattr("flow_healer.healer_runner._run_explicit_validation_commands", fake_explicit)

    task_spec = HealerTaskSpec(
        task_kind="edit",
        output_mode="patch",
        output_targets=(
            "e2e-apps/prosper-chat/supabase/migrations/20260301215513_a3f9ada2-3230-44bf-a5ef-90d631a3961c.sql",
            "e2e-apps/prosper-chat/supabase/assertions/subscription_visibility.sql",
        ),
        tool_policy="repo_only",
        validation_profile="code_change",
        language="node",
        execution_root="e2e-apps/prosper-chat",
        validation_commands=("cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh db",),
    )

    summary = _run_test_gates(
        tmp_path,
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_then_docker",
        resolved_execution=ResolvedExecution(
            language_detected="node",
            language_effective="node",
            execution_root="e2e-apps/prosper-chat",
            execution_root_source="issue",
            execution_path=tmp_path,
            strategy=get_strategy("node"),
        ),
        validation_commands=task_spec.validation_commands,
        task_spec=task_spec,
        local_gate_policy="auto",
    )

    assert len(calls) == 1
    commands = calls[0][1]
    assert commands == (
        (
            "unset FLOW_HEALER_SQL_SKIP_RESET; export FLOW_HEALER_SQL_CHECK_PATHS_JSON="
            "'[\"e2e-apps/prosper-chat/supabase/assertions/subscription_visibility.sql\"]'; "
            "./scripts/healer_validate.sh db"
        ),
        (
            "unset FLOW_HEALER_SQL_CHECK_PATHS_JSON; export FLOW_HEALER_SQL_SKIP_RESET=1; "
            "./scripts/healer_validate.sh db"
        ),
    )
    assert summary["validation_commands"] == list(commands)


def test_run_test_gates_rewrites_nested_execution_root_cd_to_local_command(monkeypatch, tmp_path):
    calls: list[tuple[str, object]] = []

    def fake_explicit(workspace: Path, commands: tuple[str, ...], timeout_seconds: int):
        calls.append(("explicit", commands))
        return {"exit_code": 0, "output_tail": "explicit ok", "gate_status": "passed", "gate_reason": ""}

    monkeypatch.setattr("flow_healer.healer_runner._run_explicit_validation_commands", fake_explicit)

    summary = _run_test_gates(
        tmp_path,
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_then_docker",
        resolved_execution=ResolvedExecution(
            language_detected="node",
            language_effective="node",
            execution_root="e2e-apps/prosper-chat",
            execution_root_source="issue",
            execution_path=tmp_path,
            strategy=get_strategy("node"),
        ),
        validation_commands=("cd e2e-apps/prosper-chat/supabase && supabase db reset --local --yes",),
        local_gate_policy="auto",
    )

    assert calls == [("explicit", ("cd supabase && supabase db reset --local --yes",))]
    assert summary["validation_commands"] == ["cd supabase && supabase db reset --local --yes"]


def test_run_test_gates_rejects_validation_commands_outside_execution_root(tmp_path):
    summary = _run_test_gates(
        tmp_path,
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_then_docker",
        resolved_execution=ResolvedExecution(
            language_detected="node",
            language_effective="node",
            execution_root="e2e-apps/prosper-chat",
            execution_root_source="issue",
            execution_path=tmp_path,
            strategy=get_strategy("node"),
        ),
        validation_commands=("cd e2e-smoke/node && npm test",),
        local_gate_policy="auto",
    )

    assert summary["failed_tests"] == 1
    assert summary["failure_class"] == "validation_command_invalid"
    assert "outside the execution root" in summary["failure_reason"]
    assert summary["local_full_status"] == "failed"
    assert summary["local_full_reason"] == "validation_command_invalid"


def test_run_test_gates_keeps_full_sql_validation_when_issue_has_no_assertion_target(monkeypatch, tmp_path):
    calls: list[tuple[str, object]] = []

    def fake_explicit(workspace: Path, commands: tuple[str, ...], timeout_seconds: int):
        calls.append(("explicit", commands))
        return {"exit_code": 0, "output_tail": "explicit ok", "gate_status": "passed", "gate_reason": ""}

    monkeypatch.setattr("flow_healer.healer_runner._run_explicit_validation_commands", fake_explicit)

    task_spec = HealerTaskSpec(
        task_kind="edit",
        output_mode="patch",
        output_targets=("db/migrations/202603090001_add_index.sql",),
        tool_policy="repo_only",
        validation_profile="code_change",
        language="node",
        validation_commands=("python3 scripts/flow_healer_sql_validate.py --project-dir .",),
    )

    summary = _run_test_gates(
        tmp_path,
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_then_docker",
        resolved_execution=ResolvedExecution(
            language_detected="node",
            language_effective="node",
            execution_root="",
            execution_root_source="issue",
            execution_path=tmp_path,
            strategy=get_strategy("node"),
        ),
        validation_commands=task_spec.validation_commands,
        task_spec=task_spec,
        local_gate_policy="auto",
    )

    assert calls == [("explicit", ("python3 scripts/flow_healer_sql_validate.py --project-dir .",))]
    assert summary["validation_commands"] == ["python3 scripts/flow_healer_sql_validate.py --project-dir ."]


def test_run_tests_locally_normalizes_pytest_command(monkeypatch, tmp_path):
    seen: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["cwd"] = kwargs.get("cwd")
        seen["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = _run_tests_locally(
        tmp_path,
        ["pytest", "-q", "tests/test_demo.py"],
        30,
        strategy=get_strategy("python"),
        local_gate_policy="auto",
    )

    assert seen["cmd"] == [sys.executable, "-m", "pytest", "-q", "tests/test_demo.py"]
    assert seen["cwd"] == str(tmp_path)
    assert str(tmp_path) in seen["env"]["PYTHONPATH"]
    assert summary["gate_status"] == "passed"


def test_run_tests_locally_bootstraps_bundle_for_rspec(monkeypatch, tmp_path):
    calls: list[object] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["/bin/zsh", "-lc", "bundle check >/dev/null 2>&1 || bundle install --jobs 2 --retry 1"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="bundle ok", stderr="")
        if cmd == ["bundle", "exec", "rspec"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="rspec ok", stderr="")
        raise AssertionError(f"Unexpected command: {cmd!r}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = _run_tests_locally(
        tmp_path,
        ["bundle", "exec", "rspec"],
        30,
        strategy=get_strategy("ruby"),
        local_gate_policy="auto",
    )

    assert calls[0] == ["/bin/zsh", "-lc", "bundle check >/dev/null 2>&1 || bundle install --jobs 2 --retry 1"]
    assert calls[1] == ["bundle", "exec", "rspec"]
    assert summary["gate_status"] == "passed"


def test_run_tests_locally_falls_back_when_bundle_exec_rspec_missing(monkeypatch, tmp_path):
    calls: list[object] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["/bin/zsh", "-lc", "bundle check >/dev/null 2>&1 || bundle install --jobs 2 --retry 1"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd == ["bundle", "exec", "rspec"]:
            return subprocess.CompletedProcess(cmd, 127, stdout="", stderr="bundler: command not found: rspec")
        if (
            isinstance(cmd, list)
            and len(cmd) == 3
            and cmd[0] == "/bin/zsh"
            and cmd[1] == "-lc"
            and str(cmd[2]).startswith("bundle exec ruby -e")
        ):
            return subprocess.CompletedProcess(cmd, 0, stdout="fallback ok", stderr="")
        raise AssertionError(f"Unexpected command: {cmd!r}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = _run_tests_locally(
        tmp_path,
        ["bundle", "exec", "rspec"],
        30,
        strategy=get_strategy("ruby"),
        local_gate_policy="auto",
    )

    assert calls[0] == ["/bin/zsh", "-lc", "bundle check >/dev/null 2>&1 || bundle install --jobs 2 --retry 1"]
    assert calls[1] == ["bundle", "exec", "rspec"]
    assert summary["gate_status"] == "passed"
    assert "bundle exec ruby -e" in summary["output_tail"]


def test_run_tests_in_docker_uses_posix_shell(monkeypatch, tmp_path):
    seen: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = _run_tests_in_docker(
        tmp_path,
        ["npm", "test", "--", "--passWithNoTests"],
        30,
        strategy=get_strategy("node"),
        local_gate_policy="auto",
    )

    expected_hash = hashlib.sha1(str(tmp_path.resolve()).encode("utf-8")).hexdigest()[:12]
    expected_name = f"flow-healer-{tmp_path.name.lower()}-test-gate-{expected_hash}"
    cmd = seen["cmd"]
    assert cmd[0:4] == [
        "docker",
        "run",
        "--rm",
        "--name",
    ]
    assert cmd[4] == expected_name
    assert "--label" in cmd
    assert "io.flow_healer.managed=true" in cmd
    assert f"io.flow_healer.repo_name={tmp_path.name.lower()}" in cmd
    assert f"io.flow_healer.repo_hash={expected_hash}" in cmd
    assert "io.flow_healer.role=test-gate" in cmd
    assert "io.flow_healer.timeout_seconds=30" in cmd
    assert cmd[-3:] == ["node:20-slim", "sh", "-c"] or cmd[-4:-1] == ["node:20-slim", "sh", "-c"]
    assert cmd[-2:] == ["-c", cmd[-1]]
    assert summary["gate_status"] == "passed"


def test_run_tests_in_docker_reports_missing_docker(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = _run_tests_in_docker(
        tmp_path,
        ["npm", "test", "--", "--passWithNoTests"],
        30,
        strategy=get_strategy("node"),
        local_gate_policy="auto",
    )

    assert summary["gate_status"] == "failed"
    assert summary["gate_reason"] == "tool_missing"
    assert summary["exit_code"] == 127


def test_run_tests_in_docker_timeout_attempts_cleanup(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = _run_tests_in_docker(
        tmp_path,
        ["npm", "test"],
        30,
        strategy=get_strategy("node"),
        local_gate_policy="auto",
    )

    assert summary["gate_status"] == "failed"
    assert summary["gate_reason"] == "infra_unavailable"
    cleanup_calls = [cmd for cmd in calls if cmd[0:3] == ["docker", "rm", "-f"]]
    assert cleanup_calls
    assert cleanup_calls[0][3].startswith(f"flow-healer-{tmp_path.name.lower()}-test-gate-")


def test_run_tests_in_docker_error_attempts_cleanup(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0:2] == ["docker", "run"]:
            return subprocess.CompletedProcess(
                cmd,
                1,
                stdout="",
                stderr="Cannot connect to the Docker daemon",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = _run_tests_in_docker(
        tmp_path,
        ["npm", "test"],
        30,
        strategy=get_strategy("node"),
        local_gate_policy="auto",
    )

    assert summary["gate_status"] == "failed"
    cleanup_calls = [cmd for cmd in calls if cmd[0:3] == ["docker", "rm", "-f"]]
    assert cleanup_calls


def test_validate_artifact_outputs_passes_valid_relative_links(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    guide = docs / "guide.md"
    guide.write_text("# Guide\n", encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text("[Guide](docs/guide.md)\n", encoding="utf-8")

    summary = _validate_artifact_outputs(workspace=tmp_path, diff_paths=["README.md"])

    assert summary["passed"] is True
    assert summary["failed_tests"] == 0
    assert summary["broken_links"] == []


def test_validate_artifact_outputs_ignores_external_and_code_block_links(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "[Website](https://example.com)\n\n```md\n[Broken](missing.md)\n```\n",
        encoding="utf-8",
    )

    summary = _validate_artifact_outputs(workspace=tmp_path, diff_paths=["README.md"])

    assert summary["passed"] is True
    assert summary["broken_links"] == []


def test_validate_artifact_outputs_fails_broken_relative_links(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("[Guide](docs/missing.md)\n", encoding="utf-8")

    summary = _validate_artifact_outputs(workspace=tmp_path, diff_paths=["README.md"])

    assert summary["passed"] is False
    assert summary["failed_tests"] == 1
    assert summary["broken_links"] == [{"file": "README.md", "line": "1", "target": "docs/missing.md"}]


def test_validate_artifact_outputs_passes_structured_files(tmp_path):
    (tmp_path / "report.json").write_text('{"ok": true}\n', encoding="utf-8")
    (tmp_path / "config.yaml").write_text("name: flow-healer\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")

    summary = _validate_artifact_outputs(
        workspace=tmp_path,
        diff_paths=["report.json", "config.yaml", "pyproject.toml"],
    )

    assert summary["passed"] is True
    assert summary["failed_tests"] == 0
    assert summary["parse_errors"] == []


def test_validate_artifact_outputs_fails_invalid_json(tmp_path):
    (tmp_path / "report.json").write_text('{"ok": }\n', encoding="utf-8")

    summary = _validate_artifact_outputs(workspace=tmp_path, diff_paths=["report.json"])

    assert summary["passed"] is False
    assert summary["failed_tests"] == 1
    assert summary["parse_errors"]
    assert summary["parse_errors"][0]["file"] == "report.json"
    assert summary["parse_errors"][0]["type"] == "json"


def test_validate_artifact_outputs_fails_invalid_yaml(tmp_path):
    (tmp_path / "config.yaml").write_text("name: [broken\n", encoding="utf-8")

    summary = _validate_artifact_outputs(workspace=tmp_path, diff_paths=["config.yaml"])

    assert summary["passed"] is False
    assert summary["failed_tests"] == 1
    assert summary["parse_errors"]
    assert summary["parse_errors"][0]["file"] == "config.yaml"
    assert summary["parse_errors"][0]["type"] == "yaml"


def test_validate_artifact_outputs_fails_invalid_toml(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project\nname = 'demo'\n", encoding="utf-8")

    summary = _validate_artifact_outputs(workspace=tmp_path, diff_paths=["pyproject.toml"])

    assert summary["passed"] is False
    assert summary["failed_tests"] == 1
    assert summary["parse_errors"]
    assert summary["parse_errors"][0]["file"] == "pyproject.toml"
    assert summary["parse_errors"][0]["type"] == "toml"


def test_run_test_gates_runs_from_resolved_execution_root(monkeypatch, tmp_path):
    sandbox = tmp_path / "e2e-smoke" / "node"
    sandbox.mkdir(parents=True)
    calls: list[tuple[str, Path]] = []

    def fake_local(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        calls.append(("local", workspace))
        return {"exit_code": 0, "output_tail": "local ok", "gate_status": "passed", "gate_reason": ""}

    def fake_docker(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        calls.append(("docker", workspace))
        return {"exit_code": 0, "output_tail": "docker ok", "gate_status": "passed", "gate_reason": ""}

    monkeypatch.setattr("flow_healer.healer_runner._run_tests_locally", fake_local)
    monkeypatch.setattr("flow_healer.healer_runner._run_tests_in_docker", fake_docker)

    summary = _run_test_gates(
        tmp_path,
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_then_docker",
        resolved_execution=ResolvedExecution(
            language_detected="node",
            language_effective="node",
            execution_root="e2e-smoke/node",
            execution_root_source="issue",
            execution_path=sandbox,
            strategy=get_strategy("node"),
        ),
        local_gate_policy="auto",
    )

    assert calls == [("local", sandbox), ("docker", sandbox)]
    assert summary["execution_root"] == "e2e-smoke/node"
    assert summary["execution_root_source"] == "issue"


def test_run_test_gates_skips_docker_for_language_without_docker_support(monkeypatch, tmp_path):
    sandbox = tmp_path / "e2e-smoke" / "custom"
    sandbox.mkdir(parents=True)
    calls: list[tuple[str, Path, list[str]]] = []

    def fake_local(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        calls.append(("local", workspace, command))
        return {"exit_code": 0, "output_tail": "local ok", "gate_status": "passed", "gate_reason": ""}

    def fake_docker(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        calls.append(("docker", workspace, command))
        return {"exit_code": 0, "output_tail": "docker ok", "gate_status": "passed", "gate_reason": ""}

    monkeypatch.setattr("flow_healer.healer_runner._run_tests_locally", fake_local)
    monkeypatch.setattr("flow_healer.healer_runner._run_tests_in_docker", fake_docker)

    summary = _run_test_gates(
        tmp_path,
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_then_docker",
        resolved_execution=ResolvedExecution(
            language_detected="custom",
            language_effective="custom",
            execution_root="e2e-smoke/custom",
            execution_root_source="issue",
            execution_path=sandbox,
            strategy=LanguageStrategy(
                language="custom",
                framework="generic",
                docker_image="",
                docker_install_cmd="",
                docker_test_cmd=["custom-test"],
                local_test_cmd=["custom-test"],
                supports_targeted_paths=False,
                supports_docker=False,
            ),
        ),
        local_gate_policy="auto",
    )

    assert calls == [("local", sandbox, ["custom-test"])]
    assert summary["local_full_status"] == "passed"
    assert summary["docker_full_status"] == "skipped"
    assert summary["docker_full_reason"] == "docker_unsupported_for_language"
    assert summary["failed_tests"] == 0


def test_run_test_gates_fails_docker_only_for_language_without_docker_support(monkeypatch, tmp_path):
    sandbox = tmp_path / "e2e-smoke" / "custom"
    sandbox.mkdir(parents=True)
    calls: list[tuple[str, Path, list[str]]] = []

    def fake_docker(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        calls.append(("docker", workspace, command))
        return {"exit_code": 0, "output_tail": "docker ok", "gate_status": "passed", "gate_reason": ""}

    monkeypatch.setattr("flow_healer.healer_runner._run_tests_in_docker", fake_docker)

    summary = _run_test_gates(
        tmp_path,
        targeted_tests=[],
        timeout_seconds=30,
        mode="docker_only",
        resolved_execution=ResolvedExecution(
            language_detected="custom",
            language_effective="custom",
            execution_root="e2e-smoke/custom",
            execution_root_source="issue",
            execution_path=sandbox,
            strategy=LanguageStrategy(
                language="custom",
                framework="generic",
                docker_image="",
                docker_install_cmd="",
                docker_test_cmd=["custom-test"],
                local_test_cmd=["custom-test"],
                supports_targeted_paths=False,
                supports_docker=False,
            ),
        ),
        local_gate_policy="auto",
    )

    assert calls == []
    assert summary["docker_full_status"] == "failed"
    assert summary["docker_full_reason"] == "docker_unsupported_for_language"
    assert summary["failed_tests"] == 1


def test_run_test_gates_soft_fails_docker_infra_when_local_passes(monkeypatch):
    def fake_local(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        return {"exit_code": 0, "output_tail": "local ok", "gate_status": "passed", "gate_reason": ""}

    def fake_docker(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        return {
            "exit_code": 1,
            "output_tail": "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?",
            "gate_status": "failed",
            "gate_reason": "",
        }

    monkeypatch.setattr("flow_healer.healer_runner._run_tests_locally", fake_local)
    monkeypatch.setattr("flow_healer.healer_runner._run_tests_in_docker", fake_docker)

    summary = _run_test_gates(
        Path("."),
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_then_docker",
        resolved_execution=ResolvedExecution(
            language_detected="python",
            language_effective="python",
            execution_root="",
            execution_root_source="repo",
            execution_path=Path("."),
            strategy=get_strategy("python"),
        ),
        local_gate_policy="auto",
    )

    assert summary["local_full_status"] == "passed"
    assert summary["docker_full_status"] == "warning"
    assert summary["docker_full_reason"] == "docker_infra_unavailable"
    assert summary["failed_tests"] == 0


def test_run_test_gates_keeps_docker_test_failures_hard_failed(monkeypatch):
    def fake_local(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        return {"exit_code": 0, "output_tail": "local ok", "gate_status": "passed", "gate_reason": ""}

    def fake_docker(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        return {
            "exit_code": 1,
            "output_tail": "AssertionError: expected 2 got 1",
            "gate_status": "failed",
            "gate_reason": "",
        }

    monkeypatch.setattr("flow_healer.healer_runner._run_tests_locally", fake_local)
    monkeypatch.setattr("flow_healer.healer_runner._run_tests_in_docker", fake_docker)

    summary = _run_test_gates(
        Path("."),
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_then_docker",
        resolved_execution=ResolvedExecution(
            language_detected="python",
            language_effective="python",
            execution_root="",
            execution_root_source="repo",
            execution_path=Path("."),
            strategy=get_strategy("python"),
        ),
        local_gate_policy="auto",
    )

    assert summary["local_full_status"] == "passed"
    assert summary["docker_full_status"] == "failed"
    assert summary["failed_tests"] == 1


def test_resolve_execution_prefers_issue_sandbox_over_repo_root_python(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    node_root = tmp_path / "e2e-smoke" / "node"
    node_root.mkdir(parents=True)
    (node_root / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")

    runner = HealerRunner(connector=None, timeout_seconds=30)  # type: ignore[arg-type]
    task_spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="patch",
        output_targets=("e2e-smoke/node/src/add.js",),
        tool_policy="repo_only",
        validation_profile="code_change",
        language="node",
        language_source="issue",
        execution_root="e2e-smoke/node",
        validation_commands=("cd e2e-smoke/node && npm test -- --passWithNoTests",),
    )

    resolved = runner.resolve_execution(workspace=tmp_path, task_spec=task_spec)

    assert resolved.language_detected == "node"
    assert resolved.language_effective == "node"
    assert resolved.execution_root == "e2e-smoke/node"
    assert resolved.execution_root_source == "issue"
    assert resolved.execution_path == node_root


def test_resolve_execution_ignores_global_override_for_explicit_issue_language(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    node_root = tmp_path / "e2e-smoke" / "node"
    node_root.mkdir(parents=True)
    (node_root / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")

    runner = HealerRunner(connector=None, timeout_seconds=30, language="python", test_command="pytest -q")  # type: ignore[arg-type]
    task_spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="patch",
        output_targets=("e2e-smoke/node/src/add.js",),
        tool_policy="repo_only",
        validation_profile="code_change",
        language="node",
        language_source="issue",
        execution_root="e2e-smoke/node",
        validation_commands=("cd e2e-smoke/node && npm test -- --passWithNoTests",),
    )

    resolved = runner.resolve_execution(workspace=tmp_path, task_spec=task_spec)

    assert resolved.language_effective == "node"
    assert resolved.strategy.local_test_cmd == ["npm", "test", "--", "--passWithNoTests"]


def test_resolve_execution_leaves_language_empty_for_ambiguous_repo_markers(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")

    runner = HealerRunner(connector=None, timeout_seconds=30)  # type: ignore[arg-type]
    task_spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="patch",
        output_targets=("src/demo.py",),
        tool_policy="repo_only",
        validation_profile="code_change",
    )

    resolved = runner.resolve_execution(workspace=tmp_path, task_spec=task_spec)

    assert resolved.language_detected == ""
    assert resolved.language_effective == ""
    assert resolved.strategy.local_test_cmd == []
    assert resolved.strategy.docker_test_cmd == []


def test_validate_workspace_fails_closed_for_ambiguous_repo_markers_without_language_hints(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")

    runner = HealerRunner(connector=None, timeout_seconds=30)  # type: ignore[arg-type]
    task_spec = HealerTaskSpec(
        task_kind="fix",
        output_mode="patch",
        output_targets=("src/demo.py",),
        tool_policy="repo_only",
        validation_profile="code_change",
    )

    summary = runner.validate_workspace(
        tmp_path,
        task_spec=task_spec,
        targeted_tests=[],
        mode="local_then_docker",
    )

    assert summary["failed_tests"] == 1
    assert summary["failure_class"] == "language_unresolved"
    assert "explicit issue language or validation command" in summary["failure_reason"]
    assert summary["local_full_status"] == "failed"
    assert summary["local_full_reason"] == "language_unresolved"


def test_run_test_gates_preserves_python3_pytest_command_with_execution_root(monkeypatch, tmp_path):
    calls: list[tuple[str, object]] = []

    def fake_explicit(workspace: Path, commands: tuple[str, ...], timeout_seconds: int):
        calls.append(("explicit", commands))
        return {"exit_code": 0, "output_tail": "explicit ok", "gate_status": "passed", "gate_reason": ""}

    monkeypatch.setattr("flow_healer.healer_runner._run_explicit_validation_commands", fake_explicit)

    summary = _run_test_gates(
        tmp_path,
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_then_docker",
        resolved_execution=ResolvedExecution(
            language_detected="python",
            language_effective="python",
            execution_root="e2e-apps/python-fastapi",
            execution_root_source="issue",
            execution_path=tmp_path,
            strategy=get_strategy("python"),
        ),
        validation_commands=("cd e2e-apps/python-fastapi && python3 -m pytest -q",),
        local_gate_policy="auto",
    )

    assert calls == [("explicit", ("python3 -m pytest -q",))]
    assert summary["validation_commands"] == ["python3 -m pytest -q"]


def test_run_explicit_validation_commands_bootstraps_bundle_for_rspec(monkeypatch, tmp_path):
    shell_commands: list[str] = []
    env_snapshots: list[dict[str, str]] = []

    def fake_run(*args, **kwargs):
        command = args[0]
        shell_command = command[2]
        shell_commands.append(shell_command)
        env_snapshots.append(dict(kwargs.get("env") or {}))
        if shell_command.startswith("bundle check"):
            return subprocess.CompletedProcess(command, 0, "", "")
        if shell_command == "bundle exec rspec":
            return subprocess.CompletedProcess(command, 0, "2 examples, 0 failures", "")
        raise AssertionError(f"Unexpected command: {shell_command}")

    monkeypatch.setattr("flow_healer.healer_runner.subprocess.run", fake_run)

    result = _run_explicit_validation_commands(
        tmp_path,
        commands=("bundle exec rspec",),
        timeout_seconds=30,
    )

    assert result["gate_status"] == "passed"
    assert shell_commands == [
        "bundle check >/dev/null 2>&1 || bundle install --jobs 2 --retry 1",
        "bundle exec rspec",
    ]
    assert any(snapshot.get("BUNDLE_PATH") for snapshot in env_snapshots)
    assert any(snapshot.get("BUNDLE_APP_CONFIG") for snapshot in env_snapshots)


def test_run_explicit_validation_commands_falls_back_when_bundle_exec_rspec_missing(monkeypatch, tmp_path):
    shell_commands: list[str] = []

    def fake_run(*args, **kwargs):
        command = args[0]
        shell_command = command[2]
        shell_commands.append(shell_command)
        if shell_command.startswith("bundle check"):
            return subprocess.CompletedProcess(command, 0, "", "")
        if shell_command == "bundle exec rspec":
            return subprocess.CompletedProcess(command, 127, "", "bundler: command not found: rspec")
        if shell_command.startswith("bundle exec ruby -e"):
            return subprocess.CompletedProcess(command, 0, "2 examples, 0 failures", "")
        raise AssertionError(f"Unexpected command: {shell_command}")

    monkeypatch.setattr("flow_healer.healer_runner.subprocess.run", fake_run)

    result = _run_explicit_validation_commands(
        tmp_path,
        commands=("bundle exec rspec",),
        timeout_seconds=30,
    )

    assert result["gate_status"] == "passed"
    assert shell_commands[0] == "bundle check >/dev/null 2>&1 || bundle install --jobs 2 --retry 1"
    assert shell_commands[1] == "bundle exec rspec"
    assert shell_commands[2].startswith("bundle exec ruby -e")


def test_stage_workspace_changes_excludes_python_packaging_artifacts(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    (workspace / "demo.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (workspace / "src" / "flow_healer.egg-info").mkdir(parents=True)
    (workspace / "src" / "flow_healer.egg-info" / "PKG-INFO").write_text("generated\n", encoding="utf-8")
    (workspace / "__pycache__").mkdir()
    (workspace / "__pycache__" / "demo.cpython-311.pyc").write_text("compiled\n", encoding="utf-8")

    changed = _stage_workspace_changes(
        workspace,
        issue_title="Fix demo",
        issue_body="Repair demo.py",
        task_spec=compile_task_spec(issue_title="Fix demo", issue_body="Repair demo.py"),
        language="python",
    )

    assert changed is True
    assert _changed_paths(workspace) == ["demo.py"]


def test_stage_workspace_changes_allows_explicit_lockfile_targets(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    (workspace / "package-lock.json").write_text('{"lockfileVersion": 3}\n', encoding="utf-8")

    changed = _stage_workspace_changes(
        workspace,
        issue_title="Update package dependencies",
        issue_body="Update package.json and package-lock.json for the new dependency set.",
        task_spec=HealerTaskSpec(
            task_kind="build",
            output_mode="patch",
            output_targets=("package-lock.json",),
            tool_policy="repo_only",
            validation_profile="code_change",
            language="node",
        ),
        language="node",
    )

    assert changed is True
    assert _changed_paths(workspace) == ["package-lock.json"]


def test_stage_workspace_changes_excludes_ruby_lockfile_when_only_validation_mentions_bundle(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "app" / "controllers").mkdir(parents=True)
    (workspace / "app" / "controllers" / "dashboard_controller.rb").write_text(
        "class DashboardController\nend\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    (workspace / "app" / "controllers" / "dashboard_controller.rb").write_text(
        "class DashboardController\n  def show; end\nend\n",
        encoding="utf-8",
    )
    (workspace / "Gemfile.lock").write_text("GEM\n  specs:\n", encoding="utf-8")

    changed = _stage_workspace_changes(
        workspace,
        issue_title="Ruby app fix",
        issue_body="Validation:\n- cd e2e-apps/ruby-rails-web && bundle exec rspec\n",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("app/controllers/dashboard_controller.rb",),
            tool_policy="repo_only",
            validation_profile="code_change",
            language="ruby",
        ),
        language="ruby",
    )

    assert changed is True
    assert _changed_paths(workspace) == ["app/controllers/dashboard_controller.rb"]


def test_stage_workspace_changes_allows_ruby_lockfile_when_explicitly_requested(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "Gemfile").write_text('source "https://rubygems.org"\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    (workspace / "Gemfile.lock").write_text("GEM\n  specs:\n", encoding="utf-8")

    changed = _stage_workspace_changes(
        workspace,
        issue_title="Update Gemfile.lock",
        issue_body="Refresh Gemfile.lock after dependency updates.",
        task_spec=HealerTaskSpec(
            task_kind="build",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
            language="ruby",
        ),
        language="ruby",
    )

    assert changed is True
    assert _changed_paths(workspace) == ["Gemfile.lock"]


def test_stage_workspace_changes_excludes_ruby_bundle_binstub_artifacts(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "app" / "controllers").mkdir(parents=True)
    (workspace / "app" / "controllers" / "dashboard_controller.rb").write_text(
        "class DashboardController\nend\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    (workspace / "app" / "controllers" / "dashboard_controller.rb").write_text(
        "class DashboardController\n  def show; end\nend\n",
        encoding="utf-8",
    )
    (workspace / "bin").mkdir()
    (workspace / "bin" / "rspec").write_text("#!/usr/bin/env ruby\n", encoding="utf-8")

    changed = _stage_workspace_changes(
        workspace,
        issue_title="Ruby app fix",
        issue_body="Validation:\n- cd e2e-apps/ruby-rails-web && bundle exec rspec\n",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("app/controllers/dashboard_controller.rb",),
            tool_policy="repo_only",
            validation_profile="code_change",
            language="ruby",
        ),
        language="ruby",
    )

    assert changed is True
    assert _changed_paths(workspace) == ["app/controllers/dashboard_controller.rb"]


def test_stage_workspace_changes_excludes_swift_build_artifacts(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "Package.swift").write_text("// swift-tools-version: 5.9\n", encoding="utf-8")
    (workspace / "Sources" / "TodoCLI").mkdir(parents=True)
    (workspace / "Sources" / "TodoCLI" / "main.swift").write_text('print("old")\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    (workspace / "Sources" / "TodoCLI" / "main.swift").write_text('print("new")\n', encoding="utf-8")
    (workspace / ".build" / "debug").mkdir(parents=True)
    (workspace / ".build" / "debug" / "cache.pcm").write_text("generated\n", encoding="utf-8")
    (workspace / ".swiftpm").mkdir()
    (workspace / ".swiftpm" / "workspace-state.json").write_text("{}\n", encoding="utf-8")

    changed = _stage_workspace_changes(
        workspace,
        issue_title="Fix Swift CLI output",
        issue_body="Required code outputs:\n- Sources/TodoCLI/main.swift\n",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("Sources/TodoCLI/main.swift",),
            tool_policy="repo_only",
            validation_profile="code_change",
            language="swift",
        ),
        language="swift",
    )

    assert changed is True
    assert _changed_paths(workspace) == ["Sources/TodoCLI/main.swift"]


def test_stage_workspace_changes_excludes_supabase_runtime_temp_artifacts(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    target = workspace / "e2e-apps" / "prosper-chat" / "supabase" / "migrations" / "0001_init.sql"
    target.parent.mkdir(parents=True)
    target.write_text("-- old\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    target.write_text("-- new\n", encoding="utf-8")
    temp_file = workspace / "e2e-apps" / "prosper-chat" / "supabase" / ".temp" / "cli-latest"
    temp_file.parent.mkdir(parents=True)
    temp_file.write_text("generated\n", encoding="utf-8")
    branch_file = workspace / "e2e-apps" / "prosper-chat" / "supabase" / ".branches" / "_current_branch"
    branch_file.parent.mkdir(parents=True)
    branch_file.write_text("generated\n", encoding="utf-8")

    changed = _stage_workspace_changes(
        workspace,
        issue_title="Prosper chat DB migration fix",
        issue_body=(
            "Required code outputs:\n"
            "- e2e-apps/prosper-chat/supabase/migrations/0001_init.sql\n\n"
            "Validation:\n"
            "- cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh db\n"
        ),
        task_spec=HealerTaskSpec(
            task_kind="edit",
            output_mode="patch",
            output_targets=("e2e-apps/prosper-chat/supabase/migrations/0001_init.sql",),
            tool_policy="repo_only",
            validation_profile="code_change",
            language="node",
            execution_root="e2e-apps/prosper-chat",
        ),
        language="node",
    )

    assert changed is True
    assert _changed_paths(workspace) == ["e2e-apps/prosper-chat/supabase/migrations/0001_init.sql"]


def test_run_test_gates_marks_local_skipped_when_toolchain_unavailable(monkeypatch):
    from flow_healer.language_strategies import LanguageStrategy

    no_local_strategy = LanguageStrategy(
        language="node",
        framework="generic",
        docker_image="node:20-slim",
        docker_install_cmd="npm install",
        docker_test_cmd=["npm", "test"],
        local_test_cmd=[],
        supports_targeted_paths=False,
    )

    def fake_docker(workspace: Path, command: list[str], timeout_seconds: int, **kwargs):
        return {"exit_code": 0, "output_tail": "docker ok", "gate_status": "passed", "gate_reason": ""}

    monkeypatch.setattr("flow_healer.healer_runner._run_tests_in_docker", fake_docker)

    summary = _run_test_gates(
        Path("."),
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_then_docker",
        resolved_execution=ResolvedExecution(
            language_detected="node",
            language_effective="node",
            execution_root="",
            execution_root_source="repo",
            execution_path=Path("."),
            strategy=no_local_strategy,
        ),
        local_gate_policy="auto",
    )

    assert summary["local_full_status"] == "skipped"
    assert summary["local_full_reason"] == "no_local_test_command"
    assert summary["docker_full_status"] == "passed"
    assert summary["failed_tests"] == 0


def test_run_test_gates_fails_local_when_policy_force_and_tool_missing():
    strategy = get_strategy("python", test_command="definitely-missing-test-binary")

    summary = _run_test_gates(
        Path("."),
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_only",
        resolved_execution=ResolvedExecution(
            language_detected="python",
            language_effective="python",
            execution_root="",
            execution_root_source="repo",
            execution_path=Path("."),
            strategy=strategy,
        ),
        local_gate_policy="force",
    )

    assert summary["local_full_status"] == "failed"
    assert summary["local_full_reason"] == "tool_missing"
    assert summary["failed_tests"] == 1


def test_run_test_gates_fails_local_only_when_gate_is_skipped():
    from flow_healer.language_strategies import LanguageStrategy

    no_local_strategy = LanguageStrategy(
        language="node",
        framework="generic",
        docker_image="node:20-slim",
        docker_install_cmd="npm install",
        docker_test_cmd=["npm", "test"],
        local_test_cmd=[],
        supports_targeted_paths=False,
    )

    summary = _run_test_gates(
        Path("."),
        targeted_tests=[],
        timeout_seconds=30,
        mode="local_only",
        resolved_execution=ResolvedExecution(
            language_detected="node",
            language_effective="node",
            execution_root="",
            execution_root_source="repo",
            execution_path=Path("."),
            strategy=no_local_strategy,
        ),
        local_gate_policy="auto",
    )

    assert summary["local_full_status"] == "failed"
    assert summary["local_full_reason"] == "no_local_test_command"
    assert summary["failed_tests"] == 1


def test_run_connector_turn_uses_detailed_result_when_supported():
    class _DetailedConnector(_RetryConnector):
        def run_turn_detailed(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> ConnectorTurnResult:
            self.turns.append((thread_id, prompt))
            return ConnectorTurnResult(
                output_text="final answer",
                final_answer_present=True,
                commentary_tail="streaming commentary",
            )

    connector = _DetailedConnector(outputs=[])
    result = _run_connector_turn(connector, "thread-1", "prompt", timeout_seconds=60)
    assert result.output_text == "final answer"
    assert result.final_answer_present is True
    assert result.commentary_tail == "streaming commentary"


class _RetryConnector:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.exec_failover_outputs: list[str] = []
        self.reset_calls: list[str] = []
        self.turns: list[tuple[str, str]] = []
        self.exec_failover_turns: list[tuple[str, str]] = []
        self.timeouts: list[int | None] = []
        self.snapshot: dict[str, object] = {}

    def get_or_create_thread(self, sender: str) -> str:
        return sender

    def reset_thread(self, sender: str) -> str:
        self.reset_calls.append(sender)
        return sender

    def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
        self.turns.append((thread_id, prompt))
        self.timeouts.append(timeout_seconds)
        return self.outputs.pop(0)

    def run_turn_exec_failover(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
        self.exec_failover_turns.append((thread_id, prompt))
        self.timeouts.append(timeout_seconds)
        if not self.exec_failover_outputs:
            return ""
        return self.exec_failover_outputs.pop(0)

    def ensure_started(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def health_snapshot(self) -> dict[str, object]:
        return dict(self.snapshot)


class _WorkspaceEditingConnector(_RetryConnector):
    def __init__(self, workspace: Path, outputs):
        super().__init__(outputs)
        self.workspace = workspace

    def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
        self.turns.append((thread_id, prompt))
        (self.workspace / "docs").mkdir(exist_ok=True)
        (self.workspace / "docs" / "create-plan-docs.md").write_text("Synthesized plan\n", encoding="utf-8")
        return self.outputs.pop(0)


def _init_git_repo(workspace: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Flow Healer Test"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "flow-healer@example.com"], cwd=workspace, check=True, capture_output=True, text=True)


def test_run_attempt_retries_after_patch_apply_failure(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Flow Healer Test"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "flow-healer@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    bad_patch = "```diff\ndiff --git a/demo.py b/demo.py\n@@ broken\n```\n"
    good_patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([bad_patch, good_patch])
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    monkeypatch.setattr(
        "flow_healer.healer_runner._run_test_gates",
        lambda *args, **kwargs: {
            "mode": "local_only",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        },
    )

    result = runner.run_attempt(
        issue_id="123",
        issue_title="Fix demo",
        issue_body="Repair demo.py",
        task_spec=compile_task_spec(issue_title="Fix demo", issue_body="Repair demo.py"),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert connector.reset_calls == ["healer:123"]
    assert len(connector.turns) == 2
    assert "Previous proposer output was unusable." in connector.turns[1][1]


def test_run_attempt_serialized_patch_mode_reclassifies_narrative_only_no_patch(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    connector = _RetryConnector(["Updated demo.py to fix the add helper and ran tests."])
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    runner.max_code_proposer_retries = 0

    result = runner.run_attempt(
        issue_id="123a",
        issue_title="Fix demo",
        issue_body="Repair demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "no_workspace_change:narrative_only"
    assert result.failure_fingerprint == "execution_contract|serialized_patch|no_workspace_change:narrative_only"
    assert "status summary" in result.failure_reason.lower()


def test_run_attempt_serialized_patch_mode_marks_final_answer_without_edits_as_narrative_only(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    class _DetailedNoopConnector(_RetryConnector):
        def run_turn_detailed(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> ConnectorTurnResult:
            self.turns.append((thread_id, prompt))
            return ConnectorTurnResult(
                output_text="I fixed demo.py and verified the requested behavior.",
                final_answer_present=True,
            )

    runner = HealerRunner(_DetailedNoopConnector(outputs=[]), timeout_seconds=30, test_gate_mode="local_only")
    runner.max_code_proposer_retries = 0

    result = runner.run_attempt(
        issue_id="123b",
        issue_title="Fix demo",
        issue_body="Repair demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "no_workspace_change:narrative_only"
    assert result.failure_fingerprint == "execution_contract|serialized_patch|no_workspace_change:narrative_only"
    assert "final answer" in result.failure_reason.lower()


def test_run_attempt_serialized_patch_mode_marks_commentary_only_turn_as_connector_noop(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    class _DetailedCommentaryConnector(_RetryConnector):
        def run_turn_detailed(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> ConnectorTurnResult:
            self.turns.append((thread_id, prompt))
            return ConnectorTurnResult(
                output_text="",
                commentary_tail="Thinking through the requested fix now.",
            )

    runner = HealerRunner(_DetailedCommentaryConnector(outputs=[]), timeout_seconds=30, test_gate_mode="local_only")
    runner.max_code_proposer_retries = 0

    result = runner.run_attempt(
        issue_id="123c",
        issue_title="Fix demo",
        issue_body="Repair demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "no_workspace_change:connector_noop"
    assert result.failure_fingerprint == "execution_contract|serialized_patch|no_workspace_change:connector_noop"
    assert "commentary mode" in result.failure_reason.lower()


def test_run_attempt_phase2_noop_replay_pack(tmp_path):
    def _make_workspace(name: str) -> Path:
        workspace = tmp_path / name
        workspace.mkdir()
        _init_git_repo(workspace)
        (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)
        return workspace

    def _run_case(issue_id: str, workspace: Path, connector) -> object:
        runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
        runner.max_code_proposer_retries = 0
        return runner.run_attempt(
            issue_id=issue_id,
            issue_title="Fix demo",
            issue_body="Repair demo.py",
            task_spec=HealerTaskSpec(
                task_kind="fix",
                output_mode="patch",
                output_targets=("demo.py",),
                tool_policy="repo_only",
                validation_profile="code_change",
            ),
            workspace=workspace,
            max_diff_files=5,
            max_diff_lines=20,
            max_failed_tests_allowed=0,
            targeted_tests=[],
        )

    narrative_result = _run_case(
        "phase2-noop-1",
        _make_workspace("narrative"),
        _RetryConnector(["Updated demo.py to fix the add helper and ran tests."]),
    )

    final_answer_workspace = _make_workspace("final-answer")

    class _DetailedNoopConnector(_RetryConnector):
        def run_turn_detailed(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> ConnectorTurnResult:
            self.turns.append((thread_id, prompt))
            return ConnectorTurnResult(
                output_text="I fixed demo.py and verified the requested behavior.",
                final_answer_present=True,
            )

    final_answer_result = _run_case("phase2-noop-2", final_answer_workspace, _DetailedNoopConnector(outputs=[]))

    commentary_workspace = _make_workspace("commentary")

    class _DetailedCommentaryConnector(_RetryConnector):
        def run_turn_detailed(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> ConnectorTurnResult:
            self.turns.append((thread_id, prompt))
            return ConnectorTurnResult(
                output_text="",
                commentary_tail="Thinking through the requested fix now.",
            )

    commentary_result = _run_case("phase2-noop-3", commentary_workspace, _DetailedCommentaryConnector(outputs=[]))

    runtime_workspace = _make_workspace("runtime-artifacts")

    class _GeneratedArtifactConnector(_RetryConnector):
        def __init__(self, workspace_path: Path):
            super().__init__(["Updated runtime artifacts only."])
            self.workspace_path = workspace_path

        def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
            self.turns.append((thread_id, prompt))
            cache_dir = self.workspace_path / ".pytest_cache"
            cache_dir.mkdir(exist_ok=True)
            (cache_dir / "v").write_text("cached\n", encoding="utf-8")
            return self.outputs.pop(0)

    app_server_cls = type("CodexAppServerConnector", (_GeneratedArtifactConnector,), {})
    runtime_artifact_result = _run_case("phase2-noop-4", runtime_workspace, app_server_cls(runtime_workspace))

    replay_results = {
        "narrative_summary": narrative_result.failure_class,
        "final_answer_only": final_answer_result.failure_class,
        "commentary_only": commentary_result.failure_class,
        "runtime_artifacts_only": runtime_artifact_result.failure_class,
    }

    assert replay_results == {
        "narrative_summary": "no_workspace_change:narrative_only",
        "final_answer_only": "no_workspace_change:narrative_only",
        "commentary_only": "no_workspace_change:connector_noop",
        "runtime_artifacts_only": "no_workspace_change:staging_filtered_all",
    }


def test_run_attempt_uses_longer_turn_timeout_for_code_change(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Flow Healer Test"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "flow-healer@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([patch])
    runner = HealerRunner(connector, timeout_seconds=300, test_gate_mode="local_only")

    monkeypatch.setattr(
        "flow_healer.healer_runner._run_test_gates",
        lambda *args, **kwargs: {
            "mode": "local_only",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        },
    )

    result = runner.run_attempt(
        issue_id="1241",
        issue_title="Fix addition bug",
        issue_body="Fix demo.py and pass tests.",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert connector.timeouts == [900]


def test_run_attempt_rejects_regular_diff_with_extra_paths(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (workspace / "other.py").write_text("VALUE = 0\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "diff --git a/other.py b/other.py\n"
        "--- a/other.py\n"
        "+++ b/other.py\n"
        "@@ -1 +1 @@\n"
        "-VALUE = 0\n"
        "+VALUE = 1\n"
        "```\n"
    )
    connector = _RetryConnector([patch])
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    monkeypatch.setattr(
        "flow_healer.healer_runner._run_test_gates",
        lambda *args, **kwargs: {
            "mode": "local_only",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        },
    )

    result = runner.run_attempt(
        issue_id="1242",
        issue_title="Fix addition bug",
        issue_body="Fix demo.py and pass tests.",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=40,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "scope_violation"
    assert "other.py" in result.failure_reason


def test_run_attempt_recleans_regenerated_lockfile_contamination(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")
    (workspace / "demo.js").write_text("export const add = (a, b) => a - b;\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    patch = (
        "```diff\n"
        "diff --git a/demo.js b/demo.js\n"
        "--- a/demo.js\n"
        "+++ b/demo.js\n"
        "@@ -1 +1 @@\n"
        "-export const add = (a, b) => a - b;\n"
        "+export const add = (a, b) => a + b;\n"
        "```\n"
    )
    connector = _RetryConnector([patch])
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_then_docker")

    # First contamination appears before validation.
    (workspace / "package-lock.json").write_text('{"lockfileVersion":3}\n', encoding="utf-8")

    validate_calls = {"count": 0}

    def fake_validate_workspace(*args, **kwargs):
        # Simulate test tooling regenerating lockfile contamination on each validation pass.
        validate_calls["count"] += 1
        (workspace / "package-lock.json").write_text(
            f'{{"lockfileVersion":3,"regenerated":{validate_calls["count"]}}}\n',
            encoding="utf-8",
        )
        return {
            "mode": "local_then_docker",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        }

    monkeypatch.setattr(runner, "validate_workspace", fake_validate_workspace)

    result = runner.run_attempt(
        issue_id="lockfix-1",
        issue_title="Fix demo add",
        issue_body="Update demo.js only.",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
            language="node",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert result.failure_class == ""
    assert result.workspace_status["cleanup_cycles_used"] >= 1
    assert "package-lock.json" in result.workspace_status["cleaned_paths"]
    assert validate_calls["count"] >= 2
    assert "package-lock.json" not in _changed_paths(workspace)


def test_run_attempt_recleans_regenerated_ruby_lockfile_contamination(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "Gemfile").write_text("source 'https://rubygems.org'\n", encoding="utf-8")
    (workspace / "app.rb").write_text("def add(a, b)\n  a - b\nend\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    patch = (
        "```diff\n"
        "diff --git a/app.rb b/app.rb\n"
        "--- a/app.rb\n"
        "+++ b/app.rb\n"
        "@@ -1,3 +1,3 @@\n"
        " def add(a, b)\n"
        "-  a - b\n"
        "+  a + b\n"
        " end\n"
        "```\n"
    )
    connector = _RetryConnector([patch])
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_then_docker")

    (workspace / "Gemfile.lock").write_text("GEM\n  specs:\n", encoding="utf-8")
    validate_calls = {"count": 0}

    def fake_validate_workspace(*args, **kwargs):
        validate_calls["count"] += 1
        (workspace / "Gemfile.lock").write_text(
            f"GEM\n  specs:\n    regenerated_{validate_calls['count']}\n",
            encoding="utf-8",
        )
        return {
            "mode": "local_then_docker",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        }

    monkeypatch.setattr(runner, "validate_workspace", fake_validate_workspace)

    result = runner.run_attempt(
        issue_id="lockfix-ruby-1",
        issue_title="Fix ruby add helper",
        issue_body="Update app.rb only.",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
            language="ruby",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert result.failure_class == ""
    assert result.workspace_status["cleanup_cycles_used"] >= 1
    assert "Gemfile.lock" in result.workspace_status["cleaned_paths"]
    assert validate_calls["count"] >= 2
    assert "Gemfile.lock" not in _changed_paths(workspace)


def test_run_attempt_embeds_input_context_file_contents_in_prompt(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Flow Healer Test"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "flow-healer@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    (workspace / "skills-suggestions.md").write_text("Implement connector-debug routing.\n", encoding="utf-8")
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([patch])
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    monkeypatch.setattr(
        "flow_healer.healer_runner._run_test_gates",
        lambda *args, **kwargs: {
            "mode": "local_only",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        },
    )

    result = runner.run_attempt(
        issue_id="1250",
        issue_title="Implement skills-suggestions.md",
        issue_body="Use skills-suggestions.md as input spec only and make code changes.",
        task_spec=HealerTaskSpec(
            task_kind="build",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
            input_context_paths=("skills-suggestions.md",),
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    prompt = connector.turns[0][1]
    assert "### Input Context Files" in prompt
    assert "#### skills-suggestions.md" in prompt
    assert "Implement connector-debug routing." in prompt


def test_run_attempt_enriches_connector_runtime_failures_with_health_snapshot(tmp_path):
    connector = _RetryConnector(["ConnectorRuntimeError: Codex CLI timed out after 300s."])
    connector.snapshot = {
        "resolved_command": "/opt/homebrew/bin/codex",
        "last_runtime_error_kind": "timeout",
        "last_runtime_stdout_tail": "partial proposer output",
        "last_runtime_stderr_tail": "mcp startup hung",
        "last_health_error": "Codex CLI timed out after 300s.",
    }
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    workspace = tmp_path / "repo"
    workspace.mkdir()

    result = runner.run_attempt(
        issue_id="1241",
        issue_title="Fix addition bug",
        issue_body="Fix demo.py and pass tests.",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "connector_runtime_error"
    assert "resolved_command=/opt/homebrew/bin/codex" in result.failure_reason
    assert "runtime_kind=timeout" in result.failure_reason
    assert "stdout_tail=partial proposer output" in result.failure_reason
    assert "stderr_tail=mcp startup hung" in result.failure_reason


def test_run_attempt_rejects_docs_only_diff_for_code_change_task(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Flow Healer Test"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "flow-healer@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    docs_patch = (
        "```diff\n"
        "diff --git a/docs/notes.md b/docs/notes.md\n"
        "new file mode 100644\n"
        "index 0000000..1234567\n"
        "--- /dev/null\n"
        "+++ b/docs/notes.md\n"
        "@@ -0,0 +1,2 @@\n"
        "+# Notes\n"
        "+This is docs-only output.\n"
        "```\n"
    )
    connector = _RetryConnector([docs_patch, docs_patch, docs_patch, docs_patch])
    runner = HealerRunner(connector, timeout_seconds=60, test_gate_mode="local_only")

    result = runner.run_attempt(
        issue_id="1242",
        issue_title="Implement feature",
        issue_body="Implement a feature with real code updates.",
        task_spec=HealerTaskSpec(
            task_kind="build",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "no_code_diff"


def test_run_attempt_skips_test_gate_for_artifact_only_issue(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Flow Healer Test"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "flow-healer@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    (workspace / "docs").mkdir()
    (workspace / "docs" / "research-note.md").write_text("Old summary\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    patch = (
        "```diff\n"
        "diff --git a/docs/research-note.md b/docs/research-note.md\n"
        "--- a/docs/research-note.md\n"
        "+++ b/docs/research-note.md\n"
        "@@ -1 +1 @@\n"
        "-Old summary\n"
        "+Research summary\n"
        "```\n"
    )
    connector = _RetryConnector([patch])
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_then_docker")

    called = False

    def fake_run_test_gates(*args, **kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr("flow_healer.healer_runner._run_test_gates", fake_run_test_gates)

    result = runner.run_attempt(
        issue_id="124",
        issue_title="Research note",
        issue_body="Research best practices and write docs/research-note.md",
        task_spec=HealerTaskSpec(
            task_kind="research",
            output_mode="patch",
            output_targets=("docs/research-note.md",),
            tool_policy="repo_plus_web",
            validation_profile="artifact_only",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert called is False
    assert result.test_summary["mode"] == "skipped_artifact_only"


def test_run_attempt_includes_task_contract_in_prompt(tmp_path):
    connector = _RetryConnector(["not a patch", "still not a patch", "again not a patch"])
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    workspace = tmp_path / "repo"
    workspace.mkdir()

    result = runner.run_attempt(
        issue_id="125",
        issue_title="Research note",
        issue_body="Research the topic and create docs/research-note.md",
        task_spec=HealerTaskSpec(
            task_kind="research",
            output_mode="patch",
            output_targets=("docs/research-note.md",),
            tool_policy="repo_plus_web",
            validation_profile="artifact_only",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    prompt = connector.turns[0][1]
    assert "Task kind: research" in prompt
    assert "Output targets: docs/research-note.md" in prompt
    assert "Input context: (none)" in prompt
    assert "Use web browsing only when repo context is insufficient" in prompt


def test_run_attempt_marks_input_specs_as_context_in_prompt(tmp_path):
    connector = _RetryConnector(["not a patch"] * 5)
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    workspace = tmp_path / "repo"
    workspace.mkdir()

    result = runner.run_attempt(
        issue_id="126",
        issue_title="Implement skills-suggestions.md",
        issue_body="Use skills-suggestions.md as input spec only and do not make doc-only edits.",
        task_spec=compile_task_spec(
            issue_title="Implement skills-suggestions.md",
            issue_body="Use skills-suggestions.md as input spec only and do not make doc-only edits.",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    prompt = connector.turns[0][1]
    assert "Input context: skills-suggestions.md" in prompt
    assert "Treat these files as input-only context, not output targets: skills-suggestions.md." in prompt
    assert "Success criteria: Stage a production-safe code patch" in prompt
    assert "Default next action: Implement the smallest safe repo patch" in prompt


def test_run_attempt_accepts_direct_workspace_edits_without_diff(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Flow Healer Test"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "flow-healer@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    connector = _WorkspaceEditingConnector(workspace, ["Created the requested artifact."])
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    monkeypatch.setattr(
        "flow_healer.healer_runner._run_test_gates",
        lambda *args, **kwargs: {
            "mode": "local_only",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        },
    )

    result = runner.run_attempt(
        issue_id="126",
        issue_title="Create plan docs",
        issue_body="Research the topic and create plan docs.",
        task_spec=HealerTaskSpec(
            task_kind="research",
            output_mode="patch",
            output_targets=("docs/create-plan-docs.md",),
            tool_policy="repo_plus_web",
            validation_profile="artifact_only",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert result.diff_paths == ["docs/create-plan-docs.md"]


def test_run_attempt_materializes_code_file_from_path_fence_for_code_change(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Flow Healer Test"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "flow-healer@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    (workspace / "src").mkdir()
    (workspace / "src" / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    connector = _RetryConnector(
        [
            "I could not emit a diff fence. Final file content:\n\n"
            "```python path=src/calc.py\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "```\n",
        ]
    )
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    monkeypatch.setattr(
        "flow_healer.healer_runner._run_test_gates",
        lambda *args, **kwargs: {
            "mode": "local_only",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        },
    )

    result = runner.run_attempt(
        issue_id="136",
        issue_title="Fix calc",
        issue_body="Fix src/calc.py and keep tests passing.",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert "src/calc.py" in result.diff_paths
    content = (workspace / "src" / "calc.py").read_text(encoding="utf-8")
    assert "return a + b" in content


def test_run_attempt_ignores_input_context_path_in_path_fenced_output(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Flow Healer Test"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "flow-healer@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    (workspace / "src").mkdir()
    (workspace / "src" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (workspace / "skills-suggestions.md").write_text("input spec\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    connector = _RetryConnector(
        [
            "```markdown path=skills-suggestions.md\n"
            "this should not be written\n"
            "```\n"
            "```python path=src/module.py\n"
            "VALUE = 2\n"
            "```\n",
        ]
    )
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    monkeypatch.setattr(
        "flow_healer.healer_runner._run_test_gates",
        lambda *args, **kwargs: {
            "mode": "local_only",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        },
    )

    result = runner.run_attempt(
        issue_id="137",
        issue_title="Implement upgrades",
        issue_body="Use skills-suggestions.md as input spec only.",
        task_spec=HealerTaskSpec(
            task_kind="build",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
            input_context_paths=("skills-suggestions.md",),
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert "src/module.py" in result.diff_paths
    assert "skills-suggestions.md" not in result.diff_paths
    input_context = (workspace / "skills-suggestions.md").read_text(encoding="utf-8")
    assert input_context == "input spec\n"


def test_run_attempt_materializes_artifact_from_plain_prose(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Flow Healer Test"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "flow-healer@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    connector = _RetryConnector(
        [
            "# Research Summary\n\n- Key finding one\n- Key finding two\n",
        ]
    )
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    result = runner.run_attempt(
        issue_id="128",
        issue_title="Research topic",
        issue_body="Research this topic and make docs/research-summary.md",
        task_spec=HealerTaskSpec(
            task_kind="research",
            output_mode="patch",
            output_targets=("docs/research-summary.md",),
            tool_policy="repo_plus_web",
            validation_profile="artifact_only",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=300,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert result.diff_paths == ["docs/research-summary.md"]
    content = (workspace / "docs" / "research-summary.md").read_text(encoding="utf-8")
    assert "# Research Summary" in content


def test_run_attempt_materializes_artifact_from_markdown_fence(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Flow Healer Test"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "flow-healer@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    connector = _RetryConnector(
        [
            "I could not apply a diff, so here is the final file content.\n\n"
            "```markdown path=docs/plan.md\n"
            "# Plan\n\n"
            "Ship the preflight gate first.\n"
            "```\n",
        ]
    )
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    result = runner.run_attempt(
        issue_id="129",
        issue_title="Create plan",
        issue_body="Research and create docs/plan.md",
        task_spec=HealerTaskSpec(
            task_kind="docs",
            output_mode="patch",
            output_targets=("docs/plan.md",),
            tool_policy="repo_plus_web",
            validation_profile="artifact_only",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=300,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert result.diff_paths == ["docs/plan.md"]
    content = (workspace / "docs" / "plan.md").read_text(encoding="utf-8")
    assert content.startswith("# Plan")


def test_run_attempt_recovers_artifact_from_malformed_diff(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Flow Healer Test"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "flow-healer@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    malformed_patch = (
        "```diff\n"
        "diff --git a/docs/recovered.md b/docs/recovered.md\n"
        "new file mode 100644\n"
        "index 0000000..1234567\n"
        "--- /dev/null\n"
        "+++ b/docs/recovered.md\n"
        "@@ -0,0 +1,3 @@\n"
        "+# Recovered\n"
        "+\n"
        "+This content should survive malformed patch output.\n"
        "THIS_IS_NOT_VALID_PATCH_SYNTAX\n"
        "```\n"
    )
    connector = _RetryConnector([malformed_patch])
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    result = runner.run_attempt(
        issue_id="130",
        issue_title="Recover malformed diff",
        issue_body="Create docs/recovered.md with research notes",
        task_spec=HealerTaskSpec(
            task_kind="research",
            output_mode="patch",
            output_targets=("docs/recovered.md",),
            tool_policy="repo_plus_web",
            validation_profile="artifact_only",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=300,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert result.diff_paths == ["docs/recovered.md"]
    content = (workspace / "docs" / "recovered.md").read_text(encoding="utf-8")
    assert content.startswith("# Recovered")
    assert "survive malformed patch output" in content


def test_looks_like_unified_diff_accepts_rename_only_patch() -> None:
    patch = (
        "diff --git a/docs/old.md b/docs/new.md\n"
        "similarity index 100%\n"
        "rename from docs/old.md\n"
        "rename to docs/new.md\n"
    )

    assert _looks_like_unified_diff(patch) is True


def test_run_attempt_retries_when_artifact_output_is_status_summary(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Flow Healer Test"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "flow-healer@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    connector = _RetryConnector(
        [
            (
                "Updated [docs/plan.md](/tmp/docs/plan.md) with a research-backed plan.\n\n"
                "I did not run tests, since this was an `artifact_only` research-doc update."
            ),
            (
                "```markdown path=docs/plan.md\n"
                "# Plan\n\n"
                "1. Improve prompt contracts.\n"
                "2. Add artifact retries.\n"
                "3. Keep verifier deterministic for artifact-only flows.\n"
                "```\n"
            ),
        ]
    )
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    result = runner.run_attempt(
        issue_id="131",
        issue_title="Create plan",
        issue_body="Research and create docs/plan.md",
        task_spec=HealerTaskSpec(
            task_kind="research",
            output_mode="patch",
            output_targets=("docs/plan.md",),
            tool_policy="repo_plus_web",
            validation_profile="artifact_only",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=300,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert len(connector.turns) == 2
    content = (workspace / "docs" / "plan.md").read_text(encoding="utf-8")
    assert content.startswith("# Plan")
    assert "I did not run tests" not in content


def test_run_attempt_classifies_connector_unavailable_error(tmp_path):
    connector = _RetryConnector(
        [
            "ConnectorUnavailable: Unable to resolve Codex command 'codex'. Set service.connector_command to an absolute path.",
        ]
    )
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    workspace = tmp_path / "repo"
    workspace.mkdir()

    result = runner.run_attempt(
        issue_id="127",
        issue_title="Create plan docs",
        issue_body="Create docs/create-plan-docs.md",
        task_spec=HealerTaskSpec(
            task_kind="docs",
            output_mode="patch",
            output_targets=("docs/create-plan-docs.md",),
            tool_policy="repo_only",
            validation_profile="artifact_only",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "connector_unavailable"
    assert "Unable to resolve Codex command" in result.failure_reason
    assert len(connector.turns) == 1


def test_run_attempt_fails_fast_for_connector_runtime_errors(tmp_path):
    connector = _RetryConnector(
        [
            "ConnectorRuntimeError: Codex CLI timed out after 300s. stderr tail: mcp startup hung stdout tail: still working",
        ]
    )
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    workspace = tmp_path / "repo"
    workspace.mkdir()

    result = runner.run_attempt(
        issue_id="132",
        issue_title="Implement feature",
        issue_body="Implement the requested repo changes.",
        task_spec=HealerTaskSpec(
            task_kind="build",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "connector_runtime_error"
    assert "timed out after 300s" in result.failure_reason
    assert len(connector.turns) == 1


def test_run_attempt_retries_empty_diff_with_targeted_guidance(tmp_path):
    connector = _RetryConnector(["```diff\n```", "not a patch", "not a patch", "not a patch"])
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    workspace = tmp_path / "repo"
    workspace.mkdir()

    result = runner.run_attempt(
        issue_id="133",
        issue_title="Implement feature",
        issue_body="Implement the requested repo changes.",
        task_spec=HealerTaskSpec(
            task_kind="build",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert "empty diff fenced block" in connector.turns[1][1]


def test_run_attempt_retries_malformed_diff_before_git_apply(tmp_path):
    connector = _RetryConnector(
        [
            "```diff\n--- a/demo.py\n+++ b/demo.py\n+print('missing hunk header')\n```",
            "not a patch",
            "not a patch",
            "not a patch",
        ]
    )
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    workspace = tmp_path / "repo"
    workspace.mkdir()

    result = runner.run_attempt(
        issue_id="134",
        issue_title="Implement feature",
        issue_body="Implement the requested repo changes.",
        task_spec=HealerTaskSpec(
            task_kind="build",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert "invalid patch syntax" in connector.turns[1][1]


def test_apply_unified_diff_patch_returns_error_when_workspace_is_missing(tmp_path):
    missing_workspace = tmp_path / "missing-worktree"

    applied, error = _apply_unified_diff_patch(
        workspace=missing_workspace,
        patch="diff --git a/demo.py b/demo.py\n--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-a\n+b\n",
        timeout_seconds=30,
    )

    assert applied is False
    assert "workspace missing before git apply" in error
    assert not missing_workspace.exists()


def test_run_attempt_accepts_expanded_issue_language(tmp_path):
    connector = _RetryConnector(["not a patch"] * 5)
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    resolved = runner.resolve_execution(
        workspace=tmp_path,
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
            language="swift",
        ),
    )

    assert resolved.language_effective == "swift"
    assert resolved.strategy.local_test_cmd == ["swift", "test"]


def test_resolve_execution_accepts_expanded_language_override(tmp_path):
    runner = HealerRunner(connector=None, timeout_seconds=30, language="ruby")  # type: ignore[arg-type]

    resolved = runner.resolve_execution(
        workspace=tmp_path,
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
    )

    assert resolved.language_effective == "ruby"
    assert resolved.strategy.local_test_cmd == ["bundle", "exec", "rspec"]


def test_run_attempt_includes_path_fenced_fallback_guidance(tmp_path):
    connector = _RetryConnector(["not a patch"] * 5)
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    workspace = tmp_path / "repo"
    workspace.mkdir()

    result = runner.run_attempt(
        issue_id="201",
        issue_title="Fix calc",
        issue_body="Fix calc.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    prompt = connector.turns[0][1]
    assert "path-fenced blocks" in prompt


def test_run_attempt_prompt_uses_clear_section_order_for_code_tasks(tmp_path):
    connector = _RetryConnector(["not a patch"] * 5)
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    workspace = tmp_path / "repo"
    workspace.mkdir()

    runner.run_attempt(
        issue_id="202",
        issue_title="Fix calc",
        issue_body="Fix calc.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("calc.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            language="python",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    prompt = connector.turns[0][1]
    assert prompt.index("### Role And Trusted Inputs") < prompt.index("### Task Context")
    assert prompt.index("### Task Context") < prompt.index("### Task Contract")
    assert prompt.index("### Task Contract") < prompt.index("### Execution Rules")
    assert prompt.index("### Execution Rules") < prompt.index("### Output Rules")
    assert prompt.index("### Output Rules") < prompt.index("### Completion Criteria")


def test_run_attempt_prompt_includes_context_stop_rules_for_code_tasks(tmp_path):
    connector = _RetryConnector(["not a patch"] * 5)
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    workspace = tmp_path / "repo"
    workspace.mkdir()

    runner.run_attempt(
        issue_id="203",
        issue_title="Fix handler",
        issue_body="Fix handler.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("handler.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    prompt = connector.turns[0][1]
    assert "Inspect only enough files" in prompt
    assert "Prefer acting once the likely root cause is confirmed" in prompt
    assert "do not return exploratory summaries" in prompt
    assert "patch them in place" in prompt
    assert "Do not recreate surrounding scaffolding" in prompt


def test_run_attempt_prompt_keeps_web_guidance_only_for_research_tasks(tmp_path):
    connector = _RetryConnector(["not a patch"] * 3)
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    workspace = tmp_path / "repo"
    workspace.mkdir()

    runner.run_attempt(
        issue_id="204",
        issue_title="Research deps",
        issue_body="Research best ways to configure this package.",
        task_spec=HealerTaskSpec(
            task_kind="research",
            output_mode="patch",
            output_targets=("docs/research.md",),
            tool_policy="repo_plus_web",
            validation_profile="artifact_only",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    research_prompt = connector.turns[0][1]
    assert "Use web browsing only when repo context is insufficient" in research_prompt

    connector_two = _RetryConnector(["not a patch"] * 5)
    runner_two = HealerRunner(connector_two, timeout_seconds=30, test_gate_mode="local_only")
    runner_two.run_attempt(
        issue_id="205",
        issue_title="Fix handler",
        issue_body="Fix handler.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("handler.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert "Use web browsing only when repo context is insufficient" not in connector_two.turns[0][1]


def test_build_retry_prompt_includes_tests_failed_guidance():
    prompt = _build_retry_prompt(
        base_prompt="Fix the bug",
        failure_class="tests_failed",
        failure_reason="pytest exited with code 1",
    )
    assert "test output" in prompt.lower()
    assert "assertion or import" in prompt.lower()


def test_build_retry_prompt_includes_verifier_failed_guidance():
    prompt = _build_retry_prompt(
        base_prompt="Fix the bug",
        failure_class="verifier_failed",
        failure_reason="AI verifier rejected the fix",
    )
    assert "verifier rejected" in prompt.lower()
    assert "root cause" in prompt.lower()
    assert "do not rebuild sandbox scaffolding" in prompt.lower()


def test_build_retry_prompt_keeps_sandbox_validation_issue_scoped():
    prompt = _build_retry_prompt(
        base_prompt="Fix the bug",
        failure_class="tests_failed",
        failure_reason="sandbox test failed",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("e2e-apps/python-fastapi/app/api.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            execution_root="e2e-apps/python-fastapi",
        ),
    )
    lowered = prompt.lower()
    assert "sandbox-local test output" in lowered
    assert "do not add or claim repo-root pytest/full-suite validation" in lowered


def test_build_retry_prompt_prefers_workspace_edits_when_requested():
    prompt = _build_retry_prompt(
        base_prompt="Fix the bug",
        failure_class="no_workspace_change",
        failure_reason="Agent returned a summary only.",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("src/demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        prefer_workspace_edits=True,
        allow_exact_target_file_fallback=True,
        continue_same_thread=True,
    )

    lowered = prompt.lower()
    assert "edit files directly in the managed workspace" in lowered
    assert "do not return a diff" in lowered
    assert "concise summary" in lowered
    assert "current thread and workspace" in lowered
    assert "path-fenced blocks" in lowered


def test_build_retry_prompt_includes_artifact_body_fallback_when_requested():
    prompt = _build_retry_prompt(
        base_prompt="Write the requested doc",
        failure_class="no_workspace_change",
        failure_reason="Agent returned a summary only.",
        task_spec=HealerTaskSpec(
            task_kind="docs",
            output_mode="patch",
            output_targets=("docs/runtime-reset-smoke.md",),
            tool_policy="repo_only",
            validation_profile="artifact_only",
        ),
        prefer_workspace_edits=True,
        allow_artifact_body_fallback=True,
        continue_same_thread=True,
    )

    lowered = prompt.lower()
    assert "exact final artifact body" in lowered
    assert "current thread and workspace" in lowered


def test_build_proposer_prompt_prefers_workspace_edits_for_app_server_tasks(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()

    prompt = _build_proposer_prompt(
        issue_id="910",
        issue_title="Fix demo",
        issue_body="Repair src/demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("src/demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        learned_context="",
        feedback_context="",
        language_hint="",
        prefer_workspace_edits=True,
    )

    lowered = prompt.lower()
    assert "edit files in place" in lowered
    assert "brief operator summary" in lowered
    assert "do not serialize a diff as the normal success path" in lowered


def test_task_execution_instructions_keep_sandbox_validation_local():
    instructions = _task_execution_instructions(
        HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("e2e-apps/python-fastapi/app/service.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            execution_root="e2e-apps/python-fastapi",
        )
    )
    lowered = instructions.lower()
    assert "sandbox-scoped" in lowered
    assert "exact allowlist for edits" in lowered
    assert "do not suggest or claim repo-root pytest/full-suite validation" in lowered


def test_run_attempt_app_server_code_task_accepts_diff_fallback_output(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    app_server_cls = type("CodexAppServerConnector", (_RetryConnector,), {})
    patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = app_server_cls([patch])
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    runner.max_code_proposer_retries = 0
    monkeypatch.setattr(
        "flow_healer.healer_runner._run_test_gates",
        lambda *args, **kwargs: {
            "mode": "local_only",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        },
    )

    result = runner.run_attempt(
        issue_id="911",
        issue_title="Fix demo",
        issue_body="Repair demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert result.failure_class == ""
    assert (workspace / "demo.py").read_text(encoding="utf-8").strip().endswith("return a + b")


def test_run_attempt_app_server_code_task_recovers_with_exact_target_fallback(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    app_server_cls = type("CodexAppServerConnector", (_RetryConnector,), {})
    connector = app_server_cls(
        [
            "Updated [demo.py](/tmp/demo.py) to fix the add helper and ran tests.",
            "```python path=demo.py\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "```\n",
        ]
    )
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    monkeypatch.setattr(
        "flow_healer.healer_runner._run_test_gates",
        lambda *args, **kwargs: {
            "mode": "local_only",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        },
    )

    result = runner.run_attempt(
        issue_id="914",
        issue_title="Fix demo",
        issue_body="Repair demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert connector.reset_calls == ["healer:914"]
    assert len(connector.turns) == 2
    assert "complete final file bodies in path-fenced blocks" in connector.turns[1][1].lower()


def test_run_attempt_app_server_code_task_rejects_fallback_with_extra_paths(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    app_server_cls = type("CodexAppServerConnector", (_RetryConnector,), {})
    connector = app_server_cls(
        [
            "```python path=demo.py\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "```\n"
            "```python path=other.py\n"
            "VALUE = 1\n"
            "```\n",
        ]
    )
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    runner.max_code_proposer_retries = 0

    result = runner.run_attempt(
        issue_id="915",
        issue_title="Fix demo",
        issue_body="Repair demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "no_workspace_change:artifact_not_materialized"
    assert "unnamed paths" in result.failure_reason


def test_run_attempt_app_server_code_task_rejects_narrative_only_path_fenced_body(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    app_server_cls = type("CodexAppServerConnector", (_RetryConnector,), {})
    connector = app_server_cls(
        [
            "```python path=demo.py\n"
            "Updated demo.py to fix the add helper and ran tests.\n"
            "```\n",
        ]
    )
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    runner.max_code_proposer_retries = 0

    result = runner.run_attempt(
        issue_id="915aa",
        issue_title="Fix demo",
        issue_body="Repair demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "no_workspace_change:artifact_not_materialized"
    assert "not a full file body" in result.failure_reason
    assert (workspace / "demo.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a - b\n"


def test_run_attempt_app_server_code_task_marks_staging_filtered_all_when_only_runtime_artifacts_change(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    class _GeneratedArtifactConnector(_RetryConnector):
        def __init__(self, workspace_path: Path):
            super().__init__(["Updated runtime artifacts only."])
            self.workspace_path = workspace_path

        def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
            self.turns.append((thread_id, prompt))
            cache_dir = self.workspace_path / ".pytest_cache"
            cache_dir.mkdir(exist_ok=True)
            (cache_dir / "v").write_text("cached\n", encoding="utf-8")
            return self.outputs.pop(0)

    app_server_cls = type("CodexAppServerConnector", (_GeneratedArtifactConnector,), {})
    connector = app_server_cls(workspace)
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    runner.max_code_proposer_retries = 0

    result = runner.run_attempt(
        issue_id="915a",
        issue_title="Fix demo",
        issue_body="Repair demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "no_workspace_change:staging_filtered_all"
    assert ".pytest_cache" in result.failure_reason


def test_run_attempt_app_server_no_workspace_change_runs_bounded_recovery_and_failover(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    app_server_cls = type("CodexAppServerConnector", (_RetryConnector,), {})
    connector = app_server_cls(
        [
            "Updated [demo.py](/tmp/demo.py) and this should work now.",
            "Updated [demo.py](/tmp/demo.py) and this should work now.",
            "Updated [demo.py](/tmp/demo.py) and this should work now.",
        ]
    )
    connector.exec_failover_outputs = ["Updated [demo.py](/tmp/demo.py) and this should work now."]
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    result = runner.run_attempt(
        issue_id="915b",
        issue_title="Fix demo",
        issue_body="Repair demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "no_workspace_change:exec_failover_failed"
    assert result.failure_fingerprint.startswith("execution_contract|workspace_edit|no_workspace_change:")
    assert len(connector.turns) == 3
    assert len(connector.exec_failover_turns) == 1
    assert "this retry is strict" in connector.turns[1][1].lower()
    assert result.workspace_status["app_server_forced_serialized_recovery_attempted"] is True
    assert result.workspace_status["app_server_forced_serialized_recovery_succeeded"] is False
    assert result.workspace_status["app_server_exec_failover_attempted"] is True
    assert result.workspace_status["app_server_exec_failover_succeeded"] is False


def test_run_attempt_app_server_no_workspace_change_recovers_with_forced_serialized_pass(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    app_server_cls = type("CodexAppServerConnector", (_RetryConnector,), {})
    connector = app_server_cls(
        [
            "Updated [demo.py](/tmp/demo.py) and this should work now.",
            "Updated [demo.py](/tmp/demo.py) and this should work now.",
            patch,
        ]
    )
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    monkeypatch.setattr(
        "flow_healer.healer_runner._run_test_gates",
        lambda *args, **kwargs: {
            "mode": "local_only",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        },
    )

    result = runner.run_attempt(
        issue_id="915c-recovery",
        issue_title="Fix demo",
        issue_body="Repair demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert len(connector.turns) == 3
    assert len(connector.exec_failover_turns) == 0
    assert result.workspace_status["app_server_forced_serialized_recovery_attempted"] is True
    assert result.workspace_status["app_server_forced_serialized_recovery_succeeded"] is True
    assert result.workspace_status["app_server_exec_failover_attempted"] is False
    assert result.workspace_status["app_server_exec_failover_succeeded"] is False


def test_run_attempt_app_server_no_workspace_change_recovers_with_exec_failover(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    app_server_cls = type("CodexAppServerConnector", (_RetryConnector,), {})
    connector = app_server_cls(
        [
            "Updated [demo.py](/tmp/demo.py) and this should work now.",
            "Updated [demo.py](/tmp/demo.py) and this should work now.",
            "Updated [demo.py](/tmp/demo.py) and this should work now.",
        ]
    )
    connector.exec_failover_outputs = [patch]
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    monkeypatch.setattr(
        "flow_healer.healer_runner._run_test_gates",
        lambda *args, **kwargs: {
            "mode": "local_only",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        },
    )

    result = runner.run_attempt(
        issue_id="915c-failover",
        issue_title="Fix demo",
        issue_body="Repair demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert len(connector.turns) == 3
    assert len(connector.exec_failover_turns) == 1
    assert result.workspace_status["app_server_forced_serialized_recovery_attempted"] is True
    assert result.workspace_status["app_server_forced_serialized_recovery_succeeded"] is False
    assert result.workspace_status["app_server_exec_failover_attempted"] is True
    assert result.workspace_status["app_server_exec_failover_succeeded"] is True


def test_run_attempt_app_server_always_mode_accepts_lenient_named_target_fallback(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    app_server_cls = type("CodexAppServerConnector", (_RetryConnector,), {})
    connector = app_server_cls(
        [
            "```python path=demo.py\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "```\n"
            "```python path=other.py\n"
            "VALUE = 1\n"
            "```\n",
        ]
    )
    runner = HealerRunner(
        connector,
        timeout_seconds=30,
        test_gate_mode="local_only",
        completion_artifact_mode="always",
    )

    monkeypatch.setattr(
        "flow_healer.healer_runner._run_test_gates",
        lambda *args, **kwargs: {
            "mode": "local_only",
            "failed_tests": 0,
            "targeted_tests": [],
            "local_full_exit_code": 0,
            "local_full_output_tail": "ok",
        },
    )

    result = runner.run_attempt(
        issue_id="915c",
        issue_title="Fix demo",
        issue_body="Repair demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert (workspace / "other.py").exists() is False
    assert result.workspace_status["completion_artifact_parser_mode"] == "lenient"
    assert result.workspace_status["completion_artifact_parser_confidence"] == 0.65


def test_build_proposer_prompt_prefers_workspace_edits_for_app_server_docs_tasks(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()

    prompt = _build_proposer_prompt(
        issue_id="912",
        issue_title="Write runtime note",
        issue_body="Create docs/runtime-reset-smoke.md",
        task_spec=HealerTaskSpec(
            task_kind="docs",
            output_mode="patch",
            output_targets=("docs/runtime-reset-smoke.md",),
            tool_policy="repo_only",
            validation_profile="artifact_only",
        ),
        workspace=workspace,
        learned_context="",
        feedback_context="",
        language_hint="",
        prefer_workspace_edits=True,
    )

    lowered = prompt.lower()
    assert "edit files in place" in lowered
    assert "end with a brief operator summary" in lowered


def test_build_proposer_prompt_adds_native_multi_agent_guidance_for_code_tasks(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()

    prompt = _build_proposer_prompt(
        issue_id="915",
        issue_title="Fix runtime routing",
        issue_body="Fix src/flow_healer/service.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("src/flow_healer/service.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        workspace=workspace,
        learned_context="",
        feedback_context="",
        language_hint="",
        prefer_workspace_edits=False,
        native_multi_agent_profile="initial",
        native_multi_agent_max_subagents=3,
    )

    lowered = prompt.lower()
    assert "codex native multi-agent" in lowered
    assert "spawn at most 3 read-only subagents" in lowered
    assert "explorer" in lowered
    assert "test_forensics" in lowered
    assert "patch_critic" in lowered
    assert "only the parent session may produce the final patch" in lowered


def test_build_proposer_prompt_skips_native_multi_agent_guidance_for_docs_tasks(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()

    prompt = _build_proposer_prompt(
        issue_id="916",
        issue_title="Write runtime note",
        issue_body="Create docs/runtime-reset-smoke.md",
        task_spec=HealerTaskSpec(
            task_kind="docs",
            output_mode="patch",
            output_targets=("docs/runtime-reset-smoke.md",),
            tool_policy="repo_only",
            validation_profile="artifact_only",
        ),
        workspace=workspace,
        learned_context="",
        feedback_context="",
        language_hint="",
        prefer_workspace_edits=False,
        native_multi_agent_profile="initial",
        native_multi_agent_max_subagents=3,
    )

    assert "codex native multi-agent" not in prompt.lower()


def test_build_retry_prompt_adds_native_multi_agent_recovery_guidance():
    prompt = _build_retry_prompt(
        base_prompt="Base prompt",
        failure_class="tests_failed",
        failure_reason="AssertionError",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("src/demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        prefer_workspace_edits=False,
        native_multi_agent_profile="recovery",
        native_multi_agent_max_subagents=3,
    )

    lowered = prompt.lower()
    assert "native multi-agent recovery attempt" in lowered
    assert "spawn at most 3 read-only subagents" in lowered
    assert "synthesize their findings, then produce the final patch in the parent session" in lowered


def test_run_attempt_app_server_artifact_task_materializes_output_without_diff(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)

    app_server_cls = type("CodexAppServerConnector", (_RetryConnector,), {})
    connector = app_server_cls(
        [
            "# Runtime Reset Smoke\n\nThis file verifies the Flow Healer issue-to-PR path after a runtime reset.\n",
        ]
    )
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    result = runner.run_attempt(
        issue_id="913",
        issue_title="Write runtime note",
        issue_body="Create docs/runtime-reset-smoke.md",
        task_spec=HealerTaskSpec(
            task_kind="docs",
            output_mode="patch",
            output_targets=("docs/runtime-reset-smoke.md",),
            tool_policy="repo_only",
            validation_profile="artifact_only",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert "docs/runtime-reset-smoke.md" in result.diff_paths
    created = (workspace / "docs" / "runtime-reset-smoke.md").read_text(encoding="utf-8")
    assert "issue-to-pr path" in created.lower()


def test_run_attempt_app_server_artifact_task_retries_same_thread_on_summary_only_output(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)

    app_server_cls = type("CodexAppServerConnector", (_RetryConnector,), {})
    connector = app_server_cls(
        [
            "Updated [docs/runtime-reset-smoke.md](/tmp/runtime-reset-smoke.md) with the requested note. I did not run tests.",
            "# Runtime Reset Smoke\n\nRecovered by returning exact artifact content on retry.\n",
        ]
    )
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    result = runner.run_attempt(
        issue_id="917",
        issue_title="Write runtime note",
        issue_body="Create docs/runtime-reset-smoke.md",
        task_spec=HealerTaskSpec(
            task_kind="docs",
            output_mode="patch",
            output_targets=("docs/runtime-reset-smoke.md",),
            tool_policy="repo_only",
            validation_profile="artifact_only",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert connector.reset_calls == ["healer:917"]
    assert len(connector.turns) == 2
    assert "exact final artifact body" in connector.turns[1][1].lower()


def test_run_attempt_materializes_completion_artifact_for_artifact_task_no_targets(tmp_path):
    """Pure prose with no explicit artifact target should still produce run output."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)

    prose_output = (
        "After investigating the authentication module, I found three root causes: "
        "missing token refresh logic, incorrect session timeout defaults, and a race "
        "condition in the concurrent login handler. Detailed findings follow..."
    )
    connector = _RetryConnector([prose_output])
    runner = HealerRunner(connector=connector, timeout_seconds=30)
    runner.max_proposer_retries = 0
    runner.max_code_proposer_retries = 0
    runner.max_artifact_proposer_retries = 0
    result = runner.run_attempt(
        issue_id="999",
        issue_title="Research login issues",
        issue_body="Investigate and report on login issues",
        task_spec=HealerTaskSpec(
            task_kind="research",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_plus_web",
            validation_profile="artifact_only",
        ),
        learned_context="",
        feedback_context="",
        workspace=workspace,
        max_diff_files=10,
        max_diff_lines=500,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )
    artifact = workspace / "docs" / "healer-runs" / "999-research-login-issues.md"
    assert result.success is True, f"Expected success via completion artifact, got failure_class={result.failure_class}"
    assert artifact.exists(), "Completion artifact should have been written"
    content = artifact.read_text(encoding="utf-8")
    assert "Issue #999" in content
    assert "Research login issues" in content


def test_run_attempt_completion_artifact_not_triggered_for_structured_output(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    diff_output = "```diff\n```\nThe fix would change x from 1 to 2."
    connector = _RetryConnector([diff_output])
    runner = HealerRunner(connector=connector, timeout_seconds=30)
    runner.max_proposer_retries = 0
    runner.max_code_proposer_retries = 0
    runner.max_artifact_proposer_retries = 0
    result = runner.run_attempt(
        issue_id="888",
        issue_title="Fix x",
        issue_body="Set x=2",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        learned_context="",
        feedback_context="",
        workspace=workspace,
        max_diff_files=10,
        max_diff_lines=500,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )
    assert result.success is False
    artifact = workspace / "docs" / "healer-runs" / "888-fix-x.md"
    assert not artifact.exists(), "Completion artifact should NOT be written for structured diff output"


class _FakeAppHarnessSession:
    def __init__(self, profile):
        self.profile = profile
        self.stop_calls = 0

    def stop(self) -> int:
        self.stop_calls += 1
        return 0


class _FakeAppHarness:
    def __init__(self):
        self.boot_calls = []
        self.sessions: list[_FakeAppHarnessSession] = []

    def boot(self, profile):
        self.boot_calls.append(profile)
        session = _FakeAppHarnessSession(profile)
        self.sessions.append(session)
        return (
            AppHarnessBootResult(
                profile=profile,
                pid=4321,
                readiness_url=profile.readiness_url,
                ready_via_url=bool(profile.readiness_url),
                ready_via_log=bool(profile.readiness_log_text),
                startup_seconds=0.25,
                output_tail="APP READY",
            ),
            session,
        )


class _ArtifactWritingAppHarnessSession(_FakeAppHarnessSession):
    def __init__(self, profile, *, artifact_path: Path):
        super().__init__(profile)
        self.artifact_path = artifact_path

    def stop(self) -> int:
        result = super().stop()
        self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_path.write_text("runtime shutdown noise\n", encoding="utf-8")
        return result


class _ArtifactWritingAppHarness(_FakeAppHarness):
    def __init__(self, *, artifact_path: Path):
        super().__init__()
        self.artifact_path = artifact_path

    def boot(self, profile):
        self.boot_calls.append(profile)
        session = _ArtifactWritingAppHarnessSession(profile, artifact_path=self.artifact_path)
        self.sessions.append(session)
        return (
            AppHarnessBootResult(
                profile=profile,
                pid=4321,
                readiness_url=profile.readiness_url,
                ready_via_url=bool(profile.readiness_url),
                ready_via_log=bool(profile.readiness_log_text),
                startup_seconds=0.25,
                output_tail="APP READY",
            ),
            session,
        )


class _FakeBrowserHarness:
    def __init__(self, results, *, runtime_available=True, runtime_reason=""):
        self.results = list(results)
        self.runtime_available = runtime_available
        self.runtime_reason = runtime_reason
        self.calls: list[dict[str, object]] = []

    def check_runtime_available(self):
        return self.runtime_available, self.runtime_reason

    def capture_journey(
        self,
        *,
        profile,
        entry_url: str,
        repro_steps,
        artifact_root: Path,
        phase: str,
        expect_failure: bool,
        storage_state_path: str = "",
    ):
        self.calls.append(
            {
                "profile": profile,
                "entry_url": entry_url,
                "repro_steps": tuple(repro_steps),
                "artifact_root": artifact_root,
                "phase": phase,
                "expect_failure": expect_failure,
                "storage_state_path": storage_state_path,
            }
        )
        result = self.results.pop(0)
        for path in (
            result.screenshot_path,
            result.video_path,
            result.console_log_path,
            result.network_log_path,
        ):
            if not path:
                continue
            artifact_path = Path(path)
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(f"{phase} artifact\n", encoding="utf-8")
        return result


class _ExplodingBrowserHarness(_FakeBrowserHarness):
    def __init__(self, *, message: str, phase: str = "resolution"):
        super().__init__([])
        self.message = message
        self.phase = phase

    def capture_journey(
        self,
        *,
        profile,
        entry_url: str,
        repro_steps,
        artifact_root: Path,
        phase: str,
        expect_failure: bool,
        storage_state_path: str = "",
    ):
        self.calls.append(
            {
                "profile": profile,
                "entry_url": entry_url,
                "repro_steps": tuple(repro_steps),
                "artifact_root": artifact_root,
                "phase": phase,
                "expect_failure": expect_failure,
                "storage_state_path": storage_state_path,
            }
        )
        if phase == self.phase:
            raise RuntimeError(self.message)
        return super().capture_journey(
            profile=profile,
            entry_url=entry_url,
            repro_steps=repro_steps,
            artifact_root=artifact_root,
            phase=phase,
            expect_failure=expect_failure,
            storage_state_path=storage_state_path,
        )


def test_run_attempt_boots_selected_app_runtime_profile_and_stops_session(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    good_patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([good_patch])
    app_harness = _FakeAppHarness()
    runner = HealerRunner(
        connector,
        timeout_seconds=30,
        test_gate_mode="local_only",
        default_runtime_profile="web",
        app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/health",
                "working_directory": ".",
            }
        ],
        app_harness=app_harness,  # type: ignore[arg-type]
    )
    runner.validate_workspace = lambda *args, **kwargs: {"failed_tests": 0, "mode": "local_only"}  # type: ignore[method-assign]

    result = runner.run_attempt(
        issue_id="app-101",
        issue_title="Fix runtime-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            entry_url="http://127.0.0.1:3000",
            runtime_profile="web",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert len(app_harness.boot_calls) == 1
    profile = app_harness.boot_calls[0]
    assert profile.name == "web"
    assert profile.command == ("npm", "run", "dev")
    assert profile.cwd == workspace
    assert result.workspace_status["app_runtime"]["status"] == "ready"
    assert result.test_summary["runtime_summary"]["app_harness"]["entry_url"] == "http://127.0.0.1:3000"
    assert result.test_summary["runtime_summary"]["app_harness"]["process"] == {
        "pid": 4321,
        "profile": "web",
        "command": ["npm", "run", "dev"],
        "cwd": str(workspace),
    }
    assert app_harness.sessions[0].stop_calls == 1


def test_run_attempt_classifies_app_runtime_boot_failures(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    good_patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([good_patch])

    class _FailingAppHarness:
        def boot(self, profile):
            raise RuntimeError("dev server failed to boot")

    runner = HealerRunner(
        connector,
        timeout_seconds=30,
        test_gate_mode="local_only",
        default_runtime_profile="web",
        app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/health",
                "working_directory": ".",
            }
        ],
        app_harness=_FailingAppHarness(),  # type: ignore[arg-type]
    )

    result = runner.run_attempt(
        issue_id="app-101b",
        issue_title="Fix runtime-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            entry_url="http://127.0.0.1:3000",
            runtime_profile="web",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "app_runtime_boot_failed"
    assert result.test_summary["browser_failure_family"] == "runtime_boot"


def test_run_attempt_fails_when_app_runtime_profile_is_missing(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    good_patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([good_patch])
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")

    result = runner.run_attempt(
        issue_id="app-102",
        issue_title="Fix runtime-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            runtime_profile="web",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "app_runtime_profile_missing"
    assert result.workspace_status["app_runtime"]["status"] == "unconfigured"
    assert "not configured" in result.failure_reason.lower()


def test_run_attempt_stops_app_runtime_session_when_validation_fails(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    good_patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([good_patch])
    app_harness = _FakeAppHarness()
    runner = HealerRunner(
        connector,
        timeout_seconds=30,
        test_gate_mode="local_only",
        default_runtime_profile="web",
        app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/health",
                "working_directory": ".",
            }
        ],
        app_harness=app_harness,  # type: ignore[arg-type]
    )
    runner.validate_workspace = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "failed_tests": 1,
        "failure_class": "tests_failed",
        "failure_reason": "Validation failed in app flow.",
    }

    result = runner.run_attempt(
        issue_id="app-103",
        issue_title="Fix runtime-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            runtime_profile="web",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "tests_failed"
    assert app_harness.sessions[0].stop_calls == 1


def test_run_attempt_does_not_require_runtime_for_artifact_requirements_alone(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    good_patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([good_patch])
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    runner.validate_workspace = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "failed_tests": 0,
        "promotion_state": "promotion_ready",
        "phase_states": {"promotion_ready": True, "merge_blocked": False},
    }

    result = runner.run_attempt(
        issue_id="app-104",
        issue_title="Fix runtime-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            artifact_requirements=("failure_video", "resolution_video"),
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert "app_runtime" not in result.workspace_status


def test_run_attempt_detects_shutdown_generated_artifacts_from_app_runtime(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    good_patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([good_patch])
    app_harness = _ArtifactWritingAppHarness(artifact_path=workspace / "dist" / "runtime.log")
    runner = HealerRunner(
        connector,
        timeout_seconds=30,
        test_gate_mode="local_only",
        default_runtime_profile="web",
        app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/health",
                "working_directory": ".",
            }
        ],
        app_harness=app_harness,  # type: ignore[arg-type]
        auto_clean_generated_artifacts=False,
    )
    runner.validate_workspace = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "failed_tests": 0,
        "promotion_state": "promotion_ready",
        "phase_states": {"promotion_ready": True, "merge_blocked": False},
    }

    result = runner.run_attempt(
        issue_id="app-105",
        issue_title="Fix runtime-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            runtime_profile="web",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "generated_artifact_contamination"
    assert "dist/runtime.log" in result.failure_reason


def test_run_attempt_captures_failure_and_resolution_browser_evidence(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    good_patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([good_patch])
    app_harness = _FakeAppHarness()
    browser_harness = _FakeBrowserHarness(
        [
            BrowserJourneyResult(
                phase="failure",
                passed=False,
                expected_failure_observed=True,
                final_url="http://127.0.0.1:3000/",
                failure_step="expect_text Broken widget",
                error="Expected text missing",
                screenshot_path=str(tmp_path / "before.png"),
                video_path=str(tmp_path / "before.webm"),
                console_log_path=str(tmp_path / "before-console.log"),
                network_log_path=str(tmp_path / "before-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "failed"},),
            ),
            BrowserJourneyResult(
                phase="failure-replay",
                passed=False,
                expected_failure_observed=True,
                final_url="http://127.0.0.1:3000/",
                failure_step="expect_text Broken widget",
                error="Expected text missing",
                screenshot_path=str(tmp_path / "before-replay.png"),
                video_path=str(tmp_path / "before-replay.webm"),
                console_log_path=str(tmp_path / "before-replay-console.log"),
                network_log_path=str(tmp_path / "before-replay-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "failed"},),
            ),
            BrowserJourneyResult(
                phase="resolution",
                passed=True,
                expected_failure_observed=False,
                final_url="http://127.0.0.1:3000/",
                screenshot_path=str(tmp_path / "after.png"),
                video_path=str(tmp_path / "after.webm"),
                console_log_path=str(tmp_path / "after-console.log"),
                network_log_path=str(tmp_path / "after-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "passed"},),
            ),
        ]
    )
    runner = HealerRunner(
        connector,
        timeout_seconds=30,
        test_gate_mode="local_only",
        default_runtime_profile="web",
        app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/",
                "working_directory": ".",
                "browser": "chromium",
                "headless": True,
            }
        ],
        app_harness=app_harness,  # type: ignore[arg-type]
        browser_harness=browser_harness,  # type: ignore[arg-type]
    )
    runner.validate_workspace = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "failed_tests": 0,
        "promotion_state": "promotion_ready",
        "phase_states": {"promotion_ready": True, "merge_blocked": False},
    }

    result = runner.run_attempt(
        issue_id="app-201",
        issue_title="Fix browser-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            entry_url="http://127.0.0.1:3000/",
            runtime_profile="web",
            repro_steps=("goto /", "expect_text Broken widget"),
            artifact_requirements=("failure_video", "resolution_video"),
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert [call["phase"] for call in browser_harness.calls] == ["failure", "failure-replay", "resolution"]
    assert browser_harness.calls[0]["profile"].browser == "chromium"
    assert browser_harness.calls[0]["profile"].headless is True
    assert result.test_summary["browser_evidence_required"] is True
    assert result.test_summary["artifact_proof_ready"] is True
    assert result.test_summary["promotion_transitions"] == [
        "failure_artifacts_captured",
        "resolution_artifacts_captured",
        "local_validated",
    ]
    assert result.test_summary["artifact_bundle"]["failure_artifacts"]["video_path"].endswith("before.webm")
    assert result.test_summary["artifact_bundle"]["resolution_artifacts"]["video_path"].endswith("after.webm")
    assert result.test_summary["artifact_links"][0]["label"] == "failure_screenshot"


def test_run_attempt_uses_fixture_driver_for_prepare_and_auth_state(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    driver_log = tmp_path / "fixture-driver.log"
    driver_script = workspace / "fixture_driver.py"
    driver_script.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "from pathlib import Path",
                "",
                "log_path = Path(sys.argv[1])",
                "action = sys.argv[2]",
                "fixture = sys.argv[3]",
                "log_path.parent.mkdir(parents=True, exist_ok=True)",
                "log_path.open('a', encoding='utf-8').write(f'{action}:{fixture}\\n')",
                "if action == 'auth-state':",
                "    output_path = Path(sys.argv[4])",
                "    output_path.parent.mkdir(parents=True, exist_ok=True)",
                "    output_path.write_text(json.dumps({'cookies': [], 'origins': []}), encoding='utf-8')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    good_patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([good_patch])
    app_harness = _FakeAppHarness()
    browser_harness = _FakeBrowserHarness(
        [
            BrowserJourneyResult(
                phase="failure",
                passed=False,
                expected_failure_observed=True,
                final_url="http://127.0.0.1:3000/",
                failure_step="expect_text Broken widget",
                error="Expected text missing",
                screenshot_path=str(tmp_path / "before.png"),
                video_path=str(tmp_path / "before.webm"),
                console_log_path=str(tmp_path / "before-console.log"),
                network_log_path=str(tmp_path / "before-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "failed"},),
            ),
            BrowserJourneyResult(
                phase="failure-replay",
                passed=False,
                expected_failure_observed=True,
                final_url="http://127.0.0.1:3000/",
                failure_step="expect_text Broken widget",
                error="Expected text missing",
                screenshot_path=str(tmp_path / "before-replay.png"),
                video_path=str(tmp_path / "before-replay.webm"),
                console_log_path=str(tmp_path / "before-replay-console.log"),
                network_log_path=str(tmp_path / "before-replay-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "failed"},),
            ),
            BrowserJourneyResult(
                phase="resolution",
                passed=True,
                expected_failure_observed=False,
                final_url="http://127.0.0.1:3000/",
                screenshot_path=str(tmp_path / "after.png"),
                video_path=str(tmp_path / "after.webm"),
                console_log_path=str(tmp_path / "after-console.log"),
                network_log_path=str(tmp_path / "after-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "passed"},),
            ),
        ]
    )
    runner = HealerRunner(
        connector,
        timeout_seconds=30,
        test_gate_mode="local_only",
        default_runtime_profile="web",
        app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/",
                "working_directory": ".",
                "browser": "chromium",
                "headless": True,
                "fixture_driver_command": [sys.executable, str(driver_script), str(driver_log)],
            }
        ],
        app_harness=app_harness,  # type: ignore[arg-type]
        browser_harness=browser_harness,  # type: ignore[arg-type]
    )
    runner.validate_workspace = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "failed_tests": 0,
        "promotion_state": "promotion_ready",
        "phase_states": {"promotion_ready": True, "merge_blocked": False},
    }

    result = runner.run_attempt(
        issue_id="app-201a",
        issue_title="Fix browser-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            entry_url="http://127.0.0.1:3000/",
            runtime_profile="web",
            fixture_profile="seeded-admin",
            repro_steps=("goto /", "expect_text Broken widget"),
            artifact_requirements=("failure_video", "resolution_video"),
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert driver_log.read_text(encoding="utf-8").splitlines() == [
        "prepare:seeded-admin",
        "auth-state:seeded-admin",
        "prepare:seeded-admin",
        "auth-state:seeded-admin",
    ]
    assert all(call["storage_state_path"] for call in browser_harness.calls)


def test_run_attempt_fails_when_browser_bug_is_not_reproduced_before_fix(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    connector = _RetryConnector(["not used"])
    app_harness = _FakeAppHarness()
    browser_harness = _FakeBrowserHarness(
        [
            BrowserJourneyResult(
                phase="failure",
                passed=True,
                expected_failure_observed=False,
                final_url="http://127.0.0.1:3000/",
                screenshot_path=str(tmp_path / "before.png"),
                video_path=str(tmp_path / "before.webm"),
                console_log_path=str(tmp_path / "before-console.log"),
                network_log_path=str(tmp_path / "before-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "passed"},),
            )
        ]
    )
    runner = HealerRunner(
        connector,
        timeout_seconds=30,
        test_gate_mode="local_only",
        default_runtime_profile="web",
        app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/",
                "working_directory": ".",
                "browser": "chromium",
                "headless": True,
            }
        ],
        app_harness=app_harness,  # type: ignore[arg-type]
        browser_harness=browser_harness,  # type: ignore[arg-type]
    )

    result = runner.run_attempt(
        issue_id="app-202",
        issue_title="Fix browser-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            entry_url="http://127.0.0.1:3000/",
            runtime_profile="web",
            repro_steps=("goto /", "expect_text Broken widget"),
            artifact_requirements=("failure_video", "resolution_video"),
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "browser_repro_failed"


def test_run_attempt_flags_flaky_browser_repro_before_mutation(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    connector = _RetryConnector(["not used"])
    app_harness = _FakeAppHarness()
    browser_harness = _FakeBrowserHarness(
        [
            BrowserJourneyResult(
                phase="failure",
                passed=False,
                expected_failure_observed=True,
                final_url="http://127.0.0.1:3000/",
                failure_step="expect_text Broken widget",
                error="Expected text missing",
                screenshot_path=str(tmp_path / "before.png"),
                video_path=str(tmp_path / "before.webm"),
                console_log_path=str(tmp_path / "before-console.log"),
                network_log_path=str(tmp_path / "before-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "failed"},),
            ),
            BrowserJourneyResult(
                phase="failure-replay",
                passed=True,
                expected_failure_observed=False,
                final_url="http://127.0.0.1:3000/",
                screenshot_path=str(tmp_path / "replay.png"),
                video_path=str(tmp_path / "replay.webm"),
                console_log_path=str(tmp_path / "replay-console.log"),
                network_log_path=str(tmp_path / "replay-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "passed"},),
            ),
        ]
    )
    runner = HealerRunner(
        connector,
        timeout_seconds=30,
        test_gate_mode="local_only",
        default_runtime_profile="web",
        app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/",
                "working_directory": ".",
                "browser": "chromium",
                "headless": True,
            }
        ],
        app_harness=app_harness,  # type: ignore[arg-type]
        browser_harness=browser_harness,  # type: ignore[arg-type]
    )

    result = runner.run_attempt(
        issue_id="app-202b",
        issue_title="Fix flaky browser-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            entry_url="http://127.0.0.1:3000/",
            runtime_profile="web",
            repro_steps=("goto /", "expect_text Broken widget"),
            artifact_requirements=("failure_video", "resolution_video"),
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "browser_repro_failed"
    assert [call["phase"] for call in browser_harness.calls] == ["failure", "failure-replay"]
    assert result.test_summary["flaky_repro"]["checked"] is True
    assert result.test_summary["flaky_repro"]["reproduced_on_first_run"] is True
    assert result.test_summary["flaky_repro"]["reproduced_on_replay"] is False


def test_run_attempt_allows_missing_failure_video_when_screenshot_exists(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    good_patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([good_patch])
    app_harness = _FakeAppHarness()
    browser_harness = _FakeBrowserHarness(
        [
            BrowserJourneyResult(
                phase="failure",
                passed=False,
                expected_failure_observed=True,
                final_url="http://127.0.0.1:3000/",
                failure_step="expect_text Broken widget",
                screenshot_path=str(tmp_path / "before.png"),
                video_path="",
                console_log_path=str(tmp_path / "before-console.log"),
                network_log_path=str(tmp_path / "before-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "failed"},),
            ),
            BrowserJourneyResult(
                phase="failure-replay",
                passed=False,
                expected_failure_observed=True,
                final_url="http://127.0.0.1:3000/",
                failure_step="expect_text Broken widget",
                screenshot_path=str(tmp_path / "before-replay.png"),
                video_path="",
                console_log_path=str(tmp_path / "before-replay-console.log"),
                network_log_path=str(tmp_path / "before-replay-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "failed"},),
            ),
            BrowserJourneyResult(
                phase="resolution",
                passed=True,
                expected_failure_observed=False,
                final_url="http://127.0.0.1:3000/",
                screenshot_path=str(tmp_path / "after.png"),
                video_path=str(tmp_path / "after.webm"),
                console_log_path=str(tmp_path / "after-console.log"),
                network_log_path=str(tmp_path / "after-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "passed"},),
            ),
        ]
    )
    runner = HealerRunner(
        connector,
        timeout_seconds=30,
        test_gate_mode="local_only",
        default_runtime_profile="web",
        app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/",
                "working_directory": ".",
                "browser": "chromium",
                "headless": True,
            }
        ],
        app_harness=app_harness,  # type: ignore[arg-type]
        browser_harness=browser_harness,  # type: ignore[arg-type]
    )
    runner.validate_workspace = lambda *args, **kwargs: {"failed_tests": 0}  # type: ignore[method-assign]

    result = runner.run_attempt(
        issue_id="app-203",
        issue_title="Fix browser-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            entry_url="http://127.0.0.1:3000/",
            runtime_profile="web",
            repro_steps=("goto /", "expect_text Broken widget"),
            artifact_requirements=("failure_video", "resolution_video"),
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert "video_path" not in result.test_summary["artifact_bundle"]["failure_artifacts"]
    assert all(link["label"] != "failure_video" for link in result.test_summary["artifact_links"])


def test_run_attempt_fails_when_resolution_browser_evidence_is_incomplete(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    good_patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([good_patch])
    app_harness = _FakeAppHarness()
    browser_harness = _FakeBrowserHarness(
        [
            BrowserJourneyResult(
                phase="failure",
                passed=False,
                expected_failure_observed=True,
                final_url="http://127.0.0.1:3000/",
                failure_step="expect_text Broken widget",
                screenshot_path=str(tmp_path / "before.png"),
                video_path=str(tmp_path / "before.webm"),
                console_log_path=str(tmp_path / "before-console.log"),
                network_log_path=str(tmp_path / "before-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "failed"},),
            ),
            BrowserJourneyResult(
                phase="failure-replay",
                passed=False,
                expected_failure_observed=True,
                final_url="http://127.0.0.1:3000/",
                failure_step="expect_text Broken widget",
                screenshot_path=str(tmp_path / "before-replay.png"),
                video_path=str(tmp_path / "before-replay.webm"),
                console_log_path=str(tmp_path / "before-replay-console.log"),
                network_log_path=str(tmp_path / "before-replay-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "failed"},),
            ),
            BrowserJourneyResult(
                phase="resolution",
                passed=True,
                expected_failure_observed=False,
                final_url="http://127.0.0.1:3000/",
                screenshot_path="",
                video_path=str(tmp_path / "after.webm"),
                console_log_path=str(tmp_path / "after-console.log"),
                network_log_path=str(tmp_path / "after-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "passed"},),
            ),
        ]
    )
    runner = HealerRunner(
        connector,
        timeout_seconds=30,
        test_gate_mode="local_only",
        default_runtime_profile="web",
        app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/",
                "working_directory": ".",
                "browser": "chromium",
                "headless": True,
            }
        ],
        app_harness=app_harness,  # type: ignore[arg-type]
        browser_harness=browser_harness,  # type: ignore[arg-type]
    )
    runner.validate_workspace = lambda *args, **kwargs: {"failed_tests": 0}  # type: ignore[method-assign]

    result = runner.run_attempt(
        issue_id="app-204",
        issue_title="Fix browser-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            entry_url="http://127.0.0.1:3000/",
            runtime_profile="web",
            repro_steps=("goto /", "expect_text Broken widget"),
            artifact_requirements=("failure_video", "resolution_video"),
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "artifacts_missing"
    assert result.test_summary["browser_failure_family"] == "artifact_publish"
    assert result.test_summary["browser_evidence_required"] is True
    assert result.test_summary["artifact_proof_ready"] is False
    assert "merge_blocked" in result.test_summary["promotion_transitions"]


def test_run_attempt_fails_when_browser_runtime_is_missing(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    runner = HealerRunner(
        _RetryConnector(["not used"]),
        timeout_seconds=30,
        test_gate_mode="local_only",
        default_runtime_profile="web",
        app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/",
                "working_directory": ".",
                "browser": "chromium",
                "headless": True,
            }
        ],
        browser_harness=_FakeBrowserHarness([], runtime_available=False, runtime_reason="Playwright missing"),  # type: ignore[arg-type]
    )

    result = runner.run_attempt(
        issue_id="app-203",
        issue_title="Fix browser-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            entry_url="http://127.0.0.1:3000/",
            runtime_profile="web",
            repro_steps=("goto /", "expect_text Broken widget"),
            artifact_requirements=("failure_video", "resolution_video"),
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "browser_runtime_missing"
    assert result.test_summary["browser_failure_family"] == "runtime_readiness"
    assert "playwright" in result.failure_reason.lower()


def test_run_attempt_classifies_browser_journey_step_failures(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    good_patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([good_patch])
    app_harness = _FakeAppHarness()
    browser_harness = _FakeBrowserHarness(
        [
            BrowserJourneyResult(
                phase="failure",
                passed=False,
                expected_failure_observed=True,
                final_url="http://127.0.0.1:3000/",
                failure_step="expect_text Broken widget",
                screenshot_path=str(tmp_path / "before.png"),
                video_path=str(tmp_path / "before.webm"),
                console_log_path=str(tmp_path / "before-console.log"),
                network_log_path=str(tmp_path / "before-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "failed"},),
            ),
            BrowserJourneyResult(
                phase="failure-replay",
                passed=False,
                expected_failure_observed=True,
                final_url="http://127.0.0.1:3000/",
                failure_step="expect_text Broken widget",
                screenshot_path=str(tmp_path / "before-replay.png"),
                video_path=str(tmp_path / "before-replay.webm"),
                console_log_path=str(tmp_path / "before-replay-console.log"),
                network_log_path=str(tmp_path / "before-replay-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "failed"},),
            ),
            BrowserJourneyResult(
                phase="resolution",
                passed=False,
                expected_failure_observed=False,
                final_url="http://127.0.0.1:3000/",
                failure_step="click button.save",
                error="Button never became enabled",
                screenshot_path=str(tmp_path / "after.png"),
                video_path=str(tmp_path / "after.webm"),
                console_log_path=str(tmp_path / "after-console.log"),
                network_log_path=str(tmp_path / "after-network.jsonl"),
                transcript=({"step": "click button.save", "status": "failed"},),
            ),
        ]
    )
    runner = HealerRunner(
        connector,
        timeout_seconds=30,
        test_gate_mode="local_only",
        default_runtime_profile="web",
        app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/",
                "working_directory": ".",
                "browser": "chromium",
                "headless": True,
            }
        ],
        app_harness=app_harness,  # type: ignore[arg-type]
        browser_harness=browser_harness,  # type: ignore[arg-type]
    )
    runner.validate_workspace = lambda *args, **kwargs: {"failed_tests": 0}  # type: ignore[method-assign]

    result = runner.run_attempt(
        issue_id="app-205",
        issue_title="Fix browser-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            entry_url="http://127.0.0.1:3000/",
            runtime_profile="web",
            repro_steps=("goto /", "expect_text Broken widget"),
            artifact_requirements=("failure_video", "resolution_video"),
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "browser_step_failed"
    assert result.test_summary["browser_failure_family"] == "journey_step"


def test_run_attempt_classifies_browser_artifact_capture_failures(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    good_patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([good_patch])
    app_harness = _FakeAppHarness()
    browser_harness = _ExplodingBrowserHarness(message="screenshot capture failed", phase="resolution")
    browser_harness.results = [
        BrowserJourneyResult(
            phase="failure",
            passed=False,
            expected_failure_observed=True,
            final_url="http://127.0.0.1:3000/",
            failure_step="expect_text Broken widget",
            screenshot_path=str(tmp_path / "before.png"),
            video_path=str(tmp_path / "before.webm"),
            console_log_path=str(tmp_path / "before-console.log"),
            network_log_path=str(tmp_path / "before-network.jsonl"),
            transcript=({"step": "expect_text Broken widget", "status": "failed"},),
        ),
        BrowserJourneyResult(
            phase="failure-replay",
            passed=False,
            expected_failure_observed=True,
            final_url="http://127.0.0.1:3000/",
            failure_step="expect_text Broken widget",
            screenshot_path=str(tmp_path / "before-replay.png"),
            video_path=str(tmp_path / "before-replay.webm"),
            console_log_path=str(tmp_path / "before-replay-console.log"),
            network_log_path=str(tmp_path / "before-replay-network.jsonl"),
            transcript=({"step": "expect_text Broken widget", "status": "failed"},),
        ),
    ]
    runner = HealerRunner(
        connector,
        timeout_seconds=30,
        test_gate_mode="local_only",
        default_runtime_profile="web",
        app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/",
                "working_directory": ".",
                "browser": "chromium",
                "headless": True,
            }
        ],
        app_harness=app_harness,  # type: ignore[arg-type]
        browser_harness=browser_harness,  # type: ignore[arg-type]
    )
    runner.validate_workspace = lambda *args, **kwargs: {"failed_tests": 0}  # type: ignore[method-assign]

    result = runner.run_attempt(
        issue_id="app-206",
        issue_title="Fix browser-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            entry_url="http://127.0.0.1:3000/",
            runtime_profile="web",
            repro_steps=("goto /", "expect_text Broken widget"),
            artifact_requirements=("failure_video", "resolution_video"),
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert result.failure_class == "browser_step_failed"
    assert result.test_summary["browser_failure_family"] == "artifact_capture"


def test_run_attempt_allows_missing_resolution_video_when_screenshots_exist(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "demo.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    good_patch = (
        "```diff\n"
        "diff --git a/demo.py b/demo.py\n"
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "```\n"
    )
    connector = _RetryConnector([good_patch])
    app_harness = _FakeAppHarness()
    browser_harness = _FakeBrowserHarness(
        [
            BrowserJourneyResult(
                phase="failure",
                passed=False,
                expected_failure_observed=True,
                final_url="http://127.0.0.1:3000/",
                failure_step="expect_text Broken widget",
                error="Expected text missing",
                screenshot_path=str(tmp_path / "before.png"),
                video_path=str(tmp_path / "before.webm"),
                console_log_path=str(tmp_path / "before-console.log"),
                network_log_path=str(tmp_path / "before-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "failed"},),
            ),
            BrowserJourneyResult(
                phase="failure-replay",
                passed=False,
                expected_failure_observed=True,
                final_url="http://127.0.0.1:3000/",
                failure_step="expect_text Broken widget",
                error="Expected text missing",
                screenshot_path=str(tmp_path / "before-replay.png"),
                video_path=str(tmp_path / "before-replay.webm"),
                console_log_path=str(tmp_path / "before-replay-console.log"),
                network_log_path=str(tmp_path / "before-replay-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "failed"},),
            ),
            BrowserJourneyResult(
                phase="resolution",
                passed=True,
                expected_failure_observed=False,
                final_url="http://127.0.0.1:3000/",
                screenshot_path=str(tmp_path / "after.png"),
                video_path="",
                console_log_path=str(tmp_path / "after-console.log"),
                network_log_path=str(tmp_path / "after-network.jsonl"),
                transcript=({"step": "expect_text Broken widget", "status": "passed"},),
            ),
        ]
    )
    runner = HealerRunner(
        connector,
        timeout_seconds=30,
        test_gate_mode="local_only",
        default_runtime_profile="web",
        app_runtime_profiles=[
            {
                "name": "web",
                "start_command": "npm run dev",
                "ready_url": "http://127.0.0.1:3000/",
                "working_directory": ".",
                "browser": "chromium",
                "headless": True,
            }
        ],
        app_harness=app_harness,  # type: ignore[arg-type]
        browser_harness=browser_harness,  # type: ignore[arg-type]
    )
    runner.validate_workspace = lambda *args, **kwargs: {"failed_tests": 0}  # type: ignore[method-assign]

    result = runner.run_attempt(
        issue_id="app-204",
        issue_title="Fix browser-backed regression",
        issue_body="Fix demo.py",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            app_target="demo-web",
            entry_url="http://127.0.0.1:3000/",
            runtime_profile="web",
            repro_steps=("goto /", "expect_text Broken widget"),
            artifact_requirements=("failure_video", "resolution_video"),
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert "video_path" not in result.test_summary["artifact_bundle"]["resolution_artifacts"]
    assert all(link["label"] != "resolution_video" for link in result.test_summary["artifact_links"])
