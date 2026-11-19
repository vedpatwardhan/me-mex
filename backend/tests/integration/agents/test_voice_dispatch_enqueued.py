import json
import time

import pytest


@pytest.mark.voice_plane
def test_voice_dispatch_retrieval(client, project, voice_context_json, mock_vllm_chat):
    r = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "What relates to grasping?",
            "thread_id": "voice-dispatch",
            "context_json": voice_context_json,
        },
    )
    assert r.status_code == 200
    end = None
    for line in r.iter_lines():
        if line.startswith(b"data: "):
            chunk = json.loads(line[6:])
            if chunk.get("type") == "turn_end":
                end = chunk
    assert end is not None
    assert end.get("dispatched") is True
    assert end.get("job_id")
    time.sleep(0.3)
    br = client.get(
        "/api/agent/session/briefing",
        params={"project_id": project.id, "thread_id": "voice-dispatch"},
    )
    jobs = br.json().get("active_jobs") or []
    assert any(j.get("status") in ("done", "awaiting_approval", "running") for j in jobs)
