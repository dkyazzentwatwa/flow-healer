from flow_healer.healer_task_spec import compile_task_spec, task_spec_to_prompt_block, _is_code_path
from flow_healer.language_strategies import UnsupportedLanguageError, ensure_supported_language


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


def test_compile_task_spec_ignores_urls_when_extracting_artifact_targets() -> None:
    spec = compile_task_spec(
        issue_title="README has broken internal links and placeholder GitHub URLs",
        issue_body=(
            "## Evidence\n"
            "- Installation URL still points to https://github.com/yourusername/osint-investigator in README.md\n"
            "- Support URL still points to https://github.com/yourusername/osint-investigator/issues in README.md\n"
            "- docs/OSINT-BEGINNER-GUIDE.md exists and should be linked from README.md\n"
        ),
    )

    assert "github.c" not in spec.output_targets
    assert spec.validation_profile == "artifact_only"
    assert "README.md" in spec.output_targets


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


def test_compile_task_spec_preserves_node_js_queue_test_contract() -> None:
    spec = compile_task_spec(
        issue_title="Issue #73: Node.js queue test 2",
        issue_body=(
            "Simple queued Node.js test issue 2 for flow-healer validation.\n"
            "\n"
            "Acceptance criteria:\n"
            "- Issue is visible in the queue\n"
            "- Flow Healer can pick it up\n"
            "- Labels mark it as ready and PR-approved"
        ),
    )

    assert spec.task_kind == "edit"
    assert spec.output_targets == ("Node.js",)
    assert spec.input_context_paths == ()
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


def test_compile_task_spec_honors_task_contract_kind_hint() -> None:
    spec = compile_task_spec(
        issue_title="Tighten the parser",
        issue_body=(
            "### Task Contract\n"
            "- Task kind: docs\n"
            "- Output targets: docs/parser-notes.md\n"
        ),
    )

    assert spec.task_kind == "docs"
    assert spec.output_targets == ("docs/parser-notes.md",)
    assert spec.validation_profile == "artifact_only"


def test_compile_task_spec_separates_input_context_from_explicit_code_outputs() -> None:
    spec = compile_task_spec(
        issue_title="Implement fixes from research-notes.md",
        issue_body=(
            "## Input context\n"
            "- research-notes.md\n\n"
            "## Required code outputs\n"
            "- src/flow_healer/healer_task_spec.py\n"
            "- tests/test_healer_task_spec.py\n"
        ),
    )

    assert spec.task_kind == "build"
    assert spec.output_targets == (
        "src/flow_healer/healer_task_spec.py",
        "tests/test_healer_task_spec.py",
    )
    assert spec.input_context_paths == ("research-notes.md",)
    assert spec.validation_profile == "code_change"


def test_task_spec_prompt_block_includes_contract_guidance() -> None:
    spec = compile_task_spec(
        issue_title="Implement skills-suggestions.md",
        issue_body="Use skills-suggestions.md as input spec only and do not make doc-only edits.",
    )

    prompt_block = task_spec_to_prompt_block(spec)

    assert "Success criteria: Stage a production-safe code patch" in prompt_block
    assert "Failure handling: If a direct edit is not possible, return exactly one valid unified diff fenced block." in prompt_block
    assert "Default next action: Implement the smallest safe repo patch" in prompt_block


def test_task_spec_prompt_block_marks_non_sandbox_code_targets_as_anchors() -> None:
    spec = compile_task_spec(
        issue_title="Fix Swift smoke fixture",
        issue_body="Fix src/demo.py so the fixture builds and passes the regression test.",
    )

    prompt_block = task_spec_to_prompt_block(spec)

    assert "Output target policy: Named targets are anchors for the fix" in prompt_block
    assert "Inspect only enough files" not in prompt_block
    assert "Preferred output order" not in prompt_block


def test_task_spec_prompt_block_marks_sandbox_code_targets_as_exact_allowlist() -> None:
    spec = compile_task_spec(
        issue_title="Hard: Node app route-state recovery regression",
        issue_body=(
            "Required code outputs:\n"
            "- e2e-smoke/node-app/src/app.js\n"
            "- e2e-smoke/node-app/test/app.test.js\n\n"
            "Validation:\n"
            "- cd e2e-smoke/node-app && npm test -- --passWithNoTests\n"
        ),
    )

    prompt_block = task_spec_to_prompt_block(spec)

    assert "Output target policy: Named targets are the exact allowed edit set for this issue" in prompt_block


def test_compile_task_spec_passes_language_through() -> None:
    spec = compile_task_spec(
        issue_title="Fix addition bug",
        issue_body="Fix demo.py",
        language="python",
    )
    assert spec.language == "python"
    assert spec.language_source == "issue"


def test_compile_task_spec_infers_python_from_py_target() -> None:
    spec = compile_task_spec(
        issue_title="Fix addition bug",
        issue_body="Fix demo.py",
    )
    assert spec.language == "python"
    assert spec.language_source == "issue"


def test_task_spec_prompt_block_includes_language_when_set() -> None:
    spec = compile_task_spec(
        issue_title="Fix addition bug",
        issue_body="Fix demo.py",
        language="python",
    )
    prompt_block = task_spec_to_prompt_block(spec)
    assert "- Language: python" in prompt_block


def test_task_spec_prompt_block_omits_language_when_empty() -> None:
    spec = compile_task_spec(
        issue_title="Write notes",
        issue_body="Document the plan in docs/notes.md",
    )
    prompt_block = task_spec_to_prompt_block(spec)
    assert "Language:" not in prompt_block


def test_compile_task_spec_infers_node_execution_root_and_validation_command() -> None:
    spec = compile_task_spec(
        issue_title="Node sandbox regression",
        issue_body=(
            "Required code outputs:\n"
            "- e2e-smoke/node/src/add.js\n"
            "- e2e-smoke/node/test/add.test.js\n\n"
            "Validation:\n"
            "- cd e2e-smoke/node && npm test -- --passWithNoTests\n"
        ),
    )

    assert spec.language == "node"
    assert spec.language_source == "issue"
    assert spec.execution_root == "e2e-smoke/node"
    assert spec.validation_commands == ("cd e2e-smoke/node && npm test -- --passWithNoTests",)


def test_compile_task_spec_ignores_issue_title_when_extracting_validation_commands() -> None:
    spec = compile_task_spec(
        issue_title="npm run test only",
        issue_body="Please review parser wording.",
    )

    assert spec.validation_commands == ()
    assert spec.execution_root == ""


def test_compile_task_spec_preserves_python3_pytest_validation_command_and_execution_root() -> None:
    spec = compile_task_spec(
        issue_title="FastAPI sandbox regression",
        issue_body=(
            "Required code outputs:\n"
            "- e2e-apps/python-fastapi/app/api.py\n\n"
            "Validation:\n"
            "- cd e2e-apps/python-fastapi && python3 -m pytest -q\n"
        ),
    )

    assert spec.language == "python"
    assert spec.execution_root == "e2e-apps/python-fastapi"
    assert spec.validation_commands == ("cd e2e-apps/python-fastapi && python3 -m pytest -q",)


def test_compile_task_spec_infers_swift_execution_root_and_validation_command() -> None:
    spec = compile_task_spec(
        issue_title="Swift sandbox regression",
        issue_body=(
            "Required code outputs:\n"
            "- e2e-smoke/swift/Sources/FlowHealerAdd/Add.swift\n"
            "- e2e-smoke/swift/Tests/FlowHealerAddTests/AddTests.swift\n\n"
            "Validation:\n"
            "- cd e2e-smoke/swift && swift test\n"
        ),
    )

    assert spec.language == "swift"
    assert spec.language_source == "issue"
    assert spec.execution_root == "e2e-smoke/swift"
    assert spec.validation_commands == ("cd e2e-smoke/swift && swift test",)


def test_compile_task_spec_swift_inference_routes_to_unsupported_language_path() -> None:
    spec = compile_task_spec(
        issue_title="Swift sandbox regression",
        issue_body="Validation: cd e2e-smoke/swift && swift test",
    )

    assert spec.language == "swift"
    try:
        ensure_supported_language(spec.language, source="issue instructions")
    except UnsupportedLanguageError as exc:
        assert "supports only python and node" in str(exc)
    else:
        raise AssertionError("expected swift issue language to be rejected")


def test_task_spec_prompt_block_includes_execution_root_and_validation_commands() -> None:
    spec = compile_task_spec(
        issue_title="Swift sandbox regression",
        issue_body="Validation: cd e2e-smoke/swift && swift test",
    )

    prompt_block = task_spec_to_prompt_block(spec)

    assert "- Execution root: e2e-smoke/swift" in prompt_block
    assert "Validation commands: cd e2e-smoke/swift && swift test" in prompt_block


def test_compile_task_spec_infers_node_execution_root_for_e2e_apps() -> None:
    spec = compile_task_spec(
        issue_title="Next.js sandbox regression",
        issue_body=(
            "Required code outputs:\n"
            "- e2e-apps/node-next/app/api/todos/route.js\n"
            "- e2e-apps/node-next/lib/todo-service.js\n\n"
            "Validation:\n"
            "- cd e2e-apps/node-next && npm test\n"
        ),
    )

    assert spec.language == "node"
    assert spec.language_source == "issue"
    assert spec.task_kind == "fix"
    assert spec.execution_root == "e2e-apps/node-next"
    assert "Next.js" not in spec.output_targets
    assert spec.output_targets == (
        "e2e-apps/node-next/app/api/todos/route.js",
        "e2e-apps/node-next/lib/todo-service.js",
    )
    assert spec.validation_commands == ("cd e2e-apps/node-next && npm test",)


def test_compile_task_spec_infers_python_execution_root_for_e2e_apps() -> None:
    spec = compile_task_spec(
        issue_title="FastAPI sandbox regression",
        issue_body=(
            "Required code outputs:\n"
            "- e2e-apps/python-fastapi/app/api.py\n"
            "- e2e-apps/python-fastapi/app/service.py\n\n"
            "Validation:\n"
            "- cd e2e-apps/python-fastapi && pytest -q\n"
        ),
    )

    assert spec.language == "python"
    assert spec.language_source == "issue"
    assert spec.task_kind == "fix"
    assert spec.execution_root == "e2e-apps/python-fastapi"
    assert spec.validation_commands == ("cd e2e-apps/python-fastapi && pytest -q",)


def test_compile_task_spec_infers_swift_execution_root_for_e2e_smoke_paths() -> None:
    spec = compile_task_spec(
        issue_title="Swift todo sandbox regression",
        issue_body=(
            "Required code outputs:\n"
            "- e2e-smoke/swift/Sources/FlowHealerAdd/Add.swift\n"
            "- e2e-smoke/swift/Tests/FlowHealerAddTests/AddTests.swift\n\n"
            "Validation:\n"
            "- cd e2e-smoke/swift && swift test\n"
        ),
    )

    assert spec.language == "swift"
    assert spec.language_source == "issue"
    assert spec.task_kind == "fix"
    assert spec.execution_root == "e2e-smoke/swift"
    assert "Package.swift" not in spec.output_targets
    assert spec.validation_commands == ("cd e2e-smoke/swift && swift test",)


def test_compile_task_spec_infers_prosper_chat_execution_root_for_e2e_apps() -> None:
    spec = compile_task_spec(
        issue_title="Prosper chat backend regression",
        issue_body=(
            "Required code outputs:\n"
            "- e2e-apps/prosper-chat/src/App.tsx\n"
            "- e2e-apps/prosper-chat/supabase/functions/chat-widget/index.ts\n\n"
            "Validation:\n"
            "- cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh full\n"
        ),
    )

    assert spec.language == "node"
    assert spec.language_source == "issue"
    assert spec.task_kind == "fix"
    assert spec.execution_root == "e2e-apps/prosper-chat"
    assert spec.validation_commands == ("cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh full",)


def test_compile_task_spec_infers_prosper_chat_db_validation_command() -> None:
    spec = compile_task_spec(
        issue_title="Prosper chat DB policy task",
        issue_body=(
            "Required code outputs:\n"
            "- e2e-apps/prosper-chat/supabase/migrations/20260302101500_7f8d9de2-cb2b-4f35-b3b8-6d8a8f519e7e.sql\n"
            "- e2e-apps/prosper-chat/supabase/assertions/anon_access_controls.sql\n\n"
            "Validation:\n"
            "- cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh db\n"
        ),
    )

    assert spec.language == "node"
    assert spec.execution_root == "e2e-apps/prosper-chat"
    assert spec.output_targets == (
        "e2e-apps/prosper-chat/supabase/migrations/20260302101500_7f8d9de2-cb2b-4f35-b3b8-6d8a8f519e7e.sql",
        "e2e-apps/prosper-chat/supabase/assertions/anon_access_controls.sql",
    )
    assert spec.validation_commands == ("cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh db",)


def test_compile_task_spec_infers_prosper_chat_backend_validation_command() -> None:
    spec = compile_task_spec(
        issue_title="Prosper chat backend task",
        issue_body=(
            "Required code outputs:\n"
            "- e2e-apps/prosper-chat/supabase/functions/check-subscription/index.ts\n"
            "- e2e-apps/prosper-chat/supabase/functions/_shared/billing.ts\n\n"
            "Validation:\n"
            "- cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh backend\n"
        ),
    )

    assert spec.language == "node"
    assert spec.execution_root == "e2e-apps/prosper-chat"
    assert spec.validation_commands == ("cd e2e-apps/prosper-chat && ./scripts/healer_validate.sh backend",)


def test_compile_task_spec_prefers_rooted_swift_paths_over_bare_filename_mentions() -> None:
    spec = compile_task_spec(
        issue_title="Swift todo sandbox: package target wiring for CLI test coverage",
        issue_body=(
            "Required code outputs:\n"
            "- e2e-smoke/swift/Package.swift\n"
            "- e2e-smoke/swift/Tests/FlowHealerAddTests/AddTests.swift\n\n"
            "Validation:\n"
            "- cd e2e-smoke/swift && swift test\n"
        ),
    )

    assert spec.output_targets == (
        "e2e-smoke/swift/Package.swift",
        "e2e-smoke/swift/Tests/FlowHealerAddTests/AddTests.swift",
    )


def test_is_code_path_recognizes_go() -> None:
    assert _is_code_path("cmd/server/main.go") is True


def test_is_code_path_recognizes_rust() -> None:
    assert _is_code_path("src/lib.rs") is True


def test_is_code_path_recognizes_java() -> None:
    assert _is_code_path("src/main/java/App.java") is True


def test_is_code_path_recognizes_c_cpp() -> None:
    assert _is_code_path("src/util.c") is True
    assert _is_code_path("src/util.cpp") is True
    assert _is_code_path("include/util.h") is True
    assert _is_code_path("include/util.hpp") is True


def test_is_code_path_recognizes_swift_scala_kotlin() -> None:
    assert _is_code_path("Sources/App.swift") is True
    assert _is_code_path("src/main/scala/Main.scala") is True
    assert _is_code_path("src/main/kotlin/Main.kt") is True


def test_is_code_path_recognizes_sql() -> None:
    assert _is_code_path("supabase/migrations/20260302101500_schema.sql") is True
