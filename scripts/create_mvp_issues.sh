#!/usr/bin/env bash
# Creates 80 healer:ready issues in batches of 10 with a sleep between batches.
# Usage: bash scripts/create_mvp_issues.sh
set -euo pipefail

REPO="dkyazzentwatwa/flow-healer"
LABEL="healer:ready"
SLEEP_SECONDS=4

create_issue() {
  local title="$1"
  local body="$2"
  gh issue create --repo "$REPO" --title "$title" --label "$LABEL" --body "$body"
  sleep 0.5
}

batch() {
  local n="$1"
  echo "=== Batch $n ==="
}

# ─── Batch 1: Class B easy doc/config fixes ──────────────────────────────────
batch 1

create_issue \
  "Add missing newline at end of SECURITY.md" \
  "$(cat <<'EOF'
SECURITY.md is missing a trailing newline, which causes diff noise on some editors.

## Required code outputs

- `SECURITY.md` (add single trailing newline)

## Validation command

python3 -c "content = open('SECURITY.md').read(); assert content.endswith('\n'), 'Missing trailing newline'"
EOF
)"

create_issue \
  "Add Python 3.12 to CI test matrix" \
  "$(cat <<'EOF'
The project supports Python 3.11+ but CI only tests 3.11. Add 3.12 to catch any compatibility issues early.

## Required code outputs

- `.github/workflows/ci.yml` (add python-version: ["3.11", "3.12"] matrix)

## Validation command

echo "CI config updated"
EOF
)"

create_issue \
  "Add py.typed marker for PEP 561 compliance" \
  "$(cat <<'EOF'
Adding a `py.typed` marker file allows mypy and other type checkers to recognize this package as typed.

## Required code outputs

- `src/flow_healer/py.typed` (create empty marker file)
- `pyproject.toml` (add `package-data = {"flow_healer" = ["py.typed"]}` under [tool.setuptools])

## Validation command

python3 -c "import importlib.resources; print('ok')"
EOF
)"

create_issue \
  "Add .editorconfig for consistent formatting across editors" \
  "$(cat <<'EOF'
An .editorconfig file ensures consistent indentation and newline handling across different editors without a linter.

## Required code outputs

- `.editorconfig` (create with: root=true, Python=4-space indent, utf-8, lf line endings)

## Validation command

echo "editorconfig created"
EOF
)"

create_issue \
  "Add project URLs to pyproject.toml" \
  "$(cat <<'EOF'
pyproject.toml is missing [project.urls] which PyPI uses to link to the repo and issue tracker.

## Required code outputs

- `pyproject.toml` (add [project.urls] section with Homepage, Repository, Issues)

## Validation command

python3 -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb')); assert 'urls' in d.get('project', {}), 'Missing urls'"
EOF
)"

create_issue \
  "Add CHANGELOG.md with initial skeleton" \
  "$(cat <<'EOF'
A CHANGELOG makes it easier for users to understand what changed between versions. Add an initial skeleton following Keep a Changelog format.

## Required code outputs

- `CHANGELOG.md` (create with [Unreleased] section and initial v0.1.0 entry noting the MVP baseline)

## Validation command

echo "CHANGELOG created"
EOF
)"

create_issue \
  "Pin dev dependency versions in pyproject.toml" \
  "$(cat <<'EOF'
Dev dependencies in pyproject.toml are unpinned, which can cause unexpected breakage on fresh installs. Pin them to minimum compatible versions.

## Required code outputs

- `pyproject.toml` (add minimum version pins to dev dependencies: pytest>=8.0, textual>=0.70)

## Validation command

python3 -c "import tomllib; deps = str(tomllib.load(open('pyproject.toml','rb'))); assert '>=' in deps"
EOF
)"

create_issue \
  "Add GitHub PR template" \
  "$(cat <<'EOF'
A pull request template helps contributors include the right context when opening PRs.

## Required code outputs

- `.github/PULL_REQUEST_TEMPLATE.md` (create with: Summary, Test plan, Checklist sections)

## Validation command

echo "PR template created"
EOF
)"

create_issue \
  "Add GitHub bug report issue template" \
  "$(cat <<'EOF'
A structured bug report template makes it easier to reproduce issues.

## Required code outputs

- `.github/ISSUE_TEMPLATE/bug_report.md` (create with: Describe the bug, Steps to reproduce, Expected/actual behavior, Environment sections)

## Validation command

echo "Bug report template created"
EOF
)"

create_issue \
  "Add GitHub feature request issue template" \
  "$(cat <<'EOF'
A feature request template guides contributors toward actionable proposals.

## Required code outputs

- `.github/ISSUE_TEMPLATE/feature_request.md` (create with: Is your feature request related to a problem? Describe the solution, Alternatives considered sections)

## Validation command

echo "Feature request template created"
EOF
)"

sleep "$SLEEP_SECONDS"

# ─── Batch 2: Class A easy test additions ────────────────────────────────────
batch 2

create_issue \
  "test_tui.py: add test for _colored_state with unknown state string" \
  "$(cat <<'EOF'
`_colored_state` in tui.py falls back to 'white' for unknown states but this path has no test coverage.

## Required code outputs

- `tests/test_tui.py` (add test_colored_state_unknown_returns_white)

## Validation command

pytest tests/test_tui.py::test_colored_state_unknown_returns_white -v
EOF
)"

create_issue \
  "test_healer_runner.py: add test for EvidenceBundle with reviewer_summary" \
  "$(cat <<'EOF'
`EvidenceBundle` has an optional `reviewer_summary` field but it is not tested when non-empty.

## Required code outputs

- `tests/test_healer_runner.py` (add test_evidence_bundle_with_reviewer_summary)

## Validation command

pytest tests/test_healer_runner.py::test_evidence_bundle_with_reviewer_summary -v
EOF
)"

create_issue \
  "test_healer_runner.py: add test for _risk_level_from_result at medium boundary" \
  "$(cat <<'EOF'
The boundary between 'low' and 'medium' risk (50 diff_lines) has no test. Add a test for exactly 51 lines.

## Required code outputs

- `tests/test_healer_runner.py` (add test_risk_level_medium_at_boundary)

## Validation command

pytest tests/test_healer_runner.py::test_risk_level_medium_at_boundary -v
EOF
)"

create_issue \
  "test_tui.py: add test for TAB_BLOCKED equals 'tab-blocked'" \
  "$(cat <<'EOF'
TAB_BLOCKED constant is defined but there is no assertion on its exact string value in the test suite.

## Required code outputs

- `tests/test_tui.py` (add test_tab_blocked_constant_value)

## Validation command

pytest tests/test_tui.py::test_tab_blocked_constant_value -v
EOF
)"

create_issue \
  "test_cli.py: add test for format_doctor_rows_plain with repo_name field" \
  "$(cat <<'EOF'
Some doctor rows use 'repo_name' instead of 'repo' as the key. The plain formatter should handle both, but this case is untested.

## Required code outputs

- `tests/test_cli.py` (add test_format_doctor_rows_plain_uses_repo_name_fallback)

## Validation command

pytest tests/test_cli.py::test_format_doctor_rows_plain_uses_repo_name_fallback -v
EOF
)"

create_issue \
  "test_healer_runner.py: add test for build_evidence_bundle with verifier_summary" \
  "$(cat <<'EOF'
`build_evidence_bundle` accepts an optional `verifier_summary` kwarg but no test verifies it is passed through to the returned `EvidenceBundle`.

## Required code outputs

- `tests/test_healer_runner.py` (add test_build_evidence_bundle_passes_verifier_summary)

## Validation command

pytest tests/test_healer_runner.py::test_build_evidence_bundle_passes_verifier_summary -v
EOF
)"

create_issue \
  "test_tui.py: add test for _format_attempt_row_for_display with None failure_class" \
  "$(cat <<'EOF'
`_format_attempt_row_for_display` uses `row.get('failure_class')` which may return None. Ensure the function handles None without raising.

## Required code outputs

- `tests/test_tui.py` (add test_format_attempt_row_handles_none_failure_class)

## Validation command

pytest tests/test_tui.py::test_format_attempt_row_handles_none_failure_class -v
EOF
)"

create_issue \
  "test_healer_runner.py: add test for _operator_failure_reason with connector_runtime_error" \
  "$(cat <<'EOF'
`connector_runtime_error` is a known internal failure class that should map to `no_confident_fix`, but it is not in the existing test assertions.

## Required code outputs

- `tests/test_healer_runner.py` (add assertion for connector_runtime_error in test_operator_failure_reason_maps_internal_codes or add a new focused test)

## Validation command

pytest tests/test_healer_runner.py -k "failure_reason" -v
EOF
)"

create_issue \
  "test_cli.py: add test for format_doctor_rows_plain with empty preflight_summary" \
  "$(cat <<'EOF'
If `preflight_summary` is absent from a doctor row, `format_doctor_rows_plain` should not crash. Add a test for this case.

## Required code outputs

- `tests/test_cli.py` (add test_format_doctor_rows_plain_missing_preflight_summary)

## Validation command

pytest tests/test_cli.py::test_format_doctor_rows_plain_missing_preflight_summary -v
EOF
)"

create_issue \
  "test_healer_runner.py: add test for EvidenceBundle.diff_summary format string" \
  "$(cat <<'EOF'
`build_evidence_bundle` constructs a `diff_summary` string from `diff_files` and `diff_lines`. No test currently asserts the format of this string.

## Required code outputs

- `tests/test_healer_runner.py` (add test_build_evidence_bundle_diff_summary_format)

## Validation command

pytest tests/test_healer_runner.py::test_build_evidence_bundle_diff_summary_format -v
EOF
)"

sleep "$SLEEP_SECONDS"

# ─── Batch 3: Class B medium CI/config improvements ──────────────────────────
batch 3

create_issue \
  "Add pip caching to GitHub Actions CI workflow" \
  "$(cat <<'EOF'
CI does not cache pip dependencies, causing slow installs on every run. Add cache-dependency-path targeting pyproject.toml.

## Required code outputs

- `.github/workflows/ci.yml` (add cache: pip to the setup-python step)

## Validation command

echo "CI cache step added"
EOF
)"

create_issue \
  "Add dependabot config for GitHub Actions auto-updates" \
  "$(cat <<'EOF'
GitHub Actions versions in workflows are pinned but not auto-updated. Add a dependabot config to keep them current.

## Required code outputs

- `.github/dependabot.yml` (create with package-ecosystem: github-actions, directory: /, schedule: weekly)

## Validation command

echo "dependabot config created"
EOF
)"

create_issue \
  "Add .github/CODEOWNERS for review routing" \
  "$(cat <<'EOF'
A CODEOWNERS file routes review requests to the right people automatically when PRs touch specific paths.

## Required code outputs

- `.github/CODEOWNERS` (create with * @dkyazzentwatwa and docs/ @dkyazzentwatwa)

## Validation command

echo "CODEOWNERS created"
EOF
)"

create_issue \
  "Add Makefile with common dev targets" \
  "$(cat <<'EOF'
A Makefile with standard targets (test, install, lint, clean) reduces cognitive overhead for contributors.

## Required code outputs

- `Makefile` (create with targets: install, test, test-fast, clean, doctor)

## Validation command

make --dry-run test
EOF
)"

create_issue \
  "Add .python-version file for pyenv users" \
  "$(cat <<'EOF'
Pyenv users need a .python-version file to automatically switch to the correct Python version.

## Required code outputs

- `.python-version` (create with content: 3.11)

## Validation command

echo "3.11" | grep -q "3.11" && echo "ok"
EOF
)"

create_issue \
  "Add mypy configuration to pyproject.toml" \
  "$(cat <<'EOF'
mypy is not configured, so running it produces noisy output. Add a basic [tool.mypy] section that at minimum sets python_version and ignore_missing_imports.

## Required code outputs

- `pyproject.toml` (add [tool.mypy] section with python_version = "3.11" and ignore_missing_imports = true)

## Validation command

python3 -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb')); assert 'mypy' in d.get('tool', {})"
EOF
)"

create_issue \
  "Add tox.ini for multi-version test orchestration" \
  "$(cat <<'EOF'
tox allows running tests against multiple Python versions in a standard way. Add a basic tox.ini targeting 3.11 and 3.12.

## Required code outputs

- `tox.ini` (create with [tox] envlist=py311,py312 and [testenv] deps=.[dev] commands=pytest)

## Validation command

echo "tox.ini created"
EOF
)"

create_issue \
  "Add pytest-cov to dev dependencies and coverage config" \
  "$(cat <<'EOF'
No test coverage reporting is configured. Add pytest-cov to dev deps and a [tool.coverage] section to pyproject.toml.

## Required code outputs

- `pyproject.toml` (add pytest-cov to dev deps; add [tool.coverage.run] with source = ["flow_healer"])

## Validation command

python3 -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb')); assert 'coverage' in d.get('tool', {})"
EOF
)"

create_issue \
  "Add pre-commit configuration" \
  "$(cat <<'EOF'
A pre-commit config with basic hooks (trailing whitespace, end-of-file fixer, check-yaml) helps keep the repo tidy without a full linter.

## Required code outputs

- `.pre-commit-config.yaml` (create with repos: pre-commit-hooks for trailing-whitespace, end-of-file-fixer, check-yaml, check-toml)

## Validation command

echo "pre-commit config created"
EOF
)"

create_issue \
  "Add GitHub Actions workflow for PR test runs" \
  "$(cat <<'EOF'
There is no GitHub Actions workflow that runs tests automatically on pull requests. Add one so PRs get automatic test feedback.

## Required code outputs

- `.github/workflows/pr-tests.yml` (create workflow: trigger on pull_request to main, run pytest on ubuntu-latest python 3.11)

## Validation command

echo "PR test workflow created"
EOF
)"

sleep "$SLEEP_SECONDS"

# ─── Batch 4: Class A medium test improvements ───────────────────────────────
batch 4

create_issue \
  "test_healer_runner.py: parametrize _operator_failure_reason for all 6 output codes" \
  "$(cat <<'EOF'
The failure reason mapping test checks many individual codes but is not parametrized. Refactor to use @pytest.mark.parametrize for cleaner coverage of all 6 operator labels.

## Required code outputs

- `tests/test_healer_runner.py` (add test_operator_failure_reason_parametrized covering all 6 output codes)

## Validation command

pytest tests/test_healer_runner.py::test_operator_failure_reason_parametrized -v
EOF
)"

create_issue \
  "test_healer_runner.py: add test for build_evidence_bundle with zero diff_lines" \
  "$(cat <<'EOF'
When `diff_lines` is 0 (e.g. a file was renamed but content unchanged), the risk level and diff_summary should still be computed without error.

## Required code outputs

- `tests/test_healer_runner.py` (add test_build_evidence_bundle_zero_diff_lines)

## Validation command

pytest tests/test_healer_runner.py::test_build_evidence_bundle_zero_diff_lines -v
EOF
)"

create_issue \
  "test_tui.py: add test for FlowHealerApp has action_pause_repo method" \
  "$(cat <<'EOF'
`action_pause_repo` was added as a key action but no test confirms the method is defined on the app class.

## Required code outputs

- `tests/test_tui.py` (add test_app_has_action_pause_repo_method)

## Validation command

pytest tests/test_tui.py::test_app_has_action_pause_repo_method -v
EOF
)"

create_issue \
  "test_tui.py: add test for FlowHealerApp has action_open_pr method" \
  "$(cat <<'EOF'
`action_open_pr` handles the `o` keybinding but no test confirms the method exists on the class.

## Required code outputs

- `tests/test_tui.py` (add test_app_has_action_open_pr_method)

## Validation command

pytest tests/test_tui.py::test_app_has_action_open_pr_method -v
EOF
)"

create_issue \
  "test_cli.py: add test for format_doctor_rows_plain with multiple repos" \
  "$(cat <<'EOF'
`format_doctor_rows_plain` is only tested with a single repo row. Add a test with two repos to confirm the separator and per-repo sections render correctly.

## Required code outputs

- `tests/test_cli.py` (add test_format_doctor_rows_plain_multiple_repos)

## Validation command

pytest tests/test_cli.py::test_format_doctor_rows_plain_multiple_repos -v
EOF
)"

create_issue \
  "test_healer_runner.py: add test for _risk_level_from_result with exactly 200 lines (boundary)" \
  "$(cat <<'EOF'
The boundary between 'medium' and 'high' risk is `diff_lines > 200`. A diff of exactly 200 lines should return 'medium', but this boundary is untested.

## Required code outputs

- `tests/test_healer_runner.py` (add test_risk_level_medium_at_200_lines)

## Validation command

pytest tests/test_healer_runner.py::test_risk_level_medium_at_200_lines -v
EOF
)"

create_issue \
  "test_tui.py: add test for _format_attempt_row_for_display with extra unknown fields" \
  "$(cat <<'EOF'
`_format_attempt_row_for_display` uses `**row` spread. Verify that unknown extra fields in the input row are preserved in the output dict.

## Required code outputs

- `tests/test_tui.py` (add test_format_attempt_row_preserves_extra_fields)

## Validation command

pytest tests/test_tui.py::test_format_attempt_row_preserves_extra_fields -v
EOF
)"

create_issue \
  "test_healer_runner.py: add test for _operator_failure_reason returns validation_failed for unknown codes" \
  "$(cat <<'EOF'
Unknown internal failure codes should fall back to `validation_failed`. This fallback is not explicitly tested.

## Required code outputs

- `tests/test_healer_runner.py` (add test_operator_failure_reason_unknown_code_falls_back_to_validation_failed)

## Validation command

pytest tests/test_healer_runner.py::test_operator_failure_reason_unknown_code_falls_back_to_validation_failed -v
EOF
)"

create_issue \
  "test_cli.py: add test for doctor command --no-plain outputs JSON" \
  "$(cat <<'EOF'
The `--no-plain` flag should bypass `format_doctor_rows_plain` and output raw JSON. This path is not covered by the current tests.

## Required code outputs

- `tests/test_cli.py` (add test that verifies --no-plain flag causes JSON output rather than plain text)

## Validation command

pytest tests/test_cli.py -k "no_plain" -v
EOF
)"

create_issue \
  "test_healer_runner.py: add test for EvidenceBundle is frozen (immutable)" \
  "$(cat <<'EOF'
`EvidenceBundle` is decorated with `frozen=True` but no test attempts mutation to confirm the dataclass is truly immutable.

## Required code outputs

- `tests/test_healer_runner.py` (add test_evidence_bundle_is_immutable that attempts attribute assignment and asserts FrozenInstanceError)

## Validation command

pytest tests/test_healer_runner.py::test_evidence_bundle_is_immutable -v
EOF
)"

sleep "$SLEEP_SECONDS"

# ─── Batch 5: Class B doc improvements ───────────────────────────────────────
batch 5

create_issue \
  "docs/usage.md: update CLI examples to include tui and doctor commands" \
  "$(cat <<'EOF'
docs/usage.md has CLI examples but does not show the `tui` or `doctor --plain` commands added in the MVP.

## Required code outputs

- `docs/usage.md` (add examples for: flow-healer tui, flow-healer doctor, flow-healer doctor --no-plain)

## Validation command

grep -q "flow-healer tui" docs/usage.md && echo "ok"
EOF
)"

create_issue \
  "docs/operator-workflow.md: add section on exporting data with flow-healer export" \
  "$(cat <<'EOF'
The operator workflow doc covers TUI and CLI status commands but does not mention `flow-healer export` for getting CSV/JSONL data.

## Required code outputs

- `docs/operator-workflow.md` (add Export section with: flow-healer export --formats csv,jsonl and what the output contains)

## Validation command

grep -q "export" docs/operator-workflow.md && echo "ok"
EOF
)"

create_issue \
  "docs/mvp.md: add section on what a successful PR body looks like" \
  "$(cat <<'EOF'
Operators reviewing a draft PR need to know what to expect in the PR body. Add a section describing the PR body format: evidence bundle fields, reviewer summary, risk level.

## Required code outputs

- `docs/mvp.md` (add PR Body Format section with field descriptions)

## Validation command

grep -q "PR Body" docs/mvp.md && echo "ok"
EOF
)"

create_issue \
  "docs/safe-scope.md: add section on how to write a good Validation command" \
  "$(cat <<'EOF'
New users often write weak validation commands (e.g. just `echo ok`). Add a section with examples of strong vs weak validation commands and when each is appropriate.

## Required code outputs

- `docs/safe-scope.md` (add Validation Command Guidelines section with good/bad examples)

## Validation command

grep -q "Validation Command" docs/safe-scope.md && echo "ok"
EOF
)"

create_issue \
  "docs/onboarding.md: add section on what to do after the first successful PR" \
  "$(cat <<'EOF'
The onboarding guide ends at Step 6 (review in TUI) but does not tell users what to do next — how to add more repos, tune config, set up serve mode, etc.

## Required code outputs

- `docs/onboarding.md` (expand Next Steps section with: adding more repos, setting up serve mode, configuring retry budget, enabling scanning)

## Validation command

grep -q "serve mode" docs/onboarding.md && echo "ok"
EOF
)"

create_issue \
  "docs/operator-workflow.md: add section on what happens when circuit breaker trips" \
  "$(cat <<'EOF'
The circuit breaker section mentions it exists but does not explain step-by-step how to diagnose and reset it.

## Required code outputs

- `docs/operator-workflow.md` (expand Circuit Breaker section with: how to diagnose via doctor, how to reset via resume, what failure_rate means)

## Validation command

grep -q "failure_rate" docs/operator-workflow.md && echo "ok"
EOF
)"

create_issue \
  "docs/mvp.md: add link to safe-scope.md from the issue classes section" \
  "$(cat <<'EOF'
The Issue Classes section in docs/mvp.md describes Class A and B but does not link to docs/safe-scope.md where the full contract is defined.

## Required code outputs

- `docs/mvp.md` (add cross-reference link to docs/safe-scope.md in the Issue Classes section)

## Validation command

grep -q "safe-scope" docs/mvp.md && echo "ok"
EOF
)"

create_issue \
  "docs/README.md: add links to new MVP docs (mvp.md, safe-scope.md, onboarding.md, operator-workflow.md)" \
  "$(cat <<'EOF'
docs/README.md is the canonical documentation index but does not list the new MVP docs added in the baseline.

## Required code outputs

- `docs/README.md` (add entries for: docs/mvp.md, docs/safe-scope.md, docs/onboarding.md, docs/operator-workflow.md)

## Validation command

grep -q "onboarding.md" docs/README.md && echo "ok"
EOF
)"

create_issue \
  "docs/dashboard.md: update TUI section to reflect new tab structure" \
  "$(cat <<'EOF'
docs/dashboard.md describes the TUI but does not mention the new tab constants (Review Queue, Blocked, Repo Health, History) added in the MVP.

## Required code outputs

- `docs/dashboard.md` (update TUI section to describe the four MVP tabs)

## Validation command

grep -q "Review Queue" docs/dashboard.md && echo "ok"
EOF
)"

create_issue \
  "docs/architecture.md: add EvidenceBundle to the data flow description" \
  "$(cat <<'EOF'
docs/architecture.md describes the healing pipeline but does not mention the EvidenceBundle dataclass introduced in the MVP.

## Required code outputs

- `docs/architecture.md` (add EvidenceBundle to the data flow section, noting it feeds PR body and TUI detail pane)

## Validation command

grep -q "EvidenceBundle" docs/architecture.md && echo "ok"
EOF
)"

sleep "$SLEEP_SECONDS"

# ─── Batch 6: Class A medium test coverage ───────────────────────────────────
batch 6

create_issue \
  "test_healer_runner.py: add test for build_evidence_bundle failure_reason for scope_violation input" \
  "$(cat <<'EOF'
When `HealerRunResult.failure_class` is `scope_violation`, `build_evidence_bundle` should set `failure_reason` to `scope_violation`. This specific mapping is not tested end-to-end through the builder.

## Required code outputs

- `tests/test_healer_runner.py` (add test_build_evidence_bundle_scope_violation_failure_reason)

## Validation command

pytest tests/test_healer_runner.py::test_build_evidence_bundle_scope_violation_failure_reason -v
EOF
)"

create_issue \
  "test_healer_runner.py: add test for build_evidence_bundle with large diff sets risk to high" \
  "$(cat <<'EOF'
When diff_lines > 200, `build_evidence_bundle` should set `risk_level` to 'high'. No test verifies this through the builder function.

## Required code outputs

- `tests/test_healer_runner.py` (add test_build_evidence_bundle_large_diff_is_high_risk)

## Validation command

pytest tests/test_healer_runner.py::test_build_evidence_bundle_large_diff_is_high_risk -v
EOF
)"

create_issue \
  "test_tui.py: add test that TAB_HISTORY equals 'tab-history'" \
  "$(cat <<'EOF'
TAB_HISTORY constant is defined but no test asserts its exact value.

## Required code outputs

- `tests/test_tui.py` (add test_tab_history_constant_value)

## Validation command

pytest tests/test_tui.py::test_tab_history_constant_value -v
EOF
)"

create_issue \
  "test_tui.py: add test that TAB_REPO_HEALTH equals 'tab-repo-health'" \
  "$(cat <<'EOF'
TAB_REPO_HEALTH constant is defined but no test asserts its exact value.

## Required code outputs

- `tests/test_tui.py` (add test_tab_repo_health_constant_value)

## Validation command

pytest tests/test_tui.py::test_tab_repo_health_constant_value -v
EOF
)"

create_issue \
  "test_healer_runner.py: add test for EvidenceBundle files_changed is a list" \
  "$(cat <<'EOF'
`EvidenceBundle.files_changed` should always be a list, even when `HealerRunResult.diff_paths` is None or empty. Add a test for the empty case.

## Required code outputs

- `tests/test_healer_runner.py` (add test_evidence_bundle_files_changed_is_list_when_diff_paths_empty)

## Validation command

pytest tests/test_healer_runner.py::test_evidence_bundle_files_changed_is_list_when_diff_paths_empty -v
EOF
)"

create_issue \
  "test_cli.py: add test for format_doctor_rows_plain with git_ok=False shows correct hint" \
  "$(cat <<'EOF'
When `git_ok` is False, the plain doctor output should show a remediation hint mentioning the `path:` config field. This specific case is not tested.

## Required code outputs

- `tests/test_cli.py` (add test_format_doctor_rows_plain_git_not_ok_shows_path_hint)

## Validation command

pytest tests/test_cli.py::test_format_doctor_rows_plain_git_not_ok_shows_path_hint -v
EOF
)"

create_issue \
  "test_healer_runner.py: add test for build_evidence_bundle with no_confident_fix from no_workspace_change" \
  "$(cat <<'EOF'
`no_workspace_change:empty_diff` should map to `no_confident_fix` through `build_evidence_bundle`. Test this end-to-end.

## Required code outputs

- `tests/test_healer_runner.py` (add test_build_evidence_bundle_no_workspace_change_maps_to_no_confident_fix)

## Validation command

pytest tests/test_healer_runner.py::test_build_evidence_bundle_no_workspace_change_maps_to_no_confident_fix -v
EOF
)"

create_issue \
  "test_tui.py: add test for _format_attempt_row_for_display with repo_blocked failure class" \
  "$(cat <<'EOF'
`circuit_breaker_open` should display as `repo_blocked` in the TUI. Add a specific test for this mapping through `_format_attempt_row_for_display`.

## Required code outputs

- `tests/test_tui.py` (add test_format_attempt_row_circuit_breaker_open_maps_to_repo_blocked)

## Validation command

pytest tests/test_tui.py::test_format_attempt_row_circuit_breaker_open_maps_to_repo_blocked -v
EOF
)"

create_issue \
  "test_healer_runner.py: add test for _risk_level_from_result with 5 diff files (high)" \
  "$(cat <<'EOF'
Five diff files (> 4 threshold) should yield 'high' risk, but the only high-risk test uses test failures. Add a diff-file-count-based test.

## Required code outputs

- `tests/test_healer_runner.py` (add test_risk_level_high_from_many_files)

## Validation command

pytest tests/test_healer_runner.py::test_risk_level_high_from_many_files -v
EOF
)"

create_issue \
  "test_cli.py: add test for format_doctor_rows_plain connector_found=False shows install hint" \
  "$(cat <<'EOF'
When `connector_found` is False, the plain doctor output should show an install hint. This case is not explicitly tested.

## Required code outputs

- `tests/test_cli.py` (add test_format_doctor_rows_plain_connector_not_found_shows_install_hint)

## Validation command

pytest tests/test_cli.py::test_format_doctor_rows_plain_connector_not_found_shows_install_hint -v
EOF
)"

sleep "$SLEEP_SECONDS"

# ─── Batch 7: Mixed medium difficulty ────────────────────────────────────────
batch 7

create_issue \
  "Add structured logging to healer_runner.py for evidence bundle creation" \
  "$(cat <<'EOF'
When `build_evidence_bundle` is called, no log message is emitted. Adding a DEBUG-level log with issue_id, repo, and risk_level would help operators correlate logs with TUI state.

## Required code outputs

- `src/flow_healer/healer_runner.py` (add logger.debug call in build_evidence_bundle with issue_id, repo, risk_level fields)

## Validation command

pytest tests/test_healer_runner.py -v
EOF
)"

create_issue \
  "Add __repr__ to EvidenceBundle for readable debug output" \
  "$(cat <<'EOF'
`EvidenceBundle` is a frozen dataclass but Python's auto-generated `__repr__` for dataclasses with `slots=True` can be verbose. Add a concise custom `__repr__` showing issue_id, repo, risk_level, and validation_passed.

## Required code outputs

- `src/flow_healer/healer_runner.py` (add __repr__ to EvidenceBundle)
- `tests/test_healer_runner.py` (add test_evidence_bundle_repr_is_concise)

## Validation command

pytest tests/test_healer_runner.py::test_evidence_bundle_repr_is_concise -v
EOF
)"

create_issue \
  "Add to_dict() method to EvidenceBundle for serialization" \
  "$(cat <<'EOF'
`EvidenceBundle` needs to be serializable to JSON for inclusion in PR bodies. Add a `to_dict()` method that returns all fields as a plain dict.

## Required code outputs

- `src/flow_healer/healer_runner.py` (add to_dict() method to EvidenceBundle)
- `tests/test_healer_runner.py` (add test_evidence_bundle_to_dict_returns_all_fields)

## Validation command

pytest tests/test_healer_runner.py::test_evidence_bundle_to_dict_returns_all_fields -v
EOF
)"

create_issue \
  "Add format_doctor_rows_plain to __all__ in cli.py for public API clarity" \
  "$(cat <<'EOF'
`format_doctor_rows_plain` is a public-facing helper but is not listed in `__all__` (or `__all__` doesn't exist). Make the public API explicit.

## Required code outputs

- `src/flow_healer/cli.py` (add __all__ = ['format_doctor_rows_plain', 'main', 'build_parser'] or equivalent)
- `tests/test_cli.py` (add test_format_doctor_rows_plain_importable_from_cli)

## Validation command

pytest tests/test_cli.py::test_format_doctor_rows_plain_importable_from_cli -v
EOF
)"

create_issue \
  "docs/safe-scope.md: add table summarizing scope rules by file extension" \
  "$(cat <<'EOF'
The safe-scope doc lists allowed files in text blocks but a quick-reference table by extension would be faster to scan.

## Required code outputs

- `docs/safe-scope.md` (add Quick Reference table: extension → allowed class → notes)

## Validation command

grep -q "Quick Reference" docs/safe-scope.md && echo "ok"
EOF
)"

create_issue \
  "Add type annotations to format_doctor_rows_plain in cli.py" \
  "$(cat <<'EOF'
`format_doctor_rows_plain` is missing type annotations on its parameter and return value, inconsistent with the rest of the module.

## Required code outputs

- `src/flow_healer/cli.py` (add `rows: list[dict[str, object]]` and `-> str` annotations to format_doctor_rows_plain)

## Validation command

pytest tests/test_cli.py -v
EOF
)"

create_issue \
  "Add test for _operator_failure_reason with review_required maps correctly" \
  "$(cat <<'EOF'
`review_required` is one of the 6 operator codes but the mapping test may not cover it explicitly. Ensure it is covered.

## Required code outputs

- `tests/test_healer_runner.py` (add or verify assertion: _operator_failure_reason('review_required') == 'review_required')

## Validation command

pytest tests/test_healer_runner.py -k "failure_reason" -v
EOF
)"

create_issue \
  "docs/demo-repo-setup.md: add section on verifying issues were rejected correctly" \
  "$(cat <<'EOF'
The demo repo setup guide describes seeding intentional reject issues but does not explain how to verify they were rejected (what comment Flow Healer posts, what state they end up in).

## Required code outputs

- `docs/demo-repo-setup.md` (add Verifying Rejections section: what needs_clarification and scope_violation look like on the GitHub issue)

## Validation command

grep -q "Verifying Rejections" docs/demo-repo-setup.md && echo "ok"
EOF
)"

create_issue \
  "Add validation that EvidenceBundle.risk_level is one of the three valid values" \
  "$(cat <<'EOF'
`_risk_level_from_result` returns 'low', 'medium', or 'high' but nothing validates this at the EvidenceBundle boundary. Add a `__post_init__` check.

Note: frozen dataclasses with slots=True do not support __post_init__ directly — use a module-level validator function called in build_evidence_bundle instead.

## Required code outputs

- `src/flow_healer/healer_runner.py` (add _validate_evidence_bundle(bundle) that raises ValueError if risk_level not in {'low', 'medium', 'high'}, call it in build_evidence_bundle)
- `tests/test_healer_runner.py` (add test_build_evidence_bundle_rejects_invalid_risk_level)

## Validation command

pytest tests/test_healer_runner.py::test_build_evidence_bundle_rejects_invalid_risk_level -v
EOF
)"

create_issue \
  "Add test for format_doctor_rows_plain db_ok=False shows disk/permissions hint" \
  "$(cat <<'EOF'
When `db_ok` is False, the plain doctor output should show a hint about disk space and permissions. This case is not explicitly tested.

## Required code outputs

- `tests/test_cli.py` (add test_format_doctor_rows_plain_db_not_ok_shows_permissions_hint)

## Validation command

pytest tests/test_cli.py::test_format_doctor_rows_plain_db_not_ok_shows_permissions_hint -v
EOF
)"

sleep "$SLEEP_SECONDS"

# ─── Batch 8: Harder / multi-file issues ─────────────────────────────────────
batch 8

create_issue \
  "Wire EvidenceBundle into healer_loop.py PR body generation" \
  "$(cat <<'EOF'
`EvidenceBundle` is built by `build_evidence_bundle` in healer_runner.py but is not yet wired into the PR body that healer_loop.py assembles. The PR body currently extracts fields ad-hoc.

Replace the ad-hoc field extraction in the PR body generation path with `bundle.to_dict()` (once to_dict() exists) or direct field access on the bundle.

## Required code outputs

- `src/flow_healer/healer_loop.py` (import EvidenceBundle; replace ad-hoc field access in _build_pr_body or equivalent with structured bundle access)
- `tests/test_healer_loop.py` (add test that PR body includes evidence fields from bundle)

## Validation command

pytest tests/test_healer_loop.py -k "pr_body" -v
EOF
)"

create_issue \
  "Add EvidenceBundle to TUI detail pane rendering" \
  "$(cat <<'EOF'
The TUI detail pane (tui_detail_lines) renders raw dict fields. When an attempt row includes evidence bundle fields (risk_level, validation_commands, validation_passed), surface them with friendly labels.

## Required code outputs

- `src/flow_healer/tui.py` (update tui_detail_lines to render risk_level, validation_passed, and files_changed with labels if present in the row)
- `tests/test_tui.py` (add test_tui_detail_lines_renders_evidence_bundle_fields)

## Validation command

pytest tests/test_tui.py::test_tui_detail_lines_renders_evidence_bundle_fields -v
EOF
)"

create_issue \
  "Add export of EvidenceBundle fields to telemetry_exports.py" \
  "$(cat <<'EOF'
`flow-healer export` produces CSV/JSONL from telemetry datasets but does not include evidence bundle fields (risk_level, files_changed, validation_passed, failure_reason) in the attempts dataset.

## Required code outputs

- `src/flow_healer/telemetry_exports.py` (add risk_level, validation_passed, failure_reason, files_changed_count columns to the attempts dataset export)
- `tests/test_telemetry_exports.py` (add test that exported attempts include risk_level field)

## Validation command

pytest tests/test_telemetry_exports.py -k "risk_level" -v
EOF
)"

create_issue \
  "Add TAB_REVIEW_QUEUE as default tab in FlowHealerApp compose()" \
  "$(cat <<'EOF'
`TAB_REVIEW_QUEUE` constant is defined but `compose()` in `FlowHealerApp` still uses the old tab layout. Update `compose()` to use `TabbedContent(initial=TAB_REVIEW_QUEUE)` as the top-level container, with Review Queue as the first tab.

This is a structural change — read the full compose() method before editing to understand all widget IDs referenced downstream.

## Required code outputs

- `src/flow_healer/tui.py` (update compose() to use TabbedContent with TAB_REVIEW_QUEUE as initial tab; move queue DataTable into Review Queue TabPane)
- `tests/test_tui.py` (add test that TAB_REVIEW_QUEUE is the initial tab)

## Validation command

pytest tests/test_tui.py -v
EOF
)"

create_issue \
  "Add structured PR body template using EvidenceBundle fields" \
  "$(cat <<'EOF'
PR bodies currently use ad-hoc string formatting. Create a `format_pr_body(bundle: EvidenceBundle, reviewer_body: str) -> str` function that renders a consistent Markdown PR body from an evidence bundle.

## Required code outputs

- `src/flow_healer/healer_runner.py` (add format_pr_body function)
- `tests/test_healer_runner.py` (add test_format_pr_body_includes_required_sections)

## Validation command

pytest tests/test_healer_runner.py::test_format_pr_body_includes_required_sections -v
EOF
)"

create_issue \
  "Add Blocked tab population to FlowHealerApp _populate_tables()" \
  "$(cat <<'EOF'
The `blocked-table` DataTable is set up with columns but the population logic in `_populate_tables()` is guarded by a try/except that silently skips it when the table is not in the compose layout. Once compose() is restructured (see linked issue), wire the blocked-table population properly.

## Required code outputs

- `src/flow_healer/tui.py` (remove try/except guard from blocked-table population in _populate_tables; ensure it populates from failed/blocked queue rows with operator failure codes)
- `tests/test_tui.py` (add test that _populate_tables fills blocked-table with failed rows)

## Validation command

pytest tests/test_tui.py -v
EOF
)"

create_issue \
  "Add Repo Health tab content to FlowHealerApp" \
  "$(cat <<'EOF'
The TAB_REPO_HEALTH tab is defined but has no content. Add a Static widget to Repo Health that renders: circuit breaker state, success rate (merged / total attempts), and the sparkline from StatsBar.

## Required code outputs

- `src/flow_healer/tui.py` (add repo-health-panel Static to Repo Health TabPane; add _update_repo_health_panel() method that reads from snapshot)
- `tests/test_tui.py` (add test_repo_health_panel_renders_circuit_breaker_state)

## Validation command

pytest tests/test_tui.py::test_repo_health_panel_renders_circuit_breaker_state -v
EOF
)"

create_issue \
  "Add History tab to FlowHealerApp with merged/closed issues" \
  "$(cat <<'EOF'
The TAB_HISTORY tab is defined but has no content. Add a DataTable to History that shows resolved issues (state: merged, closed, cancelled) with columns: issue #, title, resolution, date.

## Required code outputs

- `src/flow_healer/tui.py` (add history-table DataTable to History TabPane; populate from queue_rows where state in {merged, closed, cancelled})
- `tests/test_tui.py` (add test that history-table setup adds correct columns)

## Validation command

pytest tests/test_tui.py -v
EOF
)"

create_issue \
  "Add integration test for doctor --plain output end-to-end" \
  "$(cat <<'EOF'
The unit tests for `format_doctor_rows_plain` test the formatter in isolation. Add an integration-style test that calls `service.doctor_rows()` with a FakeStore and verifies the full plain output contains the repo name and at least one ✓ line.

## Required code outputs

- `tests/test_cli.py` (add test_doctor_plain_end_to_end_with_fake_service using FakeStore/FakeService)

## Validation command

pytest tests/test_cli.py::test_doctor_plain_end_to_end_with_fake_service -v
EOF
)"

create_issue \
  "Add snapshot regression test for EvidenceBundle serialization" \
  "$(cat <<'EOF'
Add a test that creates an EvidenceBundle with known field values and asserts the exact dict output of to_dict() (once it exists). This acts as a regression guard against accidental field changes.

## Required code outputs

- `tests/test_healer_runner.py` (add test_evidence_bundle_to_dict_snapshot that asserts exact keys and values)

## Validation command

pytest tests/test_healer_runner.py::test_evidence_bundle_to_dict_snapshot -v
EOF
)"

echo ""
echo "✓ All 80 issues created."
