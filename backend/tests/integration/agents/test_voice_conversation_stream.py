import threading
import time
from dataclasses import replace

import pytest
from app.agents import session_plane
from app.db import ToolContext
from app.llm import get_chains, set_chains_override
from app.llm.schemas import WorkerRoute
from app.services.checkpoints import JsonCheckpointStore
from app.tools import gist
from langchain_core.runnables import RunnableLambda
from tests.sse_util import iter_sse_data

pytestmark = pytest.mark.voice_plane


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
def test_supervisor_reply_avoids_a_second_sequential_conversation_call(
    client, project_scoped, monkeypatch
):
    base = get_chains()
    conversation_called = False

    def fail_conversation(_inputs):
        nonlocal conversation_called
        conversation_called = True
        raise AssertionError("Supervisor already produced the conversation reply")

    supervisor = RunnableLambda(
        lambda _inputs: WorkerRoute(
            worker="conversation",
            intent="conversation",
            dispatch=False,
            reply="The project is scoped around RSI research.",
        )
    )
    set_chains_override(
        replace(
            base,
            supervisor=supervisor,
            conversation=RunnableLambda(fail_conversation),
        )
    )
    response = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "What is this project about?",
            "thread_id": "voice-supervisor-reply",
            "context_json": {
                "voice_turn": True,
                "active_project_id": project_scoped.id,
                "project_id": project_scoped.id,
                "custom_fields": {},
            },
        },
    )

    chunks = list(iter_sse_data(response))
    end = next(chunk for chunk in chunks if chunk.get("type") == "turn_end")
    assert end["reply"] == "The project is scoped around RSI research."
    assert conversation_called is False


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
                "custom_fields": {"paper": "https://arxiv.org/pdf/2605.11550"},
            },
        },
    )

    assert response.status_code == 200
    chunks = list(iter_sse_data(response))
    end = next(chunk for chunk in chunks if chunk.get("type") == "turn_end")
    assert end["details"]["route"] == "conversation"
    assert parked == []


@pytest.mark.voice_plane
def test_gist_for_another_source_leaves_running_intradoc_job_running(
    client, project_scoped, monkeypatch
):
    from app.agents import conversation_voice, job_runtime

    thread_id = "voice-independent-jobs"
    existing = {
        "job_id": "intradoc-paper-one",
        "worker": "intradoc",
        "kind": "intradoc",
        "thread_id": thread_id,
        "project_id": project_scoped.id,
        "status": "running",
        "affinity_key": "intradoc:first-source",
    }
    job_runtime._jobs[existing["job_id"]] = existing
    job_runtime._by_thread[thread_id] = [existing["job_id"]]
    base = get_chains()

    def route(_inputs):
        return WorkerRoute(
            worker="gist",
            intent="source_summary",
            dispatch=True,
            source_field="paper",
            source_reference="https://example.test/second.pdf",
        )

    finished = threading.Event()

    def gist_stub(_ctx, _text, _context):
        finished.set()
        return {"reply": "Gist ready.", "graph_write": False}

    monkeypatch.setattr(conversation_voice, "worker_handler", lambda _worker: gist_stub)
    set_chains_override(replace(base, supervisor=RunnableLambda(route)))
    response = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "Give me a broad overview of this other paper.\npaper=https://example.test/second.pdf",
            "thread_id": thread_id,
            "context_json": {
                "voice_turn": True,
                "active_project_id": project_scoped.id,
                "custom_fields": {"paper": "https://example.test/second.pdf"},
            },
        },
    )
    end = next(chunk for chunk in iter_sse_data(response) if chunk.get("type") == "turn_end")

    assert response.status_code == 200
    assert end["worker_kind"] == "gist"
    assert end["dispatched"] is True
    assert finished.wait(timeout=2)
    assert job_runtime.get_job(existing["job_id"])["status"] == "running"


@pytest.mark.voice_plane
def test_multi_paper_mixed_workers_dispatches_three_jobs_despite_supervisor_pin(
    client, project_scoped, monkeypatch
):
    from app.agents import conversation_voice, job_runtime

    thread_id = "voice-multi-paper-mixed"
    job_runtime._by_thread.pop(thread_id, None)
    for job_id in list(job_runtime._jobs):
        if job_runtime._jobs[job_id].get("thread_id") == thread_id:
            job_runtime._jobs.pop(job_id, None)

    calls: list[str] = []

    def worker_stub(worker: str):
        def _run(_ctx, _text, _context):
            calls.append(worker)
            return {"reply": f"{worker} ready.", "graph_write": False}

        return _run

    monkeypatch.setattr(conversation_voice, "worker_handler", worker_stub)
    text = (
        "I have just attached a link to three different papers. "
        "I need a high level summary of the first two papers and I need a "
        "detailed understanding of the third paper."
    )
    response = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": text,
            "thread_id": thread_id,
            "context_json": {
                "voice_turn": True,
                "active_project_id": project_scoped.id,
                "custom_fields": {
                    "paper1": "https://arxiv.org/pdf/2605.11550",
                    "paper2": "https://arxiv.org/pdf/2610.20951",
                    "paper3": "https://arxiv.org/pdf/2610.38568",
                },
            },
        },
    )
    chunks = list(iter_sse_data(response))
    end = next(chunk for chunk in chunks if chunk.get("type") == "turn_end")
    jobs = [chunk.get("job") for chunk in chunks if chunk.get("type") == "custom"]
    assert response.status_code == 200
    assert end["dispatched"] is True
    assert len(end["job_ids"]) == 3
    assert sorted(calls) == ["gist", "gist", "intradoc"]
    assert len(jobs) == 3
    assert "background job" in (end.get("reply") or "").lower()


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
                "custom_fields": {"paper": "https://arxiv.org/pdf/2605.11550"},
            },
        },
    )

    assert response.status_code == 200
    chunks = list(iter_sse_data(response))
    end = next(chunk for chunk in chunks if chunk.get("type") == "turn_end")
    assert end["reply"]
    assert "while" in end["reply"].lower() or "read" in end["reply"].lower()
    assert end["dispatched"] is False
    assert end["worker_kind"] is None
    assert '"job_id": "job-in-progress"' in conversation_inputs[0]["text"]
    assert "2605.11550" not in conversation_inputs[0]["text"]
    active_jobs = supervisor_inputs[0]["context"]["session_state"]["active_jobs"]
    assert active_jobs[0]["job_id"] == "job-in-progress"


@pytest.mark.voice_plane
def test_scope_completion_acknowledgement_stays_in_conversation(client, store, project_scoped):
    from app.agents import job_runtime

    base = get_chains()
    seen = {}
    thread_id = "voice-scope-complete-next"
    completed_scope_job = {
        "job_id": "job-scope-already-done",
        "worker": "project_scope",
        "kind": "project_scope",
        "status": "done",
        "label": "The scope proposal was approved",
        "thread_id": thread_id,
        "project_id": project_scoped.id,
    }
    job_runtime._jobs[completed_scope_job["job_id"]] = completed_scope_job
    job_runtime._by_thread[thread_id] = [completed_scope_job["job_id"]]

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
    assert all(job["job_id"] != completed_scope_job["job_id"] for job in end["jobs"])


@pytest.mark.voice_plane
def test_post_scope_next_steps_ignores_supervisor_scope_review_reply(
    client,
    store,
    project_scoped,
    monkeypatch,
):
    """Supervisor often mis-replies 'review scope in dock'; Conversation must answer instead."""
    base = get_chains()
    conversation_called = []

    def supervisor(_inputs):
        return WorkerRoute(
            worker="conversation",
            intent="conversation",
            dispatch=False,
            reply=None,
        )

    def conversation(inp):
        conversation_called.append(inp)
        return (
            "Scope is set. Next we build the graph from sources you share—papers, blogs, or articles. "
            "Which link would you like to start with?"
        )

    set_chains_override(
        replace(
            base,
            supervisor=RunnableLambda(supervisor),
            conversation=RunnableLambda(conversation),
            project_scope=RunnableLambda(
                lambda _inputs: (_ for _ in ()).throw(AssertionError("scope"))
            ),
        )
    )
    response = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "I'd like to proceed with the next steps, what's next.",
            "thread_id": "voice-post-scope-next-fix",
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
    reply = str(end.get("reply") or "")
    assert "proposed scope" not in reply.lower()
    assert "explore" not in reply.lower() or "graph" in reply.lower()
    assert "graph" in reply.lower() or "source" in reply.lower() or "link" in reply.lower()
    assert conversation_called
    assert conversation_called[0].get("project_scope")


@pytest.mark.voice_plane
def test_voice_job_control_cancels_selected_job_without_dispatching_new_work(
    client, project_scoped, tmpdir_checkpoint, monkeypatch
):
    from app.agents import job_runtime, session_plane
    from app.services.checkpoints import JsonCheckpointStore

    monkeypatch.setattr(session_plane, "_checkpoint", JsonCheckpointStore(str(tmpdir_checkpoint)))
    base = get_chains()
    thread_id = "voice-job-cancel"
    job = {
        "job_id": "job-redundant-gist",
        "worker": "gist",
        "kind": "gist",
        "status": "running",
        "label": "Summarize the first paper",
        "thread_id": thread_id,
        "project_id": project_scoped.id,
        "affinity_key": "gist:first-paper",
    }
    job_runtime._jobs[job["job_id"]] = job
    job_runtime._by_thread[thread_id] = [job["job_id"]]
    job_runtime._cancel_events[job["job_id"]] = threading.Event()
    job_runtime._resume_events[job["job_id"]] = threading.Event()
    job_runtime._resume_events[job["job_id"]].set()

    def conversation_must_not_run(_inputs):
        raise AssertionError("job control must not be handled as ordinary chat")

    set_chains_override(
        replace(
            base,
            supervisor=RunnableLambda(
                lambda _inputs: WorkerRoute(
                    worker="job_control",
                    intent="job_control",
                    dispatch=True,
                    target_id=job["job_id"],
                    job_action="cancel",
                )
            ),
            conversation=RunnableLambda(conversation_must_not_run),
        )
    )

    response = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "Abort the redundant gist job for the first paper.",
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
    assert end["details"]["job_action"] == "cancel"
    assert end["details"]["job_status"] == "cancelled"
    assert "cancelled" in end["reply"].lower()
    assert job_runtime.get_job(job["job_id"])["status"] == "cancelled"

    from app.prompts import load_prompt

    assert "worker=job_control" in load_prompt("worker_route")


@pytest.mark.voice_plane
def test_voice_status_check_does_not_pause_misrouted_job_control(
    client, project_scoped, tmpdir_checkpoint, monkeypatch
):
    from app.agents import job_runtime, session_plane
    from app.services.checkpoints import JsonCheckpointStore

    monkeypatch.setattr(session_plane, "_checkpoint", JsonCheckpointStore(str(tmpdir_checkpoint)))
    base = get_chains()
    thread_id = "voice-status-not-pause"
    job = {
        "job_id": "job-third-gist",
        "worker": "gist",
        "kind": "gist",
        "status": "running",
        "label": "Third paper gist",
        "thread_id": thread_id,
        "project_id": project_scoped.id,
        "affinity_key": "gist:third",
    }
    job_runtime._jobs[job["job_id"]] = job
    job_runtime._by_thread[thread_id] = [job["job_id"]]
    job_runtime._cancel_events[job["job_id"]] = threading.Event()
    job_runtime._resume_events[job["job_id"]] = threading.Event()
    job_runtime._resume_events[job["job_id"]].set()

    def conversation_must_not_pause(_inputs):
        return "The gist job is still running."

    set_chains_override(
        replace(
            base,
            supervisor=RunnableLambda(
                lambda _inputs: WorkerRoute(
                    worker="conversation",
                    intent="status",
                    dispatch=False,
                    target_id=job["job_id"],
                )
            ),
            conversation=RunnableLambda(conversation_must_not_pause),
        )
    )

    response = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": (
                "What is the status of the job for the third paper gist? Just a status check."
            ),
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
    assert end.get("worker_kind") != "job_control"
    assert job_runtime.get_job(job["job_id"])["status"] == "running"
    assert "pause" not in (end.get("reply") or "").lower()


@pytest.mark.voice_plane
def test_voice_link_resolves_named_nodes_and_commits_the_requested_edge(
    client, store, project_scoped, tmpdir_checkpoint, monkeypatch
):
    thread_id = "voice-link-targets"
    monkeypatch.setattr(session_plane, "_checkpoint", JsonCheckpointStore(str(tmpdir_checkpoint)))
    ctx = ToolContext(
        project_id=project_scoped.id,
        thread_id="voice-link-targets",
        store=store,
    )
    earlier = gist.create_or_update_root_gist(
        ctx,
        title="An earlier paper",
        gist="Earlier source gist.",
    )
    dawn = gist.create_or_update_root_gist(
        ctx,
        title="The DAWN of World-Action Interactive Models",
        gist="Source gist.",
    )
    genesis_id = store.get_project(project_scoped.id).genesis_node_id
    session_plane.append_transcript_turn(
        thread_id,
        role="user",
        text="Please add the DAWN paper gist to this project.",
    )
    session_plane.append_transcript_turn(
        thread_id,
        role="assistant",
        text="The DAWN paper gist was approved and added to the graph as a ROOT.",
    )
    session_plane.record_recent_graph_change(
        store=store,
        project_id=project_scoped.id,
        thread_id=thread_id,
        operation="gist_root",
        payload={},
        result={"result": {"root_id": earlier["root_id"]}},
    )
    session_plane.record_recent_graph_change(
        store=store,
        project_id=project_scoped.id,
        thread_id=thread_id,
        operation="gist_root",
        payload={},
        result={"result": {"root_id": dawn["root_id"]}},
    )
    session_plane.record_routing_source(
        thread_id,
        worker="gist",
        source_url="https://arxiv.org/pdf/dawn.pdf",
        title="The DAWN of World-Action Interactive Models",
        root_id=dawn["root_id"],
    )

    response = client.post(
        "/api/voice/conversation/stream",
        json={
            "text": "Connect it with the Genesis node.",
            "thread_id": thread_id,
            "context_json": {
                "voice_turn": True,
                "active_project_id": project_scoped.id,
                "project_id": project_scoped.id,
                "custom_fields": {},
            },
        },
    )
    end = next(chunk for chunk in iter_sse_data(response) if chunk.get("type") == "turn_end")
    assert response.status_code == 200
    assert end["worker_kind"] == "link"
    assert end["dispatched"] is True

    approvals = []
    for _ in range(100):
        approvals = client.get(
            "/api/agent/approvals",
            params={"project_id": project_scoped.id, "thread_id": thread_id},
        ).json()["items"]
        if approvals:
            break
        time.sleep(0.01)
    placement = next(item for item in approvals if item["approval_type"] == "placement")
    assert placement["payload"]["root_id"] == dawn["root_id"]
    assert placement["payload"]["candidates"][0][0] == genesis_id

    approved = client.post(
        "/api/agent/resume",
        json={
            "thread_id": thread_id,
            "approval_id": placement["id"],
            "action": "approve",
            "context_json": {"active_project_id": project_scoped.id},
        },
    )
    assert approved.status_code == 200
    assert genesis_id in store.neighbors(dawn["root_id"])
    latest_change = session_plane.build_routing_memory(thread_id)["recent_graph_changes"][-1]
    assert latest_change["operation"] == "placement"
    assert {node["id"] for node in latest_change["nodes"]} == {
        dawn["root_id"],
        genesis_id,
    }
