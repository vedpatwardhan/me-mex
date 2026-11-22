import pytest
from app.agents.conversation_voice import (
    _astream_voice_conversation_reply,
    _conversation_prompt_inputs,
)
from app.config import settings


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
    assert len(answer.split()) <= 45
    assert any(
        phrase in answer
        for phrase in (
            "still being processed",
            "still being read",
            "don't have the findings",
            "do not have the findings",
            "not available yet",
            "when the gist is ready",
        )
    ), answer
