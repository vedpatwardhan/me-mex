"""Phase 2 voice path: turn_bridge consumes workflow-shaped context (no LiveKit room)."""

from unittest.mock import patch

import pytest
from voice_agent.turn_bridge import run_turn_with_reply


@pytest.mark.asyncio
async def test_w8_muted_context_shape():
    chunks = [
        {"type": "token", "content": "Summary"},
        {"type": "turn_end", "reply": "Summary", "graph_write": False},
    ]

    async def fake_stream(**_kwargs):
        for c in chunks:
            yield c

    with patch("voice_agent.turn_bridge.stream_turn", side_effect=fake_stream):
        reply, events, turn_end = await run_turn_with_reply(
            text="",
            thread_id="w8",
            context_json={
                "active_project_id": "p1",
                "muted": True,
                "custom_fields": {"intent": "summarize_selection"},
            },
        )
    assert reply == "Summary"
    assert len(events) == 2
    assert turn_end["graph_write"] is False
