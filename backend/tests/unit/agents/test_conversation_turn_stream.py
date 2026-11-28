import pytest
from app.agents.conversation_utterance import (
    UtteranceIntent,
    astream_dock_conversation_reply,
    build_conversation_turn,
    build_multi_utterance_turn,
    conversation_prompt_inputs,
)
from app.config import settings
from app.prompts import load_prompt


@pytest.mark.asyncio
async def test_astream_live_yields_tokens_before_full_reply():
    if settings.CHAT_LLM_MODE != "live":
        pytest.skip("CHAT_LLM_MODE is not live (set in backend/.env.test)")
    inp = {
        "text": "Say hello in one short sentence.",
        "project_scope": "Research project.",
    }
    parts: list[str] = []
    async for piece in astream_dock_conversation_reply(inp):
        parts.append(piece)
    reply = "".join(parts).strip()
    assert parts
    assert reply
    assert len(reply.split()) <= 25


def test_multi_utterance_turn_coalesces_segments():
    inp = build_multi_utterance_turn(
        user_message="Summarize and pause the job.",
        briefing={"active_jobs": [{"job_id": "j1"}], "scope_complete": True},
        project_scope="Research.",
        user_fields={"paper": "https://arxiv.org/pdf/1"},
        segments=[
            (
                UtteranceIntent.JOB_CONTROL_RESULT,
                {"job_action": "pause", "job_id": "j1"},
            ),
            (
                UtteranceIntent.DISPATCH_INTERIM,
                {"worker_kind": "gist", "already_running": False},
            ),
        ],
    )
    assert "utterance_segments" in inp["text"]
    assert "job_control_result" in inp["text"]
    assert "dispatch_interim" in inp["text"]
    assert "arxiv" not in inp["text"]


def test_dispatch_interim_prompt_excludes_source_urls():
    inputs = build_conversation_turn(
        intent=UtteranceIntent.DISPATCH_INTERIM,
        user_message="Summarize this paper.",
        briefing={"active_jobs": [], "scope_complete": True},
        project_scope="Research project scope",
        user_fields={"paper": "https://arxiv.org/pdf/2605.11550", "name": "Ved"},
        utterance_facts={"worker_kind": "gist", "already_running": False},
    )
    assert "2605.11550" not in inputs["text"]
    assert "dispatch_interim" in inputs["text"]
    assert '"name": "Ved"' not in inputs["text"]
    assert "gist" in inputs["text"]


def test_conversation_prompt_uses_completed_results_as_only_source_evidence():
    inputs = conversation_prompt_inputs(
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
    assert "dispatch_interim" in prompt
