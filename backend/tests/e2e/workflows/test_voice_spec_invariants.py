import pytest
from app.agents.conversation_voice import astream_conversation_voice
from app.agents.session_plane import build_session_briefing
from app.agents.voice_dispatch import is_voice_turn


@pytest.mark.voice_plane
def test_spec_surface_exists():
    assert callable(build_session_briefing)
    assert callable(astream_conversation_voice)
    assert is_voice_turn({"voice_turn": True})
