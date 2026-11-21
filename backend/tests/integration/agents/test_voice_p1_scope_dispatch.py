import time

import pytest
from tests.sse_util import iter_sse_data


@pytest.mark.voice_plane
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
    time.sleep(0.5)
