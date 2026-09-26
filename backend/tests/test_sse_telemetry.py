import json

from fastapi.testclient import TestClient


def test_sse_chat_stream(test_client: TestClient):
    """Test streaming SSE telemetry endpoint GET /api/sse/chat."""
    with test_client.stream(
        "GET", "/api/sse/chat?query=Hello&project_id=global"
    ) as response:
        assert response.status_code == 200
        events = []
        for line in response.iter_lines():
            if line.startswith("data:"):
                payload_str = line[len("data:") :].strip()
                if payload_str:
                    evt_data = json.loads(payload_str)
                    events.append(evt_data)

        assert len(events) > 0
        assert any(e.get("event") == "intent_classified" for e in events)
