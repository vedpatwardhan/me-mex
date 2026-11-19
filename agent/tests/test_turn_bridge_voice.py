from me_mex_agent.turn_bridge import _use_voice_conversation_stream


def test_use_voice_conversation_stream_flag():
    assert _use_voice_conversation_stream({"voice_turn": True})
    assert not _use_voice_conversation_stream({})
