import pytest
from app.agents.conversation_turn import astream_conversation_turn
from app.agents.session_plane import build_session_briefing
from app.agents.turn_dispatch import is_dock_turn


@pytest.mark.dock_turn_plane
def test_spec_surface_exists():
    assert callable(build_session_briefing)
    assert callable(astream_conversation_turn)
    assert is_dock_turn({"dock_turn": True})
