import asyncio
import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.services.event_queue import event_queue
from app.agents.orchestrator import orchestrator
from app.services.llm_gateway import llm_gateway


def test_conversation_flow_continuity():
    """Verify that conversation mode maintains engaging, detailed multi-turn conversation."""
    if not llm_gateway.is_server_available():
        print("  ⏭️ test_conversation_flow_continuity [SKIPPED - vLLM Server Offline]")
        return

    async def _run():
        events = []
        async for event in orchestrator.process_user_message(
            "Hello Me-Mex! Can you tell me what your primary purpose is as a research assistant?",
            project_id="global",
        ):
            events.append(event)

        intent_evts = [e for e in events if e.get("event") == "intent_classified"]
        assert len(intent_evts) > 0
        assert intent_evts[0]["intent"] == "CONVERSATION"

        complete_evts = [e for e in events if e.get("event") == "chat_complete"]
        assert len(complete_evts) > 0
        final_ans = complete_evts[0].get("final_answer", "")
        assert len(final_ans) > 10
        assert (
            "research" in final_ans.lower()
            or "assistant" in final_ans.lower()
            or "me-mex" in final_ans.lower()
        )

    asyncio.run(_run())


def test_external_event_understanding():
    """Verify that externally pushed events (max 15 queue) are appended to system prompt and understood by orchestrator."""
    if not llm_gateway.is_server_available():
        print("  ⏭️ test_external_event_understanding [SKIPPED - vLLM Server Offline]")
        return

    # Simulate an external system pushing a custom event directly into event_queue
    external_event = {
        "event": "gpu_alert",
        "message": "High GPU Memory Usage Alert: 92% capacity reached on Node-01",
        "timestamp": 1700000000.0,
    }
    event_queue.push("global", external_event)

    # Verify event is in queue
    queued_events = event_queue.get_events("global", limit=15)
    assert any(e.event_type == "gpu_alert" for e in queued_events)

    async def _run():
        events = []
        async for event in orchestrator.process_user_message(
            "What just happened with the system GPU?",
            project_id="global",
        ):
            events.append(event)

        complete_evts = [e for e in events if e.get("event") == "chat_complete"]
        assert len(complete_evts) > 0
        reply = complete_evts[0].get("final_answer", "").lower()
        # Verify the model recognized the externally pushed GPU alert event
        assert "gpu" in reply or "memory" in reply or "92%" in reply or "alert" in reply

    asyncio.run(_run())
