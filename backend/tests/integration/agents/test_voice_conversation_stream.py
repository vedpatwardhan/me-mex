import json

import pytest


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
    chunks = []
    for line in r.iter_lines():
        if line.startswith(b"data: "):
            chunks.append(json.loads(line[6:]))
    types = {c.get("type") for c in chunks}
    assert "token" in types
    assert "turn_end" in types
    end = next(c for c in chunks if c.get("type") == "turn_end")
    assert end.get("source") == "conversation"
    assert end.get("reply")
