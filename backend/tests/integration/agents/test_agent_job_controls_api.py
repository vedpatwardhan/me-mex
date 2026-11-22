import threading

import pytest
from app.agents import job_runtime, session_plane
from app.services.checkpoints import JsonCheckpointStore


@pytest.mark.voice_plane
def test_job_control_api_pauses_resumes_cancels_and_deletes(
    client, project, tmpdir_checkpoint, monkeypatch
):
    monkeypatch.setattr(
        session_plane,
        "_checkpoint",
        JsonCheckpointStore(str(tmpdir_checkpoint)),
    )
    thread_id = "job-control-api"
    job = {
        "job_id": "job-gist-api",
        "worker": "gist",
        "kind": "gist",
        "thread_id": thread_id,
        "project_id": project.id,
        "status": "running",
        "progress": "running",
    }
    job_runtime._jobs[job["job_id"]] = job
    job_runtime._by_thread[thread_id] = [job["job_id"]]
    job_runtime._cancel_events[job["job_id"]] = threading.Event()
    job_runtime._resume_events[job["job_id"]] = threading.Event()
    job_runtime._resume_events[job["job_id"]].set()
    params = {"project_id": project.id, "thread_id": thread_id}
    listed = client.get("/api/agent/jobs", params=params)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["job_id"] == job["job_id"]

    paused = client.post(f"/api/agent/jobs/{job['job_id']}/pause", params=params)
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    resumed = client.post(f"/api/agent/jobs/{job['job_id']}/resume", params=params)
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "running"

    cancelled = client.post(f"/api/agent/jobs/{job['job_id']}/cancel", params=params)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    deleted = client.post(f"/api/agent/jobs/{job['job_id']}/delete", params=params)
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert job_runtime.get_job(job["job_id"]) is None
    assert client.get("/api/agent/jobs", params=params).json()["items"] == []


@pytest.mark.voice_plane
def test_job_list_does_not_requeue_approved_jobs(client, project):
    thread_id = "job-list-approved"
    approved = {
        "job_id": "job-approved-gist",
        "worker": "gist",
        "thread_id": thread_id,
        "project_id": project.id,
        "status": "done",
        "approval_resolution": "approve",
    }
    done_without_approval = {
        "job_id": "job-readonly-retrieval",
        "worker": "retrieval",
        "thread_id": thread_id,
        "project_id": project.id,
        "status": "done",
    }
    job_runtime._jobs.update({job["job_id"]: job for job in (approved, done_without_approval)})
    job_runtime._by_thread[thread_id] = [approved["job_id"], done_without_approval["job_id"]]

    items = client.get(
        "/api/agent/jobs",
        params={"project_id": project.id, "thread_id": thread_id},
    ).json()["items"]

    assert [item["job_id"] for item in items] == ["job-readonly-retrieval"]
