import json

import pytest


@pytest.mark.voice_plane
def test_w9_voice_summary_path(client, project, voice_context_json, mock_vllm_chat):
    r = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "Summarize this link without writing the graph",
            "thread_id": "w9-voice",
            "context_json": voice_context_json,
        },
    )
    assert r.status_code == 200
    for line in r.iter_lines():
        if line.startswith(b"data: "):
            chunk = json.loads(line[6:])
            if chunk.get("type") == "turn_end":
                assert chunk.get("reply")
                return
    pytest.fail("no turn_end")
