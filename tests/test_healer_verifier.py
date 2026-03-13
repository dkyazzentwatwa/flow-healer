from __future__ import annotations

from flow_healer.healer_task_spec import HealerTaskSpec
from flow_healer.healer_verifier import HealerVerifier


class _CaptureConnector:
    def __init__(self, response: str) -> None:
        self.response = response
        self.timeout_seconds: int | None = None
        self.last_prompt = ""

    def get_or_create_thread(self, sender: str) -> str:
        return f"thread:{sender}"

    def reset_thread(self, sender: str) -> str:
        return f"thread:{sender}"

    def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
        self.timeout_seconds = timeout_seconds
        self.last_prompt = prompt
        return self.response

    def ensure_started(self) -> None:
        return None

    def shutdown(self) -> None:
        return None


def _task_spec() -> HealerTaskSpec:
    return HealerTaskSpec(
        task_kind="fix",
        output_mode="patch",
        output_targets=("src/flow_healer/service.py",),
        tool_policy="repo_only",
        validation_profile="code_change",
    )


def test_healer_verifier_passes_timeout_to_connector() -> None:
    connector = _CaptureConnector('{"verdict":"pass","summary":"Looks good."}')
    verifier = HealerVerifier(connector=connector, timeout_seconds=123)

    result = verifier.verify(
        issue_id="801",
        issue_title="Fix service issue",
        issue_body="Body",
        task_spec=_task_spec(),
        diff_paths=["src/flow_healer/service.py"],
        test_summary={"failed_tests": 0},
        proposer_output="```diff\ndiff --git a/x b/x\n```",
    )

    assert result.passed is True
    assert result.verdict == "pass"
    assert result.hard_failure is False
    assert connector.timeout_seconds == 123


def test_healer_verifier_treats_non_json_output_as_advisory_failure() -> None:
    connector = _CaptureConnector("This should pass, and it did not fail in my opinion.")
    verifier = HealerVerifier(connector=connector)

    result = verifier.verify(
        issue_id="802",
        issue_title="Fix service issue",
        issue_body="Body",
        task_spec=_task_spec(),
        diff_paths=["src/flow_healer/service.py"],
        test_summary={"failed_tests": 0},
        proposer_output="```diff\ndiff --git a/x b/x\n```",
    )

    assert result.passed is False
    assert result.verdict == "soft_fail"
    assert result.hard_failure is False
    assert result.parse_error is True
    assert "not valid JSON" in result.summary
    assert "This should pass" in result.summary


def test_healer_verifier_accepts_fenced_json() -> None:
    connector = _CaptureConnector('```json\n{"verdict":"pass","summary":"Looks good."}\n```')
    verifier = HealerVerifier(connector=connector)

    result = verifier.verify(
        issue_id="803",
        issue_title="Fix service issue",
        issue_body="Body",
        task_spec=_task_spec(),
        diff_paths=["src/flow_healer/service.py"],
        test_summary={"failed_tests": 0},
        proposer_output="summary",
    )

    assert result.passed is True
    assert result.verdict == "pass"
    assert result.hard_failure is False


def test_healer_verifier_extracts_first_json_object_from_prose() -> None:
    connector = _CaptureConnector(
        'I checked the patch.\n{"verdict":"soft_fail","summary":"Validation passed but this should stay advisory."}\nThanks.'
    )
    verifier = HealerVerifier(connector=connector)

    result = verifier.verify(
        issue_id="804",
        issue_title="Fix service issue",
        issue_body="Body",
        task_spec=_task_spec(),
        diff_paths=["src/flow_healer/service.py"],
        test_summary={"failed_tests": 0},
        proposer_output="summary",
    )

    assert result.passed is False
    assert result.verdict == "soft_fail"
    assert result.hard_failure is False
    assert result.parse_error is False


def test_healer_verifier_marks_unknown_verdict_as_hard_failure() -> None:
    connector = _CaptureConnector('{"verdict":"fail","summary":"Too broad."}')
    verifier = HealerVerifier(connector=connector)

    result = verifier.verify(
        issue_id="805",
        issue_title="Fix service issue",
        issue_body="Body",
        task_spec=_task_spec(),
        diff_paths=["src/flow_healer/service.py"],
        test_summary={"failed_tests": 0},
        proposer_output="summary",
    )

    assert result.passed is False
    assert result.verdict == "hard_fail"
    assert result.hard_failure is True
    assert result.parse_error is False


def test_healer_verifier_includes_structured_browser_contract_context() -> None:
    connector = _CaptureConnector('{"verdict":"pass","summary":"Looks good."}')
    verifier = HealerVerifier(connector=connector)

    verifier.verify(
        issue_id="806",
        issue_title="Browser artifact smoke",
        issue_body="Body",
        task_spec=HealerTaskSpec(
            task_kind="edit",
            output_mode="patch",
            output_targets=("demo.py",),
            tool_policy="repo_only",
            validation_profile="code_change",
            browser_repro_mode="allow_success",
            repro_steps=("goto /dashboard", "expect_text Artifact Proof Java E1"),
            artifact_requirements=("screenshot: artifacts/demo.png", "console log", "network log"),
        ),
        diff_paths=[],
        test_summary={
            "browser_repro_mode": "allow_success",
            "browser_evidence_required": True,
            "artifact_proof_ready": True,
            "promotion_transitions": ["failure_artifacts_captured", "resolution_artifacts_captured", "local_validated"],
            "flaky_repro": {
                "checked": True,
                "reproduced_on_first_run": False,
                "reproduced_on_replay": False,
            },
        },
        proposer_output="No code changes were needed.",
    )

    assert "Browser contract summary:" in connector.last_prompt
    assert "browser_repro_mode=allow_success" in connector.last_prompt
    assert "artifact_proof_ready=true" in connector.last_prompt
    assert "promotion_transitions=failure_artifacts_captured,resolution_artifacts_captured,local_validated" in connector.last_prompt
