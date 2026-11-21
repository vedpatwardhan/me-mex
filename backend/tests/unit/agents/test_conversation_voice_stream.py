import pytest
from app.agents.conversation_voice import _astream_voice_conversation_reply
from app.llm.chains import AgentChains, get_chains, set_chains_override
from langchain_core.runnables import RunnableLambda


@pytest.mark.asyncio
async def test_astream_stub_yields_tokens_before_full_reply(monkeypatch):
    base = get_chains()
    set_chains_override(
        AgentChains(
            supervisor=base.supervisor,
            conversation=RunnableLambda(lambda _: "Hello world from stub."),
            gist_draft=base.gist_draft,
            project_scope=base.project_scope,
            retrieval_summary=base.retrieval_summary,
            intradoc=base.intradoc,
        )
    )
    monkeypatch.setattr("app.agents.conversation_voice.settings.CHAT_LLM_MODE", "stub")
    inp = {"text": "user", "project_scope": ""}
    parts: list[str] = []
    async for p in _astream_voice_conversation_reply(inp):
        parts.append(p)
    assert parts
    assert "".join(parts) == "Hello world from stub."
