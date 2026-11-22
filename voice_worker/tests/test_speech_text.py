from voice_agent.speech_text import speech_friendly


def test_expands_eg_for_tts():
    assert "for example" in speech_friendly("Topics, e.g. RSI, matter.").lower()


def test_expands_ie_and_etc():
    out = speech_friendly("One term i.e. the core idea etc.")
    assert "that is" in out.lower()
    assert "and so on" in out.lower()


def test_strips_leading_bullet_markers():
    out = speech_friendly("- First point\n1. Second")
    assert not out.startswith("-")
    assert "First point" in out
