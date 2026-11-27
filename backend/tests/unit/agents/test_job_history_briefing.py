from app.agents.session_plane import build_session_briefing, upsert_job_history


def test_recent_jobs_includes_cancelled_history(store, project, tmpdir_checkpoint, monkeypatch):
    from app.agents import session_plane
    from app.services.checkpoints import JsonCheckpointStore

    monkeypatch.setattr(session_plane, "_checkpoint", JsonCheckpointStore(str(tmpdir_checkpoint)))
    thread_id = "t-hist"
    upsert_job_history(
        thread_id,
        {
            "job_id": "job_cancelled_1",
            "worker": "intradoc",
            "status": "cancelled",
            "label": "third paper",
        },
    )
    briefing = build_session_briefing(project_id=project.id, thread_id=thread_id)
    recent = briefing.get("recent_jobs") or []
    ids = {row.get("job_id") for row in recent}
    assert "job_cancelled_1" in ids
