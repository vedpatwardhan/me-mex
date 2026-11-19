import json
from unittest.mock import AsyncMock

import pytest
from me_mex_agent.worker import RoomSession, _handle_data


@pytest.mark.asyncio
async def test_approve_data_calls_post_resume(monkeypatch):
    calls: list = []

    async def fake_post_resume(**kwargs):
        calls.append(kwargs)
        return {"status": "approved"}

    monkeypatch.setattr("me_mex_agent.worker.post_resume", fake_post_resume)
    monkeypatch.setattr("me_mex_agent.worker.speech_enabled", lambda: False)

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
