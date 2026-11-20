import pytest
from tests.sse_util import iter_sse_data


@pytest.mark.voice_plane
def test_chit_chat_no_dispatch(client, voice_context_json, mock_vllm_chat):
    r = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "hello there",
            "thread_id": "voice-chit",
            "context_json": voice_context_json,
        },
    )
    assert r.status_code == 200
    for chunk in iter_sse_data(r):
        if chunk.get("type") == "turn_end":
            assert chunk.get("dispatched") is False
            return
    pytest.fail("missing turn_end")
