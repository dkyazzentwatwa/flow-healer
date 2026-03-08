from pathlib import Path

from flow_healer.local_healer_tracker import LocalHealerTracker


def test_local_tracker_create_and_list_ready_issues(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    tracker = LocalHealerTracker(repo_path=repo_path, state_root=tmp_path / "state")

    created = tracker.create_issue(
        title="Scanner finding",
        body="flow-healer-fingerprint: `abc123`",
        labels=["healer:ready", "kind:scan"],
    )
    assert created is not None

    issues = tracker.list_ready_issues(required_labels=["healer:ready"], trusted_actors=[], limit=10)
    assert len(issues) == 1
    assert issues[0].title == "Scanner finding"

    deduped = tracker.find_open_issue_by_fingerprint("abc123")
    assert deduped is not None
    assert deduped["number"] == created["number"]


def test_local_tracker_open_update_and_close_pr(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    tracker = LocalHealerTracker(repo_path=repo_path, state_root=tmp_path / "state")

    issue = tracker.create_issue(title="Bug", body="body", labels=["healer:ready"])
    assert issue is not None

    pr = tracker.open_or_update_pr(
        issue_id=str(issue["number"]),
        branch="healer/issue-1",
        title="Fix issue #1",
        body="PR body",
        base="main",
    )
    assert pr is not None
    assert tracker.get_pr_state(pr_number=pr.number) == "open"

    assert tracker.add_pr_comment(pr_number=pr.number, body="looks good")
    assert tracker.approve_pr(pr_number=pr.number, body="approved")
    assert tracker.merge_pr(pr_number=pr.number)

    details = tracker.get_pr_details(pr_number=pr.number)
    assert details is not None
    assert details.state == "merged"

