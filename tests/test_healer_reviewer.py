from __future__ import annotations

from unittest.mock import MagicMock

from flow_healer.healer_reviewer import HealerReviewer
from flow_healer.protocols import ConnectorProtocol


def test_healer_reviewer_generates_review():
    connector = MagicMock(spec=ConnectorProtocol)
    connector.get_or_create_thread.return_value = "thread_123"
    connector.run_turn.return_value = "This is a great fix! All tests passed."

    reviewer = HealerReviewer(connector=connector)
    result = reviewer.review(
        issue_id="1",
        issue_title="Fix bug",
        issue_body="The bug is bad.",
        diff_paths=["src/fix.py"],
        test_summary={"failed_tests": 0},
        proposer_output="```diff\n...\n```",
        verifier_summary="Verified",
    )

    assert result.review_body == "This is a great fix! All tests passed."
    connector.get_or_create_thread.assert_called_with("healer-review:1")
    assert "Jules" in connector.run_turn.call_args[0][1]
