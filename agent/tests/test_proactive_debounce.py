from me_mex_agent.worker import RoomSession


def test_proactive_spoken_set():
    session = RoomSession()
    session.proactive_spoken.add("job-1")
    assert "job-1" in session.proactive_spoken
    session.proactive_spoken.add("job-1")
    assert len(session.proactive_spoken) == 1
