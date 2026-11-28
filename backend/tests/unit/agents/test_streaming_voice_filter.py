import pytest
from app.agents.streaming import event_to_dock_payload


@pytest.mark.dock_turn_plane
def test_worker_reply_not_dock_reply_on_voice():
    ev = {
        "event": "on_chain_end",
        "name": "worker",
        "data": {"output": {"reply": "worker said this"}},
    }
    payload = event_to_dock_payload(ev, dock_turn=True)
    assert payload
    assert payload["type"] == "worker_progress"
