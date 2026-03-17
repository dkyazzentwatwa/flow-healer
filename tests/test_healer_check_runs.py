from __future__ import annotations

import json
import io
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

from flow_healer.healer_tracker import GitHubHealerTracker


def _make_tracker(token: str = "test-token") -> GitHubHealerTracker:
    tracker = GitHubHealerTracker(repo_path=Path("."), token=token)
    tracker.repo_slug = "owner/repo"
    return tracker


def _http_response(payload: dict, status: int = 201):
    """Create a mock urllib response for _request_json."""
    raw = json.dumps(payload).encode("utf-8")
    resp = mock.MagicMock()
    resp.__enter__ = mock.MagicMock(return_value=resp)
    resp.__exit__ = mock.MagicMock(return_value=False)
    resp.read.return_value = raw
    resp.status = status
    resp.headers = {}
    return resp


# ---------------------------------------------------------------------------
# create_check_run
# ---------------------------------------------------------------------------


def test_create_check_run_returns_id_on_success(monkeypatch):
    tracker = _make_tracker()
    posted: list[dict] = []

    def fake_urlopen(req, timeout=None):
        posted.append(json.loads(req.data))
        return _http_response({"id": 99, "name": req.full_url}, status=201)

    monkeypatch.setattr("flow_healer.healer_tracker.urlopen", fake_urlopen)

    check_id = tracker.create_check_run(
        name="flow-healer/scope-check",
        head_sha="abc123",
        status="in_progress",
        title="Scope check running",
        summary="Validating plan scope.",
    )

    assert check_id == 99
    assert len(posted) == 1
    body = posted[0]
    assert body["name"] == "flow-healer/scope-check"
    assert body["head_sha"] == "abc123"
    assert body["status"] == "in_progress"
    assert body["output"]["title"] == "Scope check running"


def test_create_check_run_sets_completed_when_conclusion_given(monkeypatch):
    tracker = _make_tracker()
    posted: list[dict] = []

    def fake_urlopen(req, timeout=None):
        posted.append(json.loads(req.data))
        return _http_response({"id": 7})

    monkeypatch.setattr("flow_healer.healer_tracker.urlopen", fake_urlopen)

    tracker.create_check_run(
        name="flow-healer/validation",
        head_sha="deadbeef",
        conclusion="success",
        summary="All tests passed.",
    )

    body = posted[0]
    assert body["status"] == "completed"
    assert body["conclusion"] == "success"


def test_create_check_run_returns_zero_when_disabled(monkeypatch):
    tracker = _make_tracker(token="")
    result = tracker.create_check_run(
        name="flow-healer/scope-check",
        head_sha="abc",
    )
    assert result == 0


def test_create_check_run_returns_zero_on_http_error(monkeypatch):
    tracker = _make_tracker()

    def fake_urlopen(req, timeout=None):
        raise HTTPError(url="", code=403, msg="Forbidden", hdrs={}, fp=io.BytesIO(b"{}"))

    monkeypatch.setattr("flow_healer.healer_tracker.urlopen", fake_urlopen)
    result = tracker.create_check_run(
        name="flow-healer/scope-check",
        head_sha="abc",
    )
    assert result == 0


# ---------------------------------------------------------------------------
# update_check_run
# ---------------------------------------------------------------------------


def test_update_check_run_patches_correct_url(monkeypatch):
    tracker = _make_tracker()
    patched_paths: list[str] = []

    def fake_urlopen(req, timeout=None):
        patched_paths.append(req.full_url)
        return _http_response({"id": 42})

    monkeypatch.setattr("flow_healer.healer_tracker.urlopen", fake_urlopen)

    ok = tracker.update_check_run(
        check_run_id=42,
        conclusion="failure",
        summary="Tests failed.",
    )

    assert ok
    assert "check-runs/42" in patched_paths[0]


def test_update_check_run_returns_false_for_zero_id():
    tracker = _make_tracker()
    assert tracker.update_check_run(check_run_id=0, conclusion="success") is False


# ---------------------------------------------------------------------------
# publish_check_run (convenience wrapper)
# ---------------------------------------------------------------------------


def test_publish_check_run_creates_completed_run(monkeypatch):
    tracker = _make_tracker()
    posted: list[dict] = []

    def fake_urlopen(req, timeout=None):
        posted.append(json.loads(req.data))
        return _http_response({"id": 55})

    monkeypatch.setattr("flow_healer.healer_tracker.urlopen", fake_urlopen)

    run_id = tracker.publish_check_run(
        name="flow-healer/evidence-ready",
        head_sha="cafebabe",
        conclusion="success",
        title="Evidence ready",
        summary="PR is ready for review.",
    )

    assert run_id == 55
    body = posted[0]
    assert body["status"] == "completed"
    assert body["conclusion"] == "success"
    assert body["name"] == "flow-healer/evidence-ready"
