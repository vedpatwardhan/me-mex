import pytest
from tests.sse_util import iter_sse_data


@pytest.mark.dock_turn_plane
def test_chitchat_empty_scope_no_scope_dispatch(client, empty_project, mock_vllm_chat):
    ctx = {
        "dock_turn": True,
        "active_project_id": empty_project.id,
        "project_id": empty_project.id,
    }
    r = client.post(
        "/api/conversation/turn/stream",
        json={
            "text": "how's your day",
            "thread_id": "voice-p1-chit",
            "context_json": ctx,
        },
    )
    assert r.status_code == 200
    chunks = list(iter_sse_data(r))
    end = next(c for c in chunks if c.get("type") == "turn_end")
    assert end.get("dispatched") is False
    assert end.get("worker_kind") in (None, "conversation")
