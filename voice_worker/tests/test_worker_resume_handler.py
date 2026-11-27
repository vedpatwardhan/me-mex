import json
from unittest.mock import AsyncMock

import pytest
from voice_agent.worker import (
    EMERGENCY_APPROVAL_FALLBACK,
    RoomSession,
    _approval_reply,
    _handle_data,
)


@pytest.mark.asyncio
async def test_approve_data_calls_post_resume(monkeypatch):
    calls: list = []

    async def fake_post_resume(**kwargs):
        calls.append(kwargs)
        return {
            "status": "approved",
            "approval_type": "gist_root",
            "graph_write": True,
            "reply": "The gist has been added to the graph.",
        }

    monkeypatch.setattr("voice_agent.worker.post_resume", fake_post_resume)
    monkeypatch.setattr("voice_agent.worker.speech_enabled", lambda: False)

    publish = AsyncMock()
    room = type("Room", (), {"local_participant": type("LP", (), {"publish_data": publish})()})()
    session = RoomSession(
        thread_id="t1",
        context_json={"active_project_id": "p1"},
        muted=False,
    )
    payload = json.dumps({"type": "approve", "approval_id": "a1"}).encode()

    await _handle_data(payload, room, session)  # type: ignore[arg-type]

    assert calls and calls[0]["approval_id"] == "a1"
    publish.assert_awaited()
    turn_end = json.loads(publish.await_args_list[0].args[0])["event"]
    assert turn_end["reply"] == "The gist has been added to the graph."
    assert turn_end["graph_write"] is True


@pytest.mark.parametrize(
    "approval_type",
    ["gist_root", "intra_doc_staging", "placement", "reorg"],
)
def test_approval_without_backend_reply_uses_emergency_fallback(approval_type):
    reply = _approval_reply({"status": "approved", "approval_type": approval_type})
    assert reply == EMERGENCY_APPROVAL_FALLBACK


def test_approval_reply_prefers_conversational_backend_reply():
    assert (
        _approval_reply(
            {
                "status": "approved",
                "approval_type": "gist_root",
                "reply": "The gist is in the graph and ready to review.",
            }
        )
        == "The gist is in the graph and ready to review."
    )
