from dataclasses import replace

import pytest
from app.llm import get_chains, set_chains_override
from app.llm.schemas import WorkerRoute
from langchain_core.runnables import RunnableLambda
from tests.sse_util import iter_sse_data


@pytest.mark.voice_plane
def test_voice_conversation_stream(client, project, voice_context_json, mock_vllm_chat):
    r = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "hello",
            "thread_id": "voice-stream",
            "context_json": voice_context_json,
        },
    )
    assert r.status_code == 200
    chunks = list(iter_sse_data(r))
    types = {c.get("type") for c in chunks}
    assert "token" in types
    assert "turn_end" in types
    tokens = [c for c in chunks if c.get("type") == "token"]
    assert len(tokens) >= 1
    end = next(c for c in chunks if c.get("type") == "turn_end")
    assert end.get("source") == "conversation"
    assert end.get("reply")
    joined = "".join(c.get("content") or "" for c in tokens)
    assert joined == end.get("reply")


@pytest.mark.voice_plane
def test_conversation_turn_does_not_park_background_jobs(
    client, project_scoped, mock_vllm_chat, monkeypatch
):
    from app.agents import job_runtime

    parked = []
    monkeypatch.setattr(job_runtime, "park_active_jobs", lambda thread_id: parked.append(thread_id))
    response = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "While that paper is being read, let's talk about what I should focus on.",
            "thread_id": "voice-background-chat",
            "context_json": {
                "voice_turn": True,
                "active_project_id": project_scoped.id,
                "project_id": project_scoped.id,
                "custom_fields": {},
            },
        },
    )

    assert response.status_code == 200
    chunks = list(iter_sse_data(response))
    end = next(chunk for chunk in chunks if chunk.get("type") == "turn_end")
    assert end["details"]["route"] == "conversation"
    assert parked == []


@pytest.mark.voice_plane
def test_malformed_supervisor_output_falls_back_to_spoken_conversation(client, project_scoped):
    from app.agents import job_runtime

    base = get_chains()
    thread_id = "voice-supervisor-fallback"
    job_runtime._jobs["job-in-progress"] = {
        "job_id": "job-in-progress",
        "worker": "gist",
        "kind": "gist",
        "label": "Read the supplied paper",
        "status": "running",
        "thread_id": thread_id,
        "project_id": project_scoped.id,
        "affinity_key": f"gist:{project_scoped.id}",
    }
    job_runtime._by_thread[thread_id] = ["job-in-progress"]
    conversation_inputs = []
    supervisor_inputs = []

    def fail(inputs):
        supervisor_inputs.append(inputs)
        raise RuntimeError("invalid structured WorkerRoute")

    def conversation(inputs):
        conversation_inputs.append(inputs)
        return "We can discuss the idea at a high level while the paper is being read."

    set_chains_override(
        replace(
            base,
            supervisor=RunnableLambda(fail),
            conversation=RunnableLambda(conversation),
        )
    )
    response = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "What do you think about this idea generally?",
            "thread_id": thread_id,
            "context_json": {
                "voice_turn": True,
                "active_project_id": project_scoped.id,
                "project_id": project_scoped.id,
                "custom_fields": {},
            },
        },
    )

    assert response.status_code == 200
    chunks = list(iter_sse_data(response))
    end = next(chunk for chunk in chunks if chunk.get("type") == "turn_end")
    assert end["reply"] == "We can discuss the idea at a high level while the paper is being read."
    assert end["dispatched"] is False
    assert end["worker_kind"] is None
    assert '"job_id": "job-in-progress"' in conversation_inputs[0]["text"]
    active_jobs = supervisor_inputs[0]["context"]["session_state"]["active_jobs"]
    assert active_jobs[0]["job_id"] == "job-in-progress"


@pytest.mark.voice_plane
def test_scope_completion_acknowledgement_stays_in_conversation(client, store, project_scoped):
    base = get_chains()
    seen = {}

    def supervisor(inputs):
        seen.update(inputs)
        return WorkerRoute(worker="conversation", intent="conversation", dispatch=False)

    def unexpected_scope_call(_inputs):
        raise AssertionError("a scope acknowledgement should not run ProjectScope")

    set_chains_override(
        replace(
            base,
            supervisor=RunnableLambda(supervisor),
            conversation=RunnableLambda(lambda _inputs: "Let's start with a paper you choose."),
            project_scope=RunnableLambda(unexpected_scope_call),
        )
    )
    thread_id = "voice-scope-complete-next"
    response = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "The project scope is done; what is next?",
            "thread_id": thread_id,
            "context_json": {
                "voice_turn": True,
                "active_project_id": project_scoped.id,
                "project_id": project_scoped.id,
                "custom_fields": {},
            },
        },
    )

    assert response.status_code == 200
    end = next(chunk for chunk in iter_sse_data(response) if chunk.get("type") == "turn_end")
    assert end["reply"] == "Let's start with a paper you choose."
    assert end["dispatched"] is False
    assert seen["context"]["project_scope_status"] == "committed"
    assert seen["context"]["scope_approval_pending"] is False
    assert store.list_pending(project_scoped.id, thread_id) == []
