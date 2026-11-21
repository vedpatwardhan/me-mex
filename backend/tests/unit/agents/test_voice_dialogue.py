from app.agents.voice_dialogue import is_dialogue_only_utterance, user_asked_for_status


def test_dialogue_only_short_and_chitchat():
    assert is_dialogue_only_utterance("your debuting so far.")
    assert is_dialogue_only_utterance("how's your day")
    assert not is_dialogue_only_utterance(
        "Robotics manipulation and sim-to-real for warehouse picking."
    )


def test_user_asked_for_status():
    assert user_asked_for_status("what's in the queue?")
    assert not user_asked_for_status("hello there friend")
