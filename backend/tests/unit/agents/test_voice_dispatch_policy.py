import pytest
from app.agents.voice_dispatch import needs_voice_dispatch
from app.llm.schemas import WorkerRoute


@pytest.mark.voice_plane
@pytest.mark.parametrize(
    "decision,voice,expected",
    [
        (WorkerRoute(worker="conversation", intent="conversation", dispatch=False), True, False),
        (WorkerRoute(worker="retrieval", intent="retrieval", dispatch=True), True, True),
        (WorkerRoute(worker="intradoc", intent="source_analysis", dispatch=True), True, True),
        (WorkerRoute(worker="conversation", intent="conversation", dispatch=False), False, False),
    ],
)
def test_needs_voice_dispatch(decision, voice, expected):
    assert needs_voice_dispatch(decision, voice_turn=voice) is expected


@pytest.mark.voice_plane
def test_project_scope_dispatch_comes_from_supervisor_decision():
    proposal = WorkerRoute(worker="project_scope", intent="scope_save", dispatch=True)
    conversation = WorkerRoute(worker="project_scope", intent="scope_conversation", dispatch=False)
    assert needs_voice_dispatch(proposal, voice_turn=True) is True
    assert needs_voice_dispatch(conversation, voice_turn=True) is False
    assert needs_voice_dispatch(proposal, voice_turn=False) is False
