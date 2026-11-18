import pytest


@pytest.mark.asyncio
async def test_astream_emits_turn_end(store, project_scoped, mock_vllm_chat):
    from app.agents.graph import astream_agent_turn

    pid = project_scoped.id
    chunks = []
    async for ch in astream_agent_turn(
        project_id=pid,
        thread_id="stream-end",
        text="hello",
        context_json={"active_project_id": pid},
    ):
        chunks.append(ch)
    assert chunks
    assert chunks[-1]["type"] == "turn_end"
    assert "reply" in chunks[-1]
