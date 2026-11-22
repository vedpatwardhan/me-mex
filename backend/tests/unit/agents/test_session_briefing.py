import pytest
from app.agents.session_plane import append_transcript_turn, build_session_briefing
from app.db import ToolContext
from app.tools import dock as dock_tools


@pytest.mark.voice_plane
def test_build_session_briefing(store, project, tmpdir_checkpoint, monkeypatch):
    from app.agents import session_plane

    monkeypatch.setattr(
        session_plane,
        "_checkpoint",
        __import__(
            "app.services.checkpoints", fromlist=["JsonCheckpointStore"]
        ).JsonCheckpointStore(str(tmpdir_checkpoint)),
    )
    append_transcript_turn("t1", role="user", text="hello")
    ctx = ToolContext(project_id=project.id, thread_id="t1", store=store)
    dock_tools.enqueue_pending_approval(
        ctx, approval_type="gist_root", title="t", payload={"gist": "g"}
    )
    b = build_session_briefing(project_id=project.id, thread_id="t1")
    assert b["pending_approval_count"] >= 1


@pytest.mark.voice_plane
def test_resolved_scope_approval_is_not_briefed_as_active_job(
    store, project, tmpdir_checkpoint, monkeypatch
):
    from app.agents import job_runtime, session_plane
    from app.services.checkpoints import JsonCheckpointStore

    checkpoint = JsonCheckpointStore(str(tmpdir_checkpoint))
    monkeypatch.setattr(session_plane, "_checkpoint", checkpoint)
    ctx = ToolContext(project_id=project.id, thread_id="resolved-scope", store=store)
    approval_id = dock_tools.enqueue_pending_approval(
        ctx,
        approval_type="project_scope",
        title="Review scope",
        payload={"proposed_introduction": "Research scope"},
    )
    job = {
        "job_id": "job-scope-stale",
        "worker": "project_scope",
        "kind": "project_scope",
        "thread_id": "resolved-scope",
        "project_id": project.id,
        "status": "awaiting_approval",
        "approval_id": approval_id,
        "recommendation_id": approval_id,
        "affinity_key": f"scope:{project.id}",
    }
    job_runtime._jobs[job["job_id"]] = job
    job_runtime._by_thread["resolved-scope"] = [job["job_id"]]
    state = checkpoint.load("resolved-scope") or {}
    state["jobs"] = [dict(job)]
    checkpoint.save("resolved-scope", state)
    store.resolve_approval(approval_id, "approve")

    briefing = build_session_briefing(project_id=project.id, thread_id="resolved-scope")

    assert briefing["pending_approval_count"] == 0
    assert briefing["active_jobs"] == []
    assert job_runtime.get_job(job["job_id"])["status"] == "resolved"
