"""Ingestion user-summary helpers and orchestrator wiring."""

import pytest

from app.config import settings
from app.services.ingest_summary import (
    build_ingestion_summary_user_message,
    query_asks_system_status,
)


def test_build_ingestion_summary_user_message_excludes_event_queue_markers():
    msg = build_ingestion_summary_user_message(
        "Sample Paper",
        "A short gist.",
        [{"title": "Concept A", "description": "One line."}],
    )
    assert "Sample Paper" in msg
    assert "Concept A" in msg
    assert "Recent System & Execution Events" not in msg
    assert "ingestion_phase_timings" not in msg


def test_query_asks_system_status():
    assert query_asks_system_status("What is the ingestion status?")
    assert not query_asks_system_status("Summarize the world model paper")


@pytest.mark.asyncio
async def test_execute_ingestion_summary_flow_options(monkeypatch):
    from app.agents.orchestrator import orchestrator

    captured: dict = {}

    async def fake_conv(*_args, **kwargs):
        captured.update(kwargs)
        yield {"event": "chat_complete", "final_answer": "Done.", "timestamp": 0.0}

    monkeypatch.setattr(orchestrator, "execute_conversation_flow", fake_conv)

    events = []
    async for evt in orchestrator.execute_ingestion_summary_flow(
        doc_title="Test Doc",
        doc_description="Gist.",
        canonical_concepts=[{"title": "T", "description": "D"}],
        project_id="global",
    ):
        events.append(evt)

    assert captured.get("include_event_queue") is False
    assert captured.get("max_tokens") == settings.INGESTION_SUMMARY_MAX_TOKENS
    override = (captured.get("system_prompt_override") or "").lower()
    assert "main concepts" in override and "do not mention graph edges" in override
    assert events[-1]["event"] == "chat_complete"


@pytest.mark.asyncio
async def test_conversation_flow_event_queue_gated_by_default(monkeypatch):
    from app.agents.orchestrator import orchestrator

    seen_system: list[str] = []

    async def fake_stream(messages, **kwargs):
        seen_system.append(messages[0]["content"])
        yield "Hi"

    monkeypatch.setattr(orchestrator.llm, "stream_chat_completion", fake_stream)

    async for _ in orchestrator.execute_conversation_flow(
        "Hello there",
        [],
        project_id="global",
    ):
        pass

    assert "Recent System & Execution Events" not in seen_system[0]
