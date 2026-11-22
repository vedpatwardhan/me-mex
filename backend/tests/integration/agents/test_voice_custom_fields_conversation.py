"""Custom fields must reach the Conversation LLM on the voice plane (02 §3)."""

import pytest
from app.llm import AgentChains, get_chains, set_chains_override
from langchain_core.runnables import RunnableLambda
from tests.sse_util import iter_sse_data


@pytest.mark.voice_plane
def test_voice_conversation_stream_passes_custom_fields_to_llm(client, project):
    captured: list[dict] = []
    base = get_chains()

    def _capture(inp: dict) -> str:
        captured.append(dict(inp))
        return "Your name is Ved."

    set_chains_override(
        AgentChains(
            supervisor=base.supervisor,
            conversation=RunnableLambda(_capture),
            gist_draft=base.gist_draft,
            project_scope=base.project_scope,
            retrieval_summary=base.retrieval_summary,
            intradoc=base.intradoc,
        )
    )

    r = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "what is my name?",
            "thread_id": "voice-fields",
            "context_json": {
                "voice_turn": True,
                "active_project_id": project.id,
                "custom_fields": {"name": "Ved"},
            },
        },
    )
    assert r.status_code == 200
    list(iter_sse_data(r))
    assert captured, "conversation chain was not invoked"
    human = captured[0]["text"]
    assert "what is my name?" in human
    assert '"name": "Ved"' in human


@pytest.mark.voice_plane
def test_rest_conversation_worker_passes_custom_fields(client, project, mock_vllm_chat):
    from app.llm import AgentChains, get_chains, set_chains_override
    from langchain_core.runnables import RunnableLambda

    captured: list[dict] = []
    base = get_chains()
    set_chains_override(
        AgentChains(
            supervisor=base.supervisor,
            conversation=RunnableLambda(lambda inp: captured.append(dict(inp)) or "ok"),
            gist_draft=base.gist_draft,
            project_scope=base.project_scope,
            retrieval_summary=base.retrieval_summary,
            intradoc=base.intradoc,
        )
    )

    r = client.post(
        "/api/agent/turn",
        json={
            "text": "what is my name?",
            "thread_id": "rest-fields",
            "context_json": {
                "active_project_id": project.id,
                "custom_fields": {"name": "Ved"},
            },
        },
    )
    assert r.status_code == 200
    assert captured
    assert "name=Ved" in captured[0]["text"]
