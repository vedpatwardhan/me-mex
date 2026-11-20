import struct
from types import SimpleNamespace

import pytest
from livekit import rtc
from voice_agent.vad_silero import (
    MIN_UTTERANCE_MS,
    frame_to_mono_rtc_frame,
    vad_frames_to_wav,
)


def test_vad_frames_to_wav_duration():
    sample_rate = 48000
    nbytes = sample_rate * 2  # 1 second mono int16
    pcm = b"\x00\x01" * (nbytes // 2)
    frame = rtc.AudioFrame(
        data=pcm,
        sample_rate=sample_rate,
        num_channels=1,
        samples_per_channel=nbytes // 2,
    )
    wav, duration = vad_frames_to_wav([frame])
    assert len(wav) > 44
    assert duration == pytest.approx(1.0, rel=0.01)


def test_vad_frames_to_wav_rejects_short_for_min_utterance_logic():
    sample_rate = 48000
    # 0.1s of audio
    nbytes = int(sample_rate * 0.1) * 2
    pcm = b"\x00" * nbytes
    frame = rtc.AudioFrame(
        data=pcm,
        sample_rate=sample_rate,
        num_channels=1,
        samples_per_channel=nbytes // 2,
    )
    wav, duration = vad_frames_to_wav([frame])
    assert duration < MIN_UTTERANCE_MS / 1000.0
    assert wav  # still valid wav bytes


def test_frame_to_mono_rtc_frame_stereo():
    samples = struct.pack("<hhhh", 16000, 16000, 0, 0)
    frame = SimpleNamespace(
        sample_rate=48000,
        num_channels=2,
        samples_per_channel=2,
        data=samples,
    )
    mono = frame_to_mono_rtc_frame(frame)  # type: ignore[arg-type]
    assert mono.num_channels == 1
    assert mono.samples_per_channel == 2
