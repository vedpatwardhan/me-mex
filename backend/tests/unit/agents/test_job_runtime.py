import threading

import pytest
from app.agents import job_runtime
from app.db import ToolContext


def test_park_active_jobs_marks_paused(tmpdir_checkpoint, monkeypatch):
    from app.agents import session_plane
    from app.services.checkpoints import JsonCheckpointStore

    monkeypatch.setattr(session_plane, "_checkpoint", JsonCheckpointStore(str(tmpdir_checkpoint)))
    job_runtime._jobs.clear()
    job_runtime._by_thread.clear()
    job_runtime._jobs["j1"] = {
        "job_id": "j1",
        "status": "running",
        "worker": "intradoc",
        "thread_id": "t-park",
    }
    job_runtime._by_thread["t-park"] = ["j1"]
    paused = job_runtime.park_active_jobs("t-park")
    assert len(paused) == 1
    assert paused[0]["status"] == "paused"
    assert job_runtime.get_job("j1")["status"] == "paused"


@pytest.mark.parametrize("worker", ["gist", "intradoc", "retrieval", "reorg"])
def test_running_worker_jobs_support_pause_resume_cancel_delete(
    worker, store, project, tmpdir_checkpoint, monkeypatch
):
    from app.agents import session_plane
    from app.services.checkpoints import JsonCheckpointStore

    monkeypatch.setattr(session_plane, "_checkpoint", JsonCheckpointStore(str(tmpdir_checkpoint)))
    job = {
        "job_id": f"job-{worker}",
        "worker": worker,
        "kind": worker,
        "thread_id": "job-control",
        "project_id": project.id,
        "status": "running",
        "progress": "running",
    }
    job_runtime._jobs[job["job_id"]] = job
    job_runtime._by_thread[job["thread_id"]] = [job["job_id"]]
    job_runtime._cancel_events[job["job_id"]] = threading.Event()
    job_runtime._resume_events[job["job_id"]] = threading.Event()
    job_runtime._resume_events[job["job_id"]].set()

    paused = job_runtime.control_job("job-control", job["job_id"], "pause", project_id=project.id)
    assert paused["status"] == "paused"
    resumed = job_runtime.control_job("job-control", job["job_id"], "resume", project_id=project.id)
    assert resumed["status"] == "running"
    cancelled = job_runtime.control_job(
        "job-control", job["job_id"], "cancel", project_id=project.id
    )
    assert cancelled["status"] == "cancelled"
    assert job_runtime.get_job(job["job_id"])["status"] == "cancelled"
    deleted = job_runtime.control_job("job-control", job["job_id"], "delete", project_id=project.id)
    assert deleted["status"] == "deleted"
    assert job_runtime.get_job(job["job_id"]) is None


def test_cancel_interrupts_at_worker_checkpoint(store, project, tmpdir_checkpoint, monkeypatch):
    from app.agents import session_plane
    from app.services.checkpoints import JsonCheckpointStore

    monkeypatch.setattr(session_plane, "_checkpoint", JsonCheckpointStore(str(tmpdir_checkpoint)))
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    side_effects = []

    def worker(_ctx: ToolContext, _text: str, context: dict) -> dict:
        try:
            started.set()
            release.wait(timeout=2)
            context["_job_control"]["checkpoint"]()
            side_effects.append("completed")
            return {"reply": "done", "graph_write": False}
        finally:
            finished.set()

    job = job_runtime.start_background_worker(
        thread_id="cancel-checkpoint",
        worker_kind="gist",
        ctx=ToolContext(project_id=project.id, thread_id="cancel-checkpoint", store=store),
        text="summarize",
        context={},
        worker_fn=worker,
    )
    assert started.wait(timeout=2)
    cancelled = job_runtime.control_job(
        "cancel-checkpoint", job["job_id"], "cancel", project_id=project.id
    )
    assert cancelled["status"] == "cancelled"
    release.set()
    assert finished.wait(timeout=2)
    assert side_effects == []
    assert job_runtime.get_job(job["job_id"])["status"] == "cancelled"
