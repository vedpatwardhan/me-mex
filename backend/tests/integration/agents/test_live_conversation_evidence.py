import pytest
from app.agents.conversation_voice import (
    _astream_voice_conversation_reply,
    _conversation_prompt_inputs,
)
from app.agents.voice_dispatch import normalize_link_decision
from app.agents.workers import route_intent
from app.config import settings
from app.models import Project


@pytest.mark.live_llm
@pytest.mark.asyncio
async def test_live_conversation_defers_source_claims_until_gist_is_complete():
    if settings.CHAT_LLM_MODE != "live":
        pytest.skip("run with ME_MEX_RUN_LIVE_LLM_TESTS=1 and CHAT_LLM_MODE=live")

    inputs = _conversation_prompt_inputs(
        text="Can you tell me this paper's main findings while it is still being processed?",
        briefing={
            "scope_complete": True,
            "project_scope_snippet": "Research project about recursive self-improvement.",
            "active_jobs": [
                {
                    "job_id": "job-pending-paper",
                    "worker": "gist",
                    "status": "running",
                    "label": "Read the paper",
                }
            ],
            "completed_worker_results": [],
            "pending_approval_count": 0,
        },
        project_scope="Research project about recursive self-improvement.",
    )
    parts: list[str] = []
    async for part in _astream_voice_conversation_reply(inputs):
        parts.append(part)
    answer = "".join(parts).strip().lower()

    assert answer
    assert len(answer.split()) <= 65
    says_pending = any(
        phrase in answer for phrase in ("still", "currently", "being processed", "being read")
    )
    defers_claims = any(
        phrase in answer
        for phrase in (
            "not yet",
            "don't have",
            "don’t have",
            "once",
            "as soon as",
            "when the",
            "when it’s",
            "when it's",
            "when ready",
        )
    )
    assert says_pending and defers_claims, answer


@pytest.mark.live_llm
@pytest.mark.asyncio
async def test_live_empty_scope_conversation_guides_user_to_define_scope():
    if settings.CHAT_LLM_MODE != "live":
        pytest.skip("run with ME_MEX_RUN_LIVE_LLM_TESTS=1 and CHAT_LLM_MODE=live")

    inputs = _conversation_prompt_inputs(
        text="I don't have anything on my mind specifically. What's on the plan today?",
        briefing={
            "scope_complete": False,
            "active_jobs": [],
            "pending_approval_count": 0,
            "completed_worker_results": [],
        },
        project_scope="",
    )
    parts: list[str] = []
    async for part in _astream_voice_conversation_reply(inputs):
        parts.append(part)
    answer = "".join(parts).strip().lower()

    assert "scope" in answer, answer
    assert "source" in answer, answer
    assert "?" in answer, answer


@pytest.mark.live_llm
def test_live_supervisor_routes_natural_cancel_to_the_active_job():
    if settings.CHAT_LLM_MODE != "live":
        pytest.skip("run with ME_MEX_RUN_LIVE_LLM_TESTS=1 and CHAT_LLM_MODE=live")

    decision = route_intent(
        "Please abort the redundant gist; I don't need another summary.",
        {
            "scope_approval_pending": False,
            "session_state": {
                "active_jobs": [
                    {
                        "job_id": "job-active-gist",
                        "worker": "gist",
                        "status": "running",
                        "label": "Summarize the first paper",
                    }
                ],
                "pending_approval_count": 0,
            },
            "custom_fields": {},
        },
        Project(_id="live-job-control", name="Live job control", introduction="Research project."),
    )
    assert decision.worker == "job_control"
    assert decision.intent == "job_control"
    assert decision.job_action == "cancel"
    assert decision.target_id == "job-active-gist"


@pytest.mark.live_llm
def test_live_supervisor_returns_foreground_reply_without_second_conversation_call():
    if settings.CHAT_LLM_MODE != "live":
        pytest.skip("run with ME_MEX_RUN_LIVE_LLM_TESTS=1 and CHAT_LLM_MODE=live")

    decision = route_intent(
        "While the deep read is running, what does this project focus on?",
        {
            "custom_fields": {},
            "session_state": {
                "active_jobs": [
                    {
                        "job_id": "job-deep-read",
                        "worker": "intradoc",
                        "status": "running",
                        "label": "Deep read: paper A",
                    }
                ],
                "pending_approval_count": 0,
                "completed_worker_results": [],
            },
        },
        Project(
            _id="live-conversation-reply",
            name="Live conversation reply",
            introduction="Research on recursive self-improvement in AI, including methods for models to improve with less human intervention.",
        ),
    )

    assert decision.worker == "conversation"
    assert decision.dispatch is False
    assert decision.reply
    assert "self-improvement" in decision.reply.lower()


@pytest.mark.live_llm
def test_live_supervisor_resolves_recent_node_pronoun_for_link():
    if settings.CHAT_LLM_MODE != "live":
        pytest.skip("run with ME_MEX_RUN_LIVE_LLM_TESTS=1 and CHAT_LLM_MODE=live")

    routing_context = {
        "custom_fields": {},
        "graph_candidates": [
            {"id": "genesis_global", "title": "Genesis", "node_kind": "CONCEPT_M"},
            {
                "id": "root_dawn",
                "title": "The DAWN paper",
                "node_kind": "ROOT",
            },
        ],
        "routing_memory": {
            "summary": "gist_root ROOT 'The DAWN paper' (id=root_dawn)",
            "focus_root": {
                "id": "root_dawn",
                "title": "The DAWN paper",
                "node_kind": "ROOT",
            },
            "current_source": {
                "worker": "gist",
                "source_url": "https://arxiv.org/pdf/2610.12345",
                "title": "The DAWN paper",
                "root_id": "root_dawn",
            },
            "recent_graph_changes": [
                {
                    "operation": "gist_root",
                    "nodes": [
                        {
                            "id": "root_dawn",
                            "title": "The DAWN paper",
                            "node_kind": "ROOT",
                        }
                    ],
                }
            ],
            "recent_turns": [
                {
                    "role": "assistant",
                    "text": "The DAWN paper gist was approved and added to the graph as a ROOT.",
                }
            ],
        },
    }
    decision = route_intent(
        "Connect it with the Genesis node.",
        routing_context,
        Project(
            _id="live-link-routing",
            name="Live link routing",
            introduction="Research project.",
        ),
    )
    decision = normalize_link_decision(decision, routing_context)

    assert decision.worker == "link"
    assert decision.root_id == "root_dawn"
    assert decision.target_ids == ["genesis_global"]
