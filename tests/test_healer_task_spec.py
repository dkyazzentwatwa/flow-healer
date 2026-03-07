from flow_healer.healer_task_spec import compile_task_spec


def test_compile_task_spec_defaults_research_issue_to_docs_artifact() -> None:
    spec = compile_task_spec(
        issue_title="Docs for preflight check",
        issue_body="Research best ways to introduce stronger preflight checks before a proposal runs.",
    )

    assert spec.task_kind == "research"
    assert spec.output_targets == ("docs/docs-for-preflight-check.md",)
    assert spec.input_context_paths == ()
    assert spec.tool_policy == "repo_plus_web"
    assert spec.validation_profile == "artifact_only"


def test_compile_task_spec_uses_explicit_file_target_for_edit_issue() -> None:
    spec = compile_task_spec(
        issue_title="Revise README",
        issue_body="Edit README.md to clarify startup behavior.",
    )

    assert spec.task_kind == "docs"
    assert spec.output_targets == ("README.md",)
    assert spec.input_context_paths == ()
    assert spec.tool_policy == "repo_only"
    assert spec.validation_profile == "artifact_only"


def test_compile_task_spec_leaves_build_issue_open_for_multi_file_patch() -> None:
    spec = compile_task_spec(
        issue_title="Build a todo app",
        issue_body="Build a simple todo app with persistence.",
    )

    assert spec.task_kind == "build"
    assert spec.output_targets == ()
    assert spec.input_context_paths == ()
    assert spec.tool_policy == "repo_only"
    assert spec.validation_profile == "code_change"


def test_compile_task_spec_prefers_required_outputs_over_review_scope_paths() -> None:
    spec = compile_task_spec(
        issue_title="Code review core files and produce report",
        issue_body=(
            "## Scope to review\n"
            "- src/flow_healer/healer_runner.py\n"
            "- src/flow_healer/healer_loop.py\n\n"
            "## Required outputs\n"
            "- docs/reviews/healer-core-review-round-1.md\n"
        ),
    )

    assert spec.task_kind == "fix"
    assert spec.output_targets == ("docs/reviews/healer-core-review-round-1.md",)
    assert spec.input_context_paths == ()
    assert spec.tool_policy == "repo_only"
    assert spec.validation_profile == "artifact_only"


def test_compile_task_spec_treats_markdown_as_input_for_code_upgrade_task() -> None:
    spec = compile_task_spec(
        issue_title="Implement skills-suggestions.md",
        issue_body="Implement code upgrades in skills-suggestions.md and make sure they pass the tests.",
    )

    assert spec.task_kind == "build"
    assert spec.output_targets == ()
    assert spec.input_context_paths == ("skills-suggestions.md",)
    assert spec.tool_policy == "repo_only"
    assert spec.validation_profile == "code_change"


def test_compile_task_spec_treats_markdown_as_input_when_issue_asks_to_ensure_tests_pass() -> None:
    spec = compile_task_spec(
        issue_title="Implement prompt-upgrade-notes.md",
        issue_body="Implement the changes in prompt-upgrade-notes.md and ensure tests pass.",
    )

    assert spec.task_kind == "build"
    assert spec.output_targets == ()
    assert spec.input_context_paths == ("prompt-upgrade-notes.md",)
    assert spec.tool_policy == "repo_only"
    assert spec.validation_profile == "code_change"


def test_compile_task_spec_marks_input_spec_only_markdown_as_context_not_target() -> None:
    spec = compile_task_spec(
        issue_title="Implement upgrades from research-notes.md",
        issue_body=(
            "Use research-notes.md as input spec only.\n"
            "Do not make doc-only edits.\n"
            "Implement the code changes in src/flow_healer/ and add tests."
        ),
    )

    assert spec.task_kind == "build"
    assert spec.output_targets == ()
    assert spec.input_context_paths == ("research-notes.md",)
    assert spec.validation_profile == "code_change"


def test_compile_task_spec_handles_path_prefix_directive_with_or_without_space() -> None:
    spec = compile_task_spec(
        issue_title="Node.js queue test",
        issue_body="path:Node.js keeps work scoped",
    )

    assert spec.output_targets == ("Node.js",)
    assert spec.task_kind == "edit"

    spec_with_space = compile_task_spec(
        issue_title="Node.js queue test",
        issue_body="path: Node.js keeps work scoped",
    )

    assert spec_with_space.output_targets == ("Node.js",)
    assert spec_with_space.task_kind == "edit"
