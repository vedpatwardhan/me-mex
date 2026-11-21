import pytest
from tests.sse_util import iter_sse_data


@pytest.mark.voice_plane
def test_voice_conversation_stream(client, project, voice_context_json, mock_vllm_chat):
    r = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "hello",
            "thread_id": "voice-stream",
            "context_json": voice_context_json,
        },
    )
    assert r.status_code == 200
    chunks = list(iter_sse_data(r))
    types = {c.get("type") for c in chunks}
    assert "token" in types
    assert "turn_end" in types
    tokens = [c for c in chunks if c.get("type") == "token"]
    assert len(tokens) >= 1
    end = next(c for c in chunks if c.get("type") == "turn_end")
    assert end.get("source") == "conversation"
    assert end.get("reply")
    joined = "".join(c.get("content") or "" for c in tokens)
    assert joined == end.get("reply")
