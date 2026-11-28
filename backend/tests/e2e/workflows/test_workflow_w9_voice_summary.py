import pytest
from tests.sse_util import iter_sse_data


@pytest.mark.dock_turn_plane
def test_w9_voice_summary_path(client, project, voice_context_json, mock_vllm_chat):
    r = client.post(
        "/api/conversation/turn/stream",
        json={
            "text": "Summarize this link without writing the graph",
            "thread_id": "w9-voice",
            "context_json": voice_context_json,
        },
    )
    assert r.status_code == 200
    for chunk in iter_sse_data(r):
        if chunk.get("type") == "turn_end":
            assert chunk.get("reply")
            return
    pytest.fail("no turn_end")
