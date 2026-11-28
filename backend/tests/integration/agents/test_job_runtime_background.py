import time

import pytest
from app.agents import job_runtime
from app.agents.worker_registry import worker_handler
from app.db import ToolContext


@pytest.mark.dock_turn_plane
def test_background_worker_lifecycle(store, project):
    ctx = ToolContext(project_id=project.id, thread_id="bg-t", store=store)
    fn = worker_handler("retrieval")
    assert fn
    job = job_runtime.start_background_worker(
        thread_id="bg-t",
        worker_kind="retrieval",
        ctx=ctx,
        text="What relates to grasping?",
        context={},
        worker_fn=fn,
        project_id=project.id,
    )
    assert job["status"] == "running"
    deadline = time.monotonic() + 45.0
    while time.monotonic() < deadline:
        jobs = job_runtime.list_jobs("bg-t")
        if jobs and jobs[-1].get("status") in ("done", "awaiting_approval", "error"):
            break
        time.sleep(0.1)
    jobs = job_runtime.list_jobs("bg-t")
    assert jobs
    assert jobs[0]["status"] in ("done", "awaiting_approval")
