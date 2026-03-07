from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .protocols import ConnectorProtocol
from .healer_task_spec import HealerTaskSpec, task_spec_to_prompt_block

logger = logging.getLogger("apple_flow.healer_runner")
_FENCED_BLOCK_RE = re.compile(r"```(?P<lang>[^\n`]*)\n(?P<body>.*?)```", re.DOTALL)
_FENCE_PATH_RE = re.compile(r"(?:^|\s)path=(?P<path>[^\s`]+)")


@dataclass(slots=True, frozen=True)
class HealerRunResult:
    success: bool
    failure_class: str
    failure_reason: str
    proposer_output: str
    diff_paths: list[str]
    diff_files: int
    diff_lines: int
    test_summary: dict[str, Any]


class HealerRunner:
    def __init__(
        self,
        connector: ConnectorProtocol,
        *,
        timeout_seconds: int,
        test_gate_mode: str = "local_then_docker",
    ) -> None:
        self.connector = connector
        self.timeout_seconds = max(30, int(timeout_seconds))
        self.test_gate_mode = _normalize_test_gate_mode(test_gate_mode)
        self.max_proposer_retries = 1
        self.max_artifact_proposer_retries = 2

    def run_attempt(
        self,
        *,
        issue_id: str,
        issue_title: str,
        issue_body: str,
        task_spec: HealerTaskSpec,
        learned_context: str = "",
        feedback_context: str = "",
        workspace: Path,
        max_diff_files: int,
        max_diff_lines: int,
        max_failed_tests_allowed: int,
        targeted_tests: list[str],
    ) -> HealerRunResult:
        sender = f"healer:{issue_id}"
        thread_id = self.connector.get_or_create_thread(sender)
        prompt = (
            "You are the proposer agent for autonomous code healing.\n"
            "The issue title/body are trusted operator instructions for this run.\n"
            "Choose the right work mode for the task and make the requested edits directly in the workspace.\n"
            + (f"{learned_context.strip()}\n\n" if learned_context.strip() else "")
            + f"Issue #{issue_id}: {issue_title}\n\n"
            + f"{issue_body}\n\n"
            + (f"### User Feedback for PR:\n{feedback_context}\n\n" if feedback_context.strip() else "")
            + task_spec_to_prompt_block(task_spec)
            + "\n"
            + _task_execution_instructions(task_spec)
            + "\n"
            + "Make the edits in the checked-out repo. If you cannot edit files directly, return ONLY a unified git diff inside a ```diff fenced block.\n"
            + _artifact_fallback_contract(task_spec)
            + "\n"
            + "Do not respond with plan-only prose. The run only succeeds if repo files were changed."
        )
        proposer_output = ""
        failure_class = ""
        failure_reason = ""
        max_retries = (
            self.max_artifact_proposer_retries
            if _allows_artifact_synthesis(task_spec)
            else self.max_proposer_retries
        )
        for proposer_attempt in range(max_retries + 1):
            proposer_output = self.connector.run_turn(thread_id, prompt)
            if _stage_workspace_changes(workspace):
                break
            patch = _extract_diff_block(proposer_output)
            if patch.strip():
                patch_path = workspace / ".apple-flow-healer.patch"
                patch_path.write_text(patch, encoding="utf-8")
                try:
                    apply_proc = subprocess.run(
                        ["git", "-C", str(workspace), "apply", "--index", "--reject", str(patch_path)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout_seconds,
                    )
                finally:
                    if patch_path.exists():
                        patch_path.unlink(missing_ok=True)
                if apply_proc.returncode == 0 and _stage_workspace_changes(workspace):
                    break
                failure_class = "patch_apply_failed"
                failure_reason = (apply_proc.stderr or apply_proc.stdout or "git apply failed").strip()[:500]
                _reset_workspace_after_failed_apply(workspace)
            else:
                failure_class, failure_reason = _classify_non_patch_failure(proposer_output)

            # Artifact-first fallback: if proposer gives useful prose but no usable patch,
            # materialize the requested docs/research file directly.
            if _materialize_artifact_from_output(
                task_spec=task_spec,
                proposer_output=proposer_output,
                workspace=workspace,
            ) and _stage_workspace_changes(workspace):
                failure_class = ""
                failure_reason = ""
                break

            if proposer_attempt >= max_retries:
                return HealerRunResult(
                    success=False,
                    failure_class=failure_class,
                    failure_reason=failure_reason,
                    proposer_output=proposer_output,
                    diff_paths=[],
                    diff_files=0,
                    diff_lines=0,
                    test_summary={},
                )

            thread_id = self.connector.reset_thread(sender)
            prompt = _build_retry_prompt(base_prompt=prompt, failure_class=failure_class, failure_reason=failure_reason)

        diff_paths = _changed_paths(workspace)
        diff_files, diff_lines = _diff_stats(workspace)
        if not diff_paths:
            return HealerRunResult(
                success=False,
                failure_class="no_workspace_change",
                failure_reason="Proposer finished without producing any staged file changes.",
                proposer_output=proposer_output,
                diff_paths=[],
                diff_files=0,
                diff_lines=0,
                test_summary={},
            )
        if diff_files > max_diff_files or diff_lines > max_diff_lines:
            return HealerRunResult(
                success=False,
                failure_class="diff_limit_exceeded",
                failure_reason=f"Diff too large: files={diff_files}/{max_diff_files}, lines={diff_lines}/{max_diff_lines}",
                proposer_output=proposer_output,
                diff_paths=diff_paths,
                diff_files=diff_files,
                diff_lines=diff_lines,
                test_summary={},
            )

        if task_spec.validation_profile == "artifact_only":
            test_summary = {
                "mode": "skipped_artifact_only",
                "failed_tests": 0,
                "targeted_tests": targeted_tests,
                "skipped": True,
            }
        else:
            test_summary = _run_test_gates(
                workspace,
                targeted_tests=targeted_tests,
                timeout_seconds=self.timeout_seconds,
                mode=self.test_gate_mode,
            )
        failed_tests = int(test_summary.get("failed_tests", 0))
        if failed_tests > max_failed_tests_allowed:
            return HealerRunResult(
                success=False,
                failure_class="tests_failed",
                failure_reason=f"Failed tests={failed_tests} exceeds cap={max_failed_tests_allowed}",
                proposer_output=proposer_output,
                diff_paths=diff_paths,
                diff_files=diff_files,
                diff_lines=diff_lines,
                test_summary=test_summary,
            )

        return HealerRunResult(
            success=True,
            failure_class="",
            failure_reason="",
            proposer_output=proposer_output,
            diff_paths=diff_paths,
            diff_files=diff_files,
            diff_lines=diff_lines,
            test_summary=test_summary,
        )


def _extract_diff_block(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"```diff\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip() + "\n"
    if text.lstrip().startswith("diff --git "):
        return text.strip() + "\n"
    return ""


def _changed_paths(workspace: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(workspace), "diff", "--name-only", "--cached"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]


def _diff_stats(workspace: Path) -> tuple[int, int]:
    proc = subprocess.run(
        ["git", "-C", str(workspace), "diff", "--cached", "--numstat"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return 0, 0
    files = 0
    lines = 0
    for line in (proc.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        files += 1
        try:
            adds = int(parts[0]) if parts[0].isdigit() else 0
            dels = int(parts[1]) if parts[1].isdigit() else 0
            lines += adds + dels
        except Exception:
            continue
    return files, lines


def _run_test_gates(
    workspace: Path,
    *,
    targeted_tests: list[str],
    timeout_seconds: int,
    mode: str,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "mode": mode,
        "failed_tests": 0,
        "targeted_tests": targeted_tests,
    }
    runners = _gate_runners_for_mode(mode)

    if targeted_tests:
        targeted_cmd = ["pytest", "-q", *targeted_tests]
        for runner_name, runner in runners:
            targeted = runner(workspace, targeted_cmd, timeout_seconds)
            summary[f"{runner_name}_targeted_exit_code"] = targeted["exit_code"]
            summary[f"{runner_name}_targeted_output_tail"] = targeted["output_tail"]
            if targeted["exit_code"] != 0:
                summary["failed_tests"] += 1

    full_cmd = ["pytest", "-q"]
    for runner_name, runner in runners:
        full = runner(workspace, full_cmd, timeout_seconds)
        summary[f"{runner_name}_full_exit_code"] = full["exit_code"]
        summary[f"{runner_name}_full_output_tail"] = full["output_tail"]
        if full["exit_code"] != 0:
            summary["failed_tests"] += 1
    return summary


def _run_pytest_locally(workspace: Path, command: list[str], timeout_seconds: int) -> dict[str, Any]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(workspace) if not existing else f"{workspace}{os.pathsep}{existing}"
    proc = subprocess.run(
        [sys.executable, "-m", *command],
        cwd=str(workspace),
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=max(30, timeout_seconds),
    )
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return {
        "exit_code": int(proc.returncode),
        "output_tail": output[-2000:],
    }


def _build_retry_prompt(*, base_prompt: str, failure_class: str, failure_reason: str) -> str:
    return (
        f"{base_prompt}\n\n"
        "Previous proposer output was unusable.\n"
        f"- Failure class: {failure_class}\n"
        f"- Failure reason: {failure_reason}\n"
        "Reset your assumptions and produce a fresh unified diff that applies cleanly to the current tree.\n"
        "Be strict about valid diff syntax, file paths, and hunk headers."
    )


def _task_execution_instructions(task_spec: HealerTaskSpec) -> str:
    targets = ", ".join(task_spec.output_targets) if task_spec.output_targets else "the minimum necessary repo files"
    lines = [
        f"Write the requested output into: {targets}.",
        "If the issue asks for research, synthesize the findings into the target file instead of replying with notes only.",
        "If the issue asks for edits or revisions, update the named files directly.",
        "If the issue asks for a build or fix, make the minimum necessary multi-file patch to satisfy it.",
    ]
    if task_spec.input_context_paths:
        input_context = ", ".join(task_spec.input_context_paths)
        lines.append(f"Treat these files as input-only context, not output targets: {input_context}.")
    if task_spec.tool_policy == "repo_plus_web":
        lines.append("Use web browsing when needed to complete research accurately before writing the file.")
    else:
        lines.append("Rely on repo and local context unless the task explicitly requires something else.")
    if _allows_artifact_synthesis(task_spec):
        lines.append(
            "Do not return status updates like 'Updated file X' or testing notes; return actual file content only."
        )
    return "\n".join(lines)


def _artifact_fallback_contract(task_spec: HealerTaskSpec) -> str:
    if not _allows_artifact_synthesis(task_spec):
        return ""
    targets = list(task_spec.output_targets) if task_spec.output_targets else ["docs/output.md"]
    if len(targets) == 1:
        target = targets[0]
        return (
            "For artifact-only docs/research tasks, if you cannot emit a valid diff, "
            f"return the final file contents for `{target}` in exactly one fenced block like "
            f"```markdown path={target}```.\n"
            "Return file body only inside the fence, with no narration before or after it."
        )
    rendered_targets = ", ".join(f"`{target}`" for target in targets)
    examples = "\n".join(
        "\n".join([f"```markdown path={target}", "...", "```"])
        for target in targets
    )
    return (
        "For artifact-only docs/research tasks with multiple targets, if you cannot emit a valid diff, "
        "return one fenced block per target using explicit `path=` markers.\n"
        f"Required targets: {rendered_targets}\n"
        f"Example format:\n{examples}\n"
        "Return file bodies only inside fences, with no narration before or after them."
    )


def _stage_workspace_changes(workspace: Path) -> bool:
    subprocess.run(
        ["git", "-C", str(workspace), "add", "-A"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return bool(_changed_paths(workspace))


def _classify_non_patch_failure(proposer_output: str) -> tuple[str, str]:
    text = (proposer_output or "").strip()
    lowered = text.lower()
    if lowered.startswith("connectorunavailable:"):
        return "connector_unavailable", text[:500]
    if lowered.startswith("connectorruntimeerror:"):
        return "connector_runtime_error", text[:500]
    if "codex cli not found" in lowered or "unable to resolve codex command" in lowered:
        return "connector_unavailable", text[:500]
    if "timed out" in lowered or "mcp startup" in lowered or "transport channel closed" in lowered:
        return "connector_runtime_error", text[:500]
    if lowered.startswith("error:") and "codex" in lowered:
        return "connector_runtime_error", text[:500]
    return "no_patch", "Proposer did not return a unified diff block."


def _materialize_artifact_from_output(
    *,
    task_spec: HealerTaskSpec,
    proposer_output: str,
    workspace: Path,
) -> bool:
    if not _allows_artifact_synthesis(task_spec):
        return False
    text = (proposer_output or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered.startswith("connectorunavailable:") or lowered.startswith("connectorruntimeerror:"):
        return False
    if lowered.startswith("error:") and "codex" in lowered:
        return False

    target_rels = [
        rel for rel in (_safe_rel_path(path) for path in task_spec.output_targets) if rel is not None
    ]
    if not target_rels:
        return False
    path_fenced_bodies = _extract_path_fenced_bodies(text)
    require_explicit_path = len(target_rels) > 1
    workspace_root = workspace.resolve()
    wrote_any = False
    for target_rel in target_rels:
        target_abs = (workspace / target_rel).resolve()
        if not _is_within_workspace(path=target_abs, workspace=workspace_root):
            continue
        content = _extract_artifact_content(
            text=text,
            target_path=target_rel,
            path_fenced_bodies=path_fenced_bodies,
            require_explicit_path=require_explicit_path,
        )
        if not content.strip():
            continue
        if _looks_like_status_update_summary(content):
            continue
        if not content.endswith("\n"):
            content += "\n"
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        existing = target_abs.read_text(encoding="utf-8") if target_abs.exists() else None
        if existing == content:
            continue
        target_abs.write_text(content, encoding="utf-8")
        wrote_any = True
    return wrote_any


def _allows_artifact_synthesis(task_spec: HealerTaskSpec) -> bool:
    if not task_spec.output_targets:
        return False
    if task_spec.validation_profile == "artifact_only":
        return True
    if task_spec.task_kind in {"research", "docs"}:
        return all(_is_artifact_path(path) for path in task_spec.output_targets)
    return False


def _extract_artifact_content(
    *,
    text: str,
    target_path: Path,
    path_fenced_bodies: dict[str, str] | None = None,
    require_explicit_path: bool = False,
) -> str:
    recovered = _recover_artifact_from_diff(text=text, target_path=target_path)
    if recovered:
        return recovered
    target_key = target_path.as_posix()
    path_fenced_bodies = path_fenced_bodies or {}
    if target_key in path_fenced_bodies:
        return path_fenced_bodies[target_key]
    if require_explicit_path:
        return ""
    suffix = target_path.suffix.lower()
    preferred_langs = _preferred_languages_for_suffix(suffix)
    best_match = ""
    fallback_match = ""
    for match in _FENCED_BLOCK_RE.finditer(text):
        lang = str(match.group("lang") or "").strip().lower().split(" ", 1)[0]
        body = str(match.group("body") or "").strip("\n")
        if not body:
            continue
        if lang == "diff":
            continue
        if not fallback_match:
            fallback_match = body
        if lang in preferred_langs:
            best_match = body
            break
    if best_match:
        return best_match
    if fallback_match:
        return fallback_match
    return text.strip()


def _extract_path_fenced_bodies(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in _FENCED_BLOCK_RE.finditer(text or ""):
        header = str(match.group("lang") or "").strip()
        body = str(match.group("body") or "").strip("\n")
        if not header or not body:
            continue
        lang = header.lower().split(" ", 1)[0]
        if lang == "diff":
            continue
        path_match = _FENCE_PATH_RE.search(header)
        if path_match is None:
            continue
        raw_path = str(path_match.group("path") or "").strip().strip("\"'")
        rel = _safe_rel_path(raw_path)
        if rel is None:
            continue
        out[rel.as_posix()] = body
    return out


def _looks_like_status_update_summary(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    if "i did not run tests" in lowered or "artifact_only" in lowered:
        if lowered.startswith(("updated ", "created ", "added ", "wrote ")):
            return True
        if lowered.startswith(("updated [", "created [", "added [", "wrote [")):
            return True
    if lowered.startswith(("updated [", "created [", "added [", "wrote [")) and " with " in lowered:
        return True
    return False


def _recover_artifact_from_diff(*, text: str, target_path: Path) -> str:
    diff_text = _extract_diff_block(text)
    if not diff_text.strip():
        return ""
    target_posix = target_path.as_posix()
    current_target = ""
    in_hunk = False
    is_new_file = False
    collected: list[str] = []
    for raw in diff_text.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("diff --git "):
            in_hunk = False
            is_new_file = False
            current_target = ""
            parts = line.split(" ")
            if len(parts) >= 4:
                b_path = parts[3]
                if b_path.startswith("b/"):
                    current_target = b_path[2:]
            continue
        if current_target != target_posix:
            continue
        if line.startswith("new file mode "):
            is_new_file = True
            continue
        if line.startswith("@@ "):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        if is_new_file:
            if line.startswith("+"):
                collected.append(line[1:])
            continue
        if line.startswith(" "):
            collected.append(line[1:])
            continue
        if line.startswith("+"):
            collected.append(line[1:])
            continue
    if not collected:
        return ""
    return "\n".join(collected).strip("\n")


def _preferred_languages_for_suffix(suffix: str) -> set[str]:
    if suffix in {".md", ".mdx"}:
        return {"markdown", "md", "mdx", "text", "txt"}
    if suffix in {".rst"}:
        return {"rst", "text", "txt"}
    if suffix in {".txt"}:
        return {"text", "txt", ""}
    if suffix in {".json"}:
        return {"json"}
    if suffix in {".yml", ".yaml"}:
        return {"yaml", "yml"}
    if suffix in {".toml"}:
        return {"toml"}
    if suffix in {".ini", ".cfg", ".conf"}:
        return {"ini", "cfg", "conf", "text", "txt"}
    return {"", "text", "txt"}


def _safe_rel_path(path: str) -> Path | None:
    candidate = Path(str(path).strip())
    if not candidate.parts or candidate.is_absolute():
        return None
    if any(part == ".." for part in candidate.parts):
        return None
    return candidate


def _is_within_workspace(*, path: Path, workspace: Path) -> bool:
    try:
        path.relative_to(workspace)
        return True
    except ValueError:
        return False


def _is_artifact_path(path: str) -> bool:
    lowered = str(path or "").strip().lower()
    suffix = Path(lowered).suffix
    return lowered.startswith("docs/") or suffix in {".md", ".mdx", ".rst", ".txt"}


def _reset_workspace_after_failed_apply(workspace: Path) -> None:
    subprocess.run(
        ["git", "-C", str(workspace), "reset", "--hard", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _run_pytest_in_docker(workspace: Path, command: list[str], timeout_seconds: int) -> dict[str, Any]:
    bash_script = _build_docker_test_script(command)
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{workspace}:/workspace",
        "-w",
        "/workspace",
        "python:3.11-slim",
        "bash",
        "-lc",
        bash_script,
    ]
    proc = subprocess.run(
        docker_cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=max(60, timeout_seconds),
    )
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return {
        "exit_code": int(proc.returncode),
        "output_tail": output[-2000:],
    }


def _build_docker_test_script(command: list[str]) -> str:
    bootstrap = [
        "python -m pip install --disable-pip-version-check -q pytest",
        (
            "if [ -f pyproject.toml ] || [ -f setup.py ] || [ -f setup.cfg ]; then "
            "python -m pip install --disable-pip-version-check -q -e .; "
            "fi"
        ),
    ]
    return " && ".join([*bootstrap, " ".join(_shell_quote(part) for part in command)])


def _shell_quote(value: str) -> str:
    return json.dumps(value)


def _normalize_test_gate_mode(mode: str) -> str:
    candidate = str(mode or "").strip().lower().replace("-", "_")
    if candidate in {"docker_only", "local_only", "local_then_docker"}:
        return candidate
    return "local_then_docker"


def _gate_runners_for_mode(mode: str) -> list[tuple[str, Any]]:
    if mode == "local_only":
        return [("local", _run_pytest_locally)]
    if mode == "docker_only":
        return [("docker", _run_pytest_in_docker)]
    return [
        ("local", _run_pytest_locally),
        ("docker", _run_pytest_in_docker),
    ]
