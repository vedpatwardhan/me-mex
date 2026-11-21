import pytest
from app.agents.voice_dispatch import needs_voice_dispatch


@pytest.mark.voice_plane
@pytest.mark.parametrize(
    "worker,voice,expected",
    [
        ("conversation", True, False),
        ("retrieval", True, True),
        ("intradoc", True, True),
        ("conversation", False, False),
    ],
)
def test_needs_voice_dispatch(worker, voice, expected):
    assert needs_voice_dispatch(worker, voice_turn=voice) is expected


@pytest.mark.voice_plane
def test_project_scope_conditional_voice_dispatch():
    assert (
        needs_voice_dispatch(
            "project_scope",
            voice_turn=True,
            text="Robotics manipulation and sim-to-real transfer.",
        )
        is True
    )
    assert needs_voice_dispatch("project_scope", voice_turn=True, text="how's your day") is False
    assert needs_voice_dispatch("project_scope", voice_turn=True, text="save scope: intro") is True
    assert needs_voice_dispatch("project_scope", voice_turn=False, text="save scope") is False
