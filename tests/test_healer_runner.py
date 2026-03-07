import subprocess
from pathlib import Path

from flow_healer.healer_runner import (
    HealerRunner,
    _build_docker_test_script,
    _gate_runners_for_mode,
    _normalize_test_gate_mode,
    _run_test_gates,
)
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

    def fake_local(workspace: Path, command: list[str], timeout_seconds: int):
        calls.append(("local", command))
        return {"exit_code": 0, "output_tail": "local ok"}

    def fake_docker(workspace: Path, command: list[str], timeout_seconds: int):
        calls.append(("docker", command))
        return {"exit_code": 0, "output_tail": "docker ok"}

    monkeypatch.setattr("flow_healer.healer_runner._run_pytest_locally", fake_local)
    monkeypatch.setattr("flow_healer.healer_runner._run_pytest_in_docker", fake_docker)

    summary = _run_test_gates(
        Path("."),
        targeted_tests=["tests/test_demo.py"],
        timeout_seconds=30,
        mode="local_then_docker",
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


class _RetryConnector:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.reset_calls: list[str] = []
        self.turns: list[tuple[str, str]] = []

    def get_or_create_thread(self, sender: str) -> str:
        return sender

    def reset_thread(self, sender: str) -> str:
        self.reset_calls.append(sender)
        return sender

    def run_turn(self, thread_id: str, prompt: str) -> str:
        self.turns.append((thread_id, prompt))
        return self.outputs.pop(0)

    def ensure_started(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


class _WorkspaceEditingConnector(_RetryConnector):
    def __init__(self, workspace: Path, outputs):
        super().__init__(outputs)
        self.workspace = workspace

    def run_turn(self, thread_id: str, prompt: str) -> str:
        self.turns.append((thread_id, prompt))
        (self.workspace / "docs").mkdir(exist_ok=True)
        (self.workspace / "docs" / "create-plan-docs.md").write_text("Synthesized plan\n", encoding="utf-8")
        return self.outputs.pop(0)


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
    assert "Use web browsing when needed" in prompt


def test_run_attempt_marks_input_specs_as_context_in_prompt(tmp_path):
    connector = _RetryConnector(["not a patch", "still not a patch"])
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
            "ConnectorUnavailable: Unable to resolve Codex command 'codex'. Set service.connector_command to an absolute path.",
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
