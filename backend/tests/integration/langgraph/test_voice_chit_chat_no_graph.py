import json

import pytest


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
    for line in r.iter_lines():
        if line.startswith(b"data: "):
            chunk = json.loads(line[6:])
            if chunk.get("type") == "turn_end":
                assert chunk.get("dispatched") is False
                return
    pytest.fail("missing turn_end")
