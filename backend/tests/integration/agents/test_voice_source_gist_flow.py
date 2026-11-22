import threading
from dataclasses import replace

from app.agents import job_runtime, session_plane, workers
from app.llm import get_chains, set_chains_override
from langchain_core.runnables import RunnableLambda
from tests.sse_util import iter_sse_data


def test_voice_source_gist_holds_then_creates_reviewable_root_proposal(
    client, store, project_scoped, voice_context_json, monkeypatch
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
    thread_id = "voice-source-gist-flow"
    response = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "Give me a short summary of this paper.",
            "thread_id": thread_id,
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
    assert followup["text"] == (
        "The gist is ready in the dock for review. Approve it there to add it to the graph."
    )
    assert "2605.11550" in conversation_inputs[0]["text"]

    approvals = client.get(
        "/api/agent/approvals",
        params={"project_id": project_scoped.id, "thread_id": thread_id},
    ).json()["items"]
    gist_approval = next(item for item in approvals if item["approval_type"] == "gist_root")
    assert gist_approval["payload"]["gist"] == (
        "The paper proposes a new predictive world model and evaluates it experimentally."
    )
    assert gist_approval["payload"]["source_uri"] == "https://arxiv.org/pdf/2605.11550"

    approved = client.post(
        "/api/agent/resume",
        json={
            "thread_id": thread_id,
            "approval_id": gist_approval["id"],
            "action": "approve",
            "context_json": {"active_project_id": project_scoped.id},
        },
    )
    assert approved.status_code == 200
    root_id = approved.json()["result"]["root_id"]
    root = store.get_node(root_id)
    assert root.description == gist_approval["payload"]["gist"]
    assert root.source_uri == gist_approval["payload"]["source_uri"]
    gist_job = next(job for job in job_runtime.list_jobs(thread_id) if job["worker"] == "gist")
    assert gist_job["status"] == "done"
