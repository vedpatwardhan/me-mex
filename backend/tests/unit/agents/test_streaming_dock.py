from app.agents.streaming import event_to_dock_payload


def test_maps_chat_token():
    class Chunk:
        content = "hi"

    out = event_to_dock_payload({"event": "on_chat_model_stream", "data": {"chunk": Chunk()}})
    assert out == {"type": "token", "content": "hi"}


def test_maps_custom_event():
    out = event_to_dock_payload(
        {"event": "on_custom_event", "data": {"job": {"job_id": "j1", "status": "running"}}}
    )
    assert out["type"] == "custom"
