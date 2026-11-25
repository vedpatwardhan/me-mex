import time
from uuid import uuid4

import pytest
from tests.sse_util import iter_sse_data

pytestmark = pytest.mark.voice_plane


def test_empty_scope_dispatches_project_scope_job(client, empty_project, mock_vllm_chat):
    ctx = {
        "voice_turn": True,
        "active_project_id": empty_project.id,
        "project_id": empty_project.id,
    }
    r = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "Robotics manipulation and sim-to-real for warehouse picking.",
            "thread_id": "voice-p1",
            "context_json": ctx,
        },
    )
    assert r.status_code == 200
    chunks = list(iter_sse_data(r))
    end = next(c for c in chunks if c.get("type") == "turn_end")
    assert end.get("dispatched") is True
    assert end.get("worker_kind") == "project_scope"
    assert all(c.get("source") != "project_scope" for c in chunks if c.get("type") == "token")
    time.sleep(2.0)


@pytest.mark.voice_plane
def test_substantive_scope_turn_creates_approval_without_define_scope_command(
    client, empty_project
):
    thread_id = f"voice-scope-first-turn-{uuid4().hex}"
    response = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": (
                "My project studies recursive self-improvement in AI, including how systems "
                "could improve their algorithms and infrastructure."
            ),
            "thread_id": thread_id,
            "context_json": {
                "voice_turn": True,
                "active_project_id": empty_project.id,
                "project_id": empty_project.id,
            },
        },
    )
    chunks = list(iter_sse_data(response))
    end = next(chunk for chunk in chunks if chunk.get("type") == "turn_end")

    assert response.status_code == 200
    assert end["worker_kind"] == "project_scope"
    assert end["dispatched"] is True

    deadline = time.monotonic() + 90.0
    approvals = []
    while time.monotonic() < deadline:
        approvals = client.get(
            "/api/agent/approvals",
            params={"project_id": empty_project.id, "thread_id": thread_id},
        ).json()["items"]
        if approvals:
            break
        time.sleep(0.05)
    assert approvals
    assert approvals[0]["approval_type"] == "project_scope"
    proposed = approvals[0]["payload"]["proposed_introduction"] or ""
    assert len(proposed.strip()) >= 80
    assert "recursive" in proposed.lower() or "self-improvement" in proposed.lower()
