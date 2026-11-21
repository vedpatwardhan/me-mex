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


@pytest.mark.voice_plane
def test_conversation_turn_does_not_park_background_jobs(
    client, project_scoped, mock_vllm_chat, monkeypatch
):
    from app.agents import job_runtime

    parked = []
    monkeypatch.setattr(job_runtime, "park_active_jobs", lambda thread_id: parked.append(thread_id))
    response = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "While that paper is being read, let's talk about what I should focus on.",
            "thread_id": "voice-background-chat",
            "context_json": {
                "voice_turn": True,
                "active_project_id": project_scoped.id,
                "project_id": project_scoped.id,
                "custom_fields": {},
            },
        },
    )

    assert response.status_code == 200
    chunks = list(iter_sse_data(response))
    end = next(chunk for chunk in chunks if chunk.get("type") == "turn_end")
    assert end["details"]["route"] == "conversation"
    assert parked == []
