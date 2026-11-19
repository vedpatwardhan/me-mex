from app.agents import job_runtime


def test_park_active_jobs_marks_paused():
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
