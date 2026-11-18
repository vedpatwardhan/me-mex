import pytest
from app.services.speech_client import ColabSpeechClient


def test_speech_client_disabled_without_url():
    c = ColabSpeechClient(base_url="")
    assert c.enabled() is False


@pytest.mark.asyncio
async def test_speech_client_requires_url():
    c = ColabSpeechClient(base_url="")
    with pytest.raises(RuntimeError, match="COLAB_SPEECH_BASE_URL"):
        await c.synthesize("hello")
