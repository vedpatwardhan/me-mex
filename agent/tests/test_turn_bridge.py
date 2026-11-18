import pytest
from me_mex_agent import turn_bridge


@pytest.mark.asyncio
async def test_run_turn_with_reply_parses_sse(monkeypatch):
    lines = [
        'data: {"type": "token", "content": "A"}',
        'data: {"type": "turn_end", "reply": "All good", "jobs": []}',
    ]

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            for line in lines:
                yield line

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(turn_bridge.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    reply, events, turn_end = await turn_bridge.run_turn_with_reply(
        text="hi",
        thread_id="t1",
        context_json={"active_project_id": "p1"},
    )
    assert reply == "All good"
    assert len(events) == 2
    assert turn_end["reply"] == "All good"
