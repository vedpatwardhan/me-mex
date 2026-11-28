import pytest
from app.agents.session_plane import append_transcript_turn, build_session_briefing
from app.db import ToolContext
from app.tools import dock as dock_tools


@pytest.mark.dock_turn_plane
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


@pytest.mark.dock_turn_plane
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


@pytest.mark.dock_turn_plane
def test_briefing_separates_active_job_status_from_completed_source_evidence(
    store, project, tmpdir_checkpoint, monkeypatch
):
    from app.agents import job_runtime, session_plane
    from app.services.checkpoints import JsonCheckpointStore

    checkpoint = JsonCheckpointStore(str(tmpdir_checkpoint))
    monkeypatch.setattr(session_plane, "_checkpoint", checkpoint)
    thread_id = "briefing-evidence-boundary"
    jobs = [
        {
            "job_id": "job-gist-running",
            "worker": "gist",
            "kind": "gist",
            "label": "Read current paper",
            "status": "running",
            "thread_id": thread_id,
            "project_id": project.id,
            "output": {"source_summary": "This is not complete evidence."},
        },
        {
            "job_id": "job-gist-complete",
            "worker": "gist",
            "kind": "gist",
            "label": "Earlier paper",
            "status": "done",
            "thread_id": thread_id,
            "project_id": project.id,
            "output": {
                "source_title": "Completed paper",
                "source_url": "https://example.test/paper.pdf",
                "source_summary": "The completed paper studies a latent model.",
            },
        },
    ]
    job_runtime._by_thread[thread_id] = [job["job_id"] for job in jobs]
    job_runtime._jobs.update({job["job_id"]: job for job in jobs})

    briefing = session_plane.build_session_briefing(project_id=project.id, thread_id=thread_id)

    assert [job["job_id"] for job in briefing["active_jobs"]] == ["job-gist-running"]
    assert "output" not in briefing["active_jobs"][0]
    assert briefing["completed_worker_results"] == [
        {
            "job_id": "job-gist-complete",
            "worker": "gist",
            "status": "done",
            "label": "Earlier paper",
            "source_title": "Completed paper",
            "source_url": "https://example.test/paper.pdf",
            "result": "The completed paper studies a latent model.",
        }
    ]
