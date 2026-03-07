from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from conftest import FakeConnector, FakeStore

from flow_healer.healer_memory import HealerMemoryService
from flow_healer.healer_runner import HealerRunner
from flow_healer.healer_task_spec import HealerTaskSpec
from flow_healer.healer_verifier import HealerVerifier


def test_healer_memory_records_success_and_failure_lessons():
    store = FakeStore()
    memory = HealerMemoryService(store, enabled=True)
    issue = SimpleNamespace(issue_id="501", title="Fix store race", body="Touches src/apple_flow/store.py")

    memory.maybe_record_lesson(
        issue=issue,
        attempt_id="hat_success",
        final_state="pr_open",
        predicted_lock_set=["path:src/apple_flow/store.py"],
        actual_diff_set=["src/apple_flow/store.py"],
        test_summary={"targeted_tests": ["tests/test_store.py"]},
        verifier_summary={"passed": True, "summary": "Looks good"},
        failure_class="",
        failure_reason="",
    )
    memory.maybe_record_lesson(
        issue=issue,
        attempt_id="hat_failure",
        final_state="failed",
        predicted_lock_set=["path:src/apple_flow/store.py"],
        actual_diff_set=[],
        test_summary={"targeted_tests": ["tests/test_store.py"]},
        verifier_summary={},
        failure_class="tests_failed",
        failure_reason="pytest failed",
    )

    lessons = store.list_healer_lessons()
    assert len(lessons) == 2
    assert {lesson["outcome"] for lesson in lessons} == {"success", "failure"}
    assert any(lesson["guardrail"]["failure_class"] == "tests_failed" for lesson in lessons)


def test_healer_memory_retrieval_prefers_scope_overlap_and_marks_use():
    store = FakeStore()
    memory = HealerMemoryService(store, enabled=True)
    issue = SimpleNamespace(issue_id="502", title="Repair parser edge case", body="src/apple_flow/store.py")

    memory.maybe_record_lesson(
        issue=issue,
        attempt_id="hat_scope",
        final_state="pr_pending_approval",
        predicted_lock_set=["path:src/apple_flow/store.py"],
        actual_diff_set=["src/apple_flow/store.py"],
        test_summary={"targeted_tests": ["tests/test_store.py"]},
        verifier_summary={"passed": True, "summary": "pass"},
        failure_class="",
        failure_reason="",
    )
    memory.maybe_record_lesson(
        issue=SimpleNamespace(issue_id="503", title="Fix unrelated docs issue", body="README.md"),
        attempt_id="hat_other",
        final_state="pr_open",
        predicted_lock_set=["path:README.md"],
        actual_diff_set=["README.md"],
        test_summary={},
        verifier_summary={"passed": True, "summary": "pass"},
        failure_class="",
        failure_reason="",
    )

    context = memory.build_prompt_context(
        issue_text="Parser bug in src/apple_flow/store.py",
        predicted_lock_set=["path:src/apple_flow/store.py"],
    )

    assert "Relevant prior healer lessons:" in context
    assert "store.py" in context
    used = [lesson for lesson in store.healer_lessons if lesson["use_count"] > 0]
    assert len(used) == 1


def test_healer_memory_skips_artifact_scope_lessons_for_code_change_tasks():
    store = FakeStore()
    memory = HealerMemoryService(store, enabled=True)

    memory.maybe_record_lesson(
        issue=SimpleNamespace(issue_id="510", title="Docs tweak", body="skills-suggestions.md"),
        attempt_id="hat_docs",
        final_state="pr_open",
        predicted_lock_set=["path:skills-suggestions.md"],
        actual_diff_set=["skills-suggestions.md"],
        test_summary={},
        verifier_summary={"passed": True, "summary": "pass"},
        failure_class="",
        failure_reason="",
    )
    memory.maybe_record_lesson(
        issue=SimpleNamespace(issue_id="511", title="Fix service race", body="src/flow_healer/service.py"),
        attempt_id="hat_code",
        final_state="pr_open",
        predicted_lock_set=["path:src/flow_healer/service.py"],
        actual_diff_set=["src/flow_healer/service.py"],
        test_summary={},
        verifier_summary={"passed": True, "summary": "pass"},
        failure_class="",
        failure_reason="",
    )

    context = memory.build_prompt_context(
        issue_text="Implement code fix in src/flow_healer/service.py and pass tests",
        predicted_lock_set=["path:src/flow_healer/service.py"],
        task_kind="build",
        validation_profile="code_change",
        output_targets=[],
    )

    assert "service.py" in context
    assert "skills-suggestions.md" not in context


def test_healer_runner_includes_learned_context_in_prompt(tmp_path):
    connector = FakeConnector()
    runner = HealerRunner(connector=connector, timeout_seconds=30)
    workspace = Path(tmp_path)

    result = runner.run_attempt(
        issue_id="600",
        issue_title="Fix issue",
        issue_body="Body",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=(),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        learned_context="Relevant prior healer lessons:\n- Keep changes small.",
        workspace=workspace,
        max_diff_files=5,
        max_diff_lines=50,
        max_failed_tests_allowed=0,
        targeted_tests=[],
    )

    assert result.success is False
    assert "Keep changes small." in connector.turns[0][1]


def test_healer_verifier_includes_learned_context_in_prompt():
    connector = FakeConnector()
    verifier = HealerVerifier(connector=connector)

    verifier.verify(
        issue_id="601",
        issue_title="Fix verifier issue",
        issue_body="Body",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("src/apple_flow/store.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        diff_paths=["src/apple_flow/store.py"],
        test_summary={"full_exit_code": 0},
        proposer_output="diff --git a/x b/x",
        learned_context="Relevant prior healer lessons:\n- Preserve verified behavior.",
    )

    assert "Preserve verified behavior." in connector.turns[0][1]


def test_healer_verifier_short_circuits_artifact_only_docs_diff():
    connector = FakeConnector()
    verifier = HealerVerifier(connector=connector)

    result = verifier.verify(
        issue_id="6011",
        issue_title="Create docs artifact",
        issue_body="Research and create docs/research-note.md",
        task_spec=HealerTaskSpec(
            task_kind="research",
            output_mode="patch",
            output_targets=("docs/research-note.md",),
            tool_policy="repo_plus_web",
            validation_profile="artifact_only",
        ),
        diff_paths=["docs/research-note.md"],
        test_summary={"mode": "skipped_artifact_only", "failed_tests": 0},
        proposer_output="Research summary prose output",
    )

    assert result.passed is True
    assert "deterministic docs/config guardrails" in result.summary
    assert connector.turns == []


def test_healer_verifier_adds_docs_only_guardrails():
    connector = FakeConnector()
    verifier = HealerVerifier(connector=connector)

    verifier.verify(
        issue_id="602",
        issue_title="Update roadmap",
        issue_body="Refresh roadmap wording.",
        task_spec=HealerTaskSpec(
            task_kind="docs",
            output_mode="patch",
            output_targets=("roadmap.md",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        diff_paths=["roadmap.md"],
        test_summary={"full_exit_code": 0},
        proposer_output="```diff\ndiff --git a/roadmap.md b/roadmap.md\n```",
    )

    prompt = connector.turns[0][1]
    assert "Change classification: docs-only." in prompt
    assert "Docs-only changes may pass" in prompt
    assert "Do not fail a docs-only fix merely because it does not change runtime code." in prompt
    assert "focus on accuracy, clarity, and consistency" in prompt


def test_healer_verifier_adds_config_only_guardrails():
    connector = FakeConnector()
    verifier = HealerVerifier(connector=connector)

    verifier.verify(
        issue_id="603",
        issue_title="Adjust sample config",
        issue_body="Update config.example.yaml defaults.",
        task_spec=HealerTaskSpec(
            task_kind="edit",
            output_mode="patch",
            output_targets=("config.example.yaml",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        diff_paths=["config.example.yaml"],
        test_summary={"full_exit_code": 0},
        proposer_output="```diff\ndiff --git a/config.example.yaml b/config.example.yaml\n```",
    )

    prompt = connector.turns[0][1]
    assert "Change classification: config-only." in prompt
    assert "Config-only changes may pass" in prompt
    assert "does not introduce secrets" in prompt
    assert "real credentials, machine-specific paths" in prompt


def test_healer_verifier_adds_high_risk_guardrails():
    connector = FakeConnector()
    verifier = HealerVerifier(connector=connector)

    verifier.verify(
        issue_id="604",
        issue_title="Touch runtime service logic",
        issue_body="Fix service orchestration.",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("src/flow_healer/service.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        diff_paths=["src/flow_healer/service.py"],
        test_summary={"full_exit_code": 0},
        proposer_output="```diff\ndiff --git a/src/flow_healer/service.py b/src/flow_healer/service.py\n```",
    )

    prompt = connector.turns[0][1]
    assert "Change classification: high-risk." in prompt
    assert "High-risk code changes require strict scrutiny" in prompt
    assert "convincing validation" in prompt
    assert "missing, ambiguous, or inconsistent" in prompt


def test_healer_verifier_treats_dependency_manifest_as_high_risk():
    connector = FakeConnector()
    verifier = HealerVerifier(connector=connector)

    verifier.verify(
        issue_id="605",
        issue_title="Adjust build dependency",
        issue_body="Update pyproject settings.",
        task_spec=HealerTaskSpec(
            task_kind="fix",
            output_mode="patch",
            output_targets=("pyproject.toml",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        diff_paths=["pyproject.toml"],
        test_summary={"full_exit_code": 0},
        proposer_output="```diff\ndiff --git a/pyproject.toml b/pyproject.toml\n```",
    )

    prompt = connector.turns[0][1]
    assert "Change classification: high-risk." in prompt
    assert "dependency, build, state, locking, and service-entrypoint changes" in prompt


def test_healer_verifier_detects_broader_docs_and_config_paths():
    connector = FakeConnector()
    verifier = HealerVerifier(connector=connector)

    verifier.verify(
        issue_id="606",
        issue_title="Refresh setup docs",
        issue_body="Update README instructions.",
        task_spec=HealerTaskSpec(
            task_kind="docs",
            output_mode="patch",
            output_targets=("README.rst",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        diff_paths=["README.rst"],
        test_summary={"full_exit_code": 0},
        proposer_output="```diff\ndiff --git a/README.rst b/README.rst\n```",
    )
    assert "Change classification: docs-only." in connector.turns[0][1]

    verifier.verify(
        issue_id="607",
        issue_title="Adjust env template",
        issue_body="Update sample env defaults.",
        task_spec=HealerTaskSpec(
            task_kind="edit",
            output_mode="patch",
            output_targets=("deploy/.env.sample",),
            tool_policy="repo_only",
            validation_profile="code_change",
        ),
        diff_paths=["deploy/.env.sample"],
        test_summary={"full_exit_code": 0},
        proposer_output="```diff\ndiff --git a/deploy/.env.sample b/deploy/.env.sample\n```",
    )
    assert "Change classification: config-only." in connector.turns[1][1]
