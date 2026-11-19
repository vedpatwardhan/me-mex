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
