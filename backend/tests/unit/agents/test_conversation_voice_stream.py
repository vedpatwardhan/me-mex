import pytest
from app.agents.conversation_voice import (
    _astream_voice_conversation_reply,
    _background_worker_acknowledgement,
    _conversation_prompt_inputs,
)
from app.llm.chains import AgentChains, get_chains, set_chains_override
from app.prompts import load_prompt
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


def test_background_gist_dispatch_uses_fixed_acknowledgement():
    assert _background_worker_acknowledgement("gist") == (
        "I’ll read the paper you shared and put a concise gist in the dock for review."
    )


def test_conversation_prompt_uses_completed_results_as_only_source_evidence():
    inputs = _conversation_prompt_inputs(
        text="What does the paper say about its method?",
        briefing={
            "pending_approval_count": 1,
            "active_jobs": [{"worker": "gist", "status": "running", "label": "paper"}],
            "completed_worker_results": [
                {
                    "worker": "gist",
                    "source_title": "Paper A",
                    "result": "It evaluates a latent world-action model.",
                }
            ],
            "recommendation_cards": [{"title": "not conversational evidence"}],
        },
        project_scope="Research project scope",
        user_fields={
            "name": "Ved",
            "paper": "https://arxiv.org/pdf/2605.11550",
        },
    )
    assert '"pending_approval_count": 1' in inputs["text"]
    assert "It evaluates a latent world-action model." in inputs["text"]
    assert "not conversational evidence" not in inputs["text"]
    assert '"name": "Ved"' in inputs["text"]
    assert "2605.11550" not in inputs["text"]
    prompt = load_prompt("conversation", project_scope="Research project scope")
    assert "Only `completed_worker_results`" in prompt
    assert "Never infer a title, method, finding, or conclusion" in prompt
    assert "When `session_briefing.scope_complete` is false" in prompt
    assert "define the project scope" in prompt
