import pytest
from app.agents import session_plane
from app.services.checkpoints import JsonCheckpointStore


@pytest.mark.voice_plane
def test_transcript_append(tmpdir_checkpoint, monkeypatch):
    monkeypatch.setattr(session_plane, "_checkpoint", JsonCheckpointStore(str(tmpdir_checkpoint)))
    session_plane.append_transcript_turn("thr", role="user", text="hi")
    state = session_plane._checkpoint.load("thr")
    assert state["transcript"][-1]["text"] == "hi"
