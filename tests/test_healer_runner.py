import subprocess
import sys
from pathlib import Path

from flow_healer.healer_runner import (
    HealerRunner,
    ResolvedExecution,
    _validate_artifact_outputs,
    _build_docker_test_script,
    _changed_paths,
    _gate_runners_for_mode,
    _looks_like_unified_diff,
    _normalize_test_gate_mode,
    _run_test_gates,
    _run_tests_in_docker,
    _run_tests_locally,
    _stage_workspace_changes,
)
from flow_healer.language_strategies import get_strategy
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


def test_run_tests_in_docker_uses_posix_shell(monkeypatch, tmp_path):
    seen: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = _run_tests_in_docker(
        tmp_path,
        ["go", "test", "./..."],
        30,
        strategy=get_strategy("go"),
        local_gate_policy="auto",
    )

    assert seen["cmd"][0:8] == [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{tmp_path}:/workspace",
        "-w",
        "/workspace",
        "golang:1.22-alpine",
    ]
    assert seen["cmd"][8:10] == ["sh", "-c"]
    assert summary["gate_status"] == "passed"


def test_run_tests_in_docker_reports_missing_docker(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = _run_tests_in_docker(
        tmp_path,
        ["go", "test", "./..."],
        30,
        strategy=get_strategy("go"),
        local_gate_policy="auto",
    )

    assert summary["gate_status"] == "failed"
    assert summary["gate_reason"] == "tool_missing"
    assert summary["exit_code"] == 127


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


def test_stage_workspace_changes_excludes_ruby_dependency_artifacts(tmp_path):
    workspace = tmp_path / "repo"
    ruby_root = workspace / "e2e-smoke" / "ruby"
    (ruby_root / "spec").mkdir(parents=True)
    workspace.mkdir(exist_ok=True)
    _init_git_repo(workspace)
    (ruby_root / "add.rb").write_text("def add(a, b)\n  a - b\nend\n", encoding="utf-8")
    (ruby_root / "spec" / "add_spec.rb").write_text("RSpec.describe '#add' do\nend\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    (ruby_root / "add.rb").write_text("def add(a, b)\n  a + b\nend\n", encoding="utf-8")
    (ruby_root / "vendor" / "bundle" / "gems" / "demo").mkdir(parents=True)
    (ruby_root / "vendor" / "bundle" / "gems" / "demo" / "generated.rb").write_text("module Demo; end\n", encoding="utf-8")
    (ruby_root / ".bundle").mkdir()
    (ruby_root / ".bundle" / "config").write_text("BUNDLE_PATH: vendor/bundle\n", encoding="utf-8")
    (ruby_root / "Gemfile.lock").write_text("GEM\n", encoding="utf-8")

    changed = _stage_workspace_changes(
        workspace,
        issue_title="Ruby sandbox regression",
        issue_body="Fix the Ruby sandbox behavior and keep tests passing.",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("e2e-smoke/ruby/add.rb",),
            tool_policy="repo_only",
            validation_profile="code_change",
            language="ruby",
        ),
        language="ruby",
    )

    assert changed is True
    assert _changed_paths(workspace) == ["e2e-smoke/ruby/add.rb"]


def test_stage_workspace_changes_excludes_ruby_lockfile_for_validation_command_only_issue(tmp_path):
    workspace = tmp_path / "repo"
    ruby_root = workspace / "e2e-smoke" / "ruby"
    (ruby_root / "spec").mkdir(parents=True)
    workspace.mkdir(exist_ok=True)
    _init_git_repo(workspace)
    (ruby_root / "add.rb").write_text("def add(a, b)\n  a - b\nend\n", encoding="utf-8")
    (ruby_root / "spec" / "add_spec.rb").write_text("RSpec.describe '#add' do\nend\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    (ruby_root / "add.rb").write_text("def add(a, b)\n  a + b\nend\n", encoding="utf-8")
    (ruby_root / "spec" / "add_spec.rb").write_text(
        "RSpec.describe '#add' do\n"
        "  it 'adds numbers' do\n"
        "    expect(add(2, 3)).to eq(5)\n"
        "  end\n"
        "end\n",
        encoding="utf-8",
    )
    (ruby_root / "Gemfile.lock").write_text("BUNDLED WITH\n   2.5.23\n", encoding="utf-8")

    changed = _stage_workspace_changes(
        workspace,
        issue_title="Ruby sandbox regression",
        issue_body=(
            "Fix the Ruby sandbox behavior in e2e-smoke/ruby.\n"
            "Validation: cd e2e-smoke/ruby && bundle exec rspec\n"
        ),
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("e2e-smoke/ruby/add.rb", "e2e-smoke/ruby/spec/add_spec.rb"),
            tool_policy="repo_only",
            validation_profile="code_change",
            language="ruby",
        ),
        language="ruby",
    )

    assert changed is True
    assert _changed_paths(workspace) == [
        "e2e-smoke/ruby/add.rb",
        "e2e-smoke/ruby/spec/add_spec.rb",
    ]


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


def test_run_test_gates_marks_local_skipped_when_toolchain_unavailable(monkeypatch):
    from flow_healer.language_strategies import LanguageStrategy

    no_local_strategy = LanguageStrategy(
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


class _RetryConnector:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.reset_calls: list[str] = []
        self.turns: list[tuple[str, str]] = []
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


class _ArtifactNoiseConnector(_RetryConnector):
    def __init__(self, workspace: Path, outputs, *, language: str):
        super().__init__(outputs)
        self.workspace = workspace
        self.language = language

    def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
        self.turns.append((thread_id, prompt))
        if self.language == "ruby":
            ruby_root = self.workspace / "e2e-smoke" / "ruby"
            (ruby_root / "vendor" / "bundle" / "gems" / "demo").mkdir(parents=True, exist_ok=True)
            (ruby_root / ".bundle").mkdir(exist_ok=True)
            (ruby_root / "Gemfile.lock").write_text("LOCKFILE\n", encoding="utf-8")
            (ruby_root / ".bundle" / "config").write_text("BUNDLE_PATH: vendor/bundle\n", encoding="utf-8")
            for index in range(25):
                (ruby_root / "vendor" / "bundle" / "gems" / "demo" / f"file_{index}.rb").write_text(
                    f"# generated {index}\n",
                    encoding="utf-8",
                )
            (ruby_root / "add.rb").write_text(
                "def add(a, b)\n  a + b\nend\n\ndef multiply(a, b)\n  a * b\nend\n",
                encoding="utf-8",
            )
            (ruby_root / "spec" / "add_spec.rb").write_text(
                "RSpec.describe '#add' do\n"
                "  it 'adds numbers' do\n"
                "    expect(add(2, 3)).to eq(5)\n"
                "  end\n"
                "end\n",
                encoding="utf-8",
            )
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


def test_run_attempt_ignores_generated_artifact_noise_for_diff_limit(monkeypatch, tmp_path):
    workspace = tmp_path / "repo"
    ruby_root = workspace / "e2e-smoke" / "ruby"
    (ruby_root / "spec").mkdir(parents=True)
    workspace.mkdir(exist_ok=True)
    _init_git_repo(workspace)
    (ruby_root / "add.rb").write_text("def add(a, b)\n  a - b\nend\n", encoding="utf-8")
    (ruby_root / "spec" / "add_spec.rb").write_text("RSpec.describe '#add' do\nend\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    connector = _ArtifactNoiseConnector(workspace, ["Applied changes."], language="ruby")
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
        issue_id="500",
        issue_title="Ruby sandbox regression",
        issue_body="Fix the Ruby sandbox behavior and keep tests passing.",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("e2e-smoke/ruby/add.rb", "e2e-smoke/ruby/spec/add_spec.rb"),
            tool_policy="repo_only",
            validation_profile="code_change",
            language="ruby",
        ),
        workspace=workspace,
        max_diff_files=3,
        max_diff_lines=80,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is True
    assert result.diff_paths == ["e2e-smoke/ruby/add.rb", "e2e-smoke/ruby/spec/add_spec.rb"]


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


def test_run_attempt_includes_language_in_prompt(tmp_path):
    connector = _RetryConnector(["not a patch"] * 5)
    runner = HealerRunner(connector, timeout_seconds=30, test_gate_mode="local_only")
    workspace = tmp_path / "repo"
    workspace.mkdir()

    result = runner.run_attempt(
        issue_id="200",
        issue_title="Fix handler",
        issue_body="Fix the handler in main.go",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
            language="go",
        ),
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=20,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    prompt = connector.turns[0][1]
    assert "This repository uses go." in prompt
    assert "Follow go conventions" in prompt


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


# --- Change 1: _build_retry_prompt includes class-specific guidance ---


from flow_healer.healer_runner import _build_retry_prompt


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
