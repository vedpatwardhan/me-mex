import threading
from dataclasses import replace

from app.agents import session_plane, workers
from app.llm import get_chains, set_chains_override
from langchain_core.runnables import RunnableLambda
from tests.sse_util import iter_sse_data


def test_voice_source_gist_holds_then_returns_worker_result(
    client, project_scoped, voice_context_json, monkeypatch
):
    events = []
    followup_ready = threading.Event()
    conversation_inputs = []

    def conversation(inputs):
        conversation_inputs.append(inputs)
        if "[task_state]" in inputs["text"]:
            return "I’ll read the linked paper and share a concise summary when it’s ready."
        return "The May 2026 paper proposes a new predictive world model and evaluates it experimentally."

    base = get_chains()
    set_chains_override(
        replace(
            base,
            conversation=RunnableLambda(conversation),
            gist_draft=RunnableLambda(
                lambda inputs: (
                    "The paper proposes a new predictive world model and evaluates it experimentally."
                )
            ),
        )
    )
    monkeypatch.setattr(
        workers.fetch_tool,
        "fetch_normalized_text",
        lambda _ctx, url: {
            "text": "# Paper from May 2026\n\nActual source methods and results.",
            "content_hash": "source-hash",
            "url": url,
            "status": "SUCCESS",
        },
    )

    def publish(_thread_id, event):
        events.append(event)
        if event.get("type") == "assistant_followup":
            followup_ready.set()

    monkeypatch.setattr(session_plane, "publish_session_event", publish)
    context = {
        **voice_context_json,
        "active_project_id": project_scoped.id,
        "project_id": project_scoped.id,
        "custom_fields": {"paper": "https://arxiv.org/abs/2605.11550"},
    }
    response = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "Give me a short summary of this paper.",
            "thread_id": "voice-source-gist-flow",
            "context_json": context,
        },
    )
    chunks = list(iter_sse_data(response))
    end = next(chunk for chunk in chunks if chunk.get("type") == "turn_end")

    assert response.status_code == 200
    assert end["worker_kind"] == "gist"
    assert end["dispatched"] is True
    assert "read the linked paper" in end["reply"]
    assert "predictive world model" not in end["reply"]
    assert '"background_job_starting": true' in conversation_inputs[0]["text"]
    assert followup_ready.wait(timeout=5)
    followup = next(event for event in events if event.get("type") == "assistant_followup")
    assert "predictive world model" in followup["text"]
    assert "2605.11550" in conversation_inputs[1]["text"]
