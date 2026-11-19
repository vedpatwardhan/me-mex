import struct
from types import SimpleNamespace

from me_mex_agent.audio_util import frame_to_mono_floats, should_end_utterance


def test_frame_to_mono_floats_stereo_interleaved():
    # L=10000, R=-10000 → mean ~0; L=16000, R=16000 → strong signal
    samples = struct.pack("<hhhh", 16000, 16000, 0, 0)
    frame = SimpleNamespace(
        sample_rate=48000,
        num_channels=2,
        samples_per_channel=2,
        data=samples,
    )
    floats, _frame_ms = frame_to_mono_floats(frame)
    assert len(floats) == 2
    assert max(abs(f) for f in floats) > 0.4


def test_should_not_end_before_min_speech_or_silence():
    assert not should_end_utterance(
        speaking_ms=300,
        silent_ms=2000,
        buffer_nonempty=True,
        min_utterance_ms=400,
        max_utterance_ms=20000,
        end_silence_ms=1500,
    )


def test_should_end_after_trailing_silence():
    assert should_end_utterance(
        speaking_ms=800,
        silent_ms=1501,
        buffer_nonempty=True,
        min_utterance_ms=400,
        max_utterance_ms=20000,
        end_silence_ms=1500,
    )


def test_should_end_at_max_utterance():
    assert should_end_utterance(
        speaking_ms=20000,
        silent_ms=0,
        buffer_nonempty=True,
        min_utterance_ms=400,
        max_utterance_ms=20000,
        end_silence_ms=1500,
    )


def test_old_600ms_threshold_would_have_ended_early():
    assert not should_end_utterance(
        speaking_ms=500,
        silent_ms=700,
        buffer_nonempty=True,
        min_utterance_ms=400,
        max_utterance_ms=20000,
        end_silence_ms=1500,
    )
    assert should_end_utterance(
        speaking_ms=500,
        silent_ms=700,
        buffer_nonempty=True,
        min_utterance_ms=400,
        max_utterance_ms=20000,
        end_silence_ms=600,
    )
