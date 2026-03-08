from __future__ import annotations

from flow_healer.healer_task_spec import HealerTaskSpec
from flow_healer.healer_verifier import HealerVerifier


class _CaptureConnector:
    def __init__(self, response: str) -> None:
        self.response = response
        self.timeout_seconds: int | None = None

    def get_or_create_thread(self, sender: str) -> str:
        return f"thread:{sender}"

    def reset_thread(self, sender: str) -> str:
        return f"thread:{sender}"

    def run_turn(self, thread_id: str, prompt: str, *, timeout_seconds: int | None = None) -> str:
        self.timeout_seconds = timeout_seconds
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
    assert connector.timeout_seconds == 123


def test_healer_verifier_treats_non_json_output_as_failure() -> None:
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
    assert "not valid JSON" in result.summary
    assert "This should pass" in result.summary
