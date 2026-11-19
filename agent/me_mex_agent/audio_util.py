"""PCM → WAV helpers for Colab STT."""

from __future__ import annotations

import io
import struct
import wave
from typing import Any


def frame_to_mono_floats(frame: Any) -> tuple[list[float], int]:
    """LiveKit AudioFrame is int16 interleaved by channel → mono floats + frame duration ms."""
    sample_rate = int(getattr(frame, "sample_rate", 48000) or 48000)
    n_ch = max(1, int(getattr(frame, "num_channels", 1) or 1))
    n = int(getattr(frame, "samples_per_channel", 0) or 0)
    if n <= 0:
        return [], 0
    nbytes = n * n_ch * 2
    raw = bytes(getattr(frame, "data", b"") or b"")[:nbytes]
    if len(raw) < nbytes:
        return [], 0
    all_s = struct.unpack(f"<{n * n_ch}h", raw)
    if n_ch == 1:
        floats = [s / 32768.0 for s in all_s]
    else:
        floats = [sum(all_s[i : i + n_ch]) / (32768.0 * n_ch) for i in range(0, len(all_s), n_ch)]
    frame_ms = int(1000 * len(floats) / sample_rate) if sample_rate else 0
    return floats, frame_ms


def pcm16_mono_to_wav(pcm: bytes, sample_rate: int = 48000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def should_end_utterance(
    *,
    speaking_ms: int,
    silent_ms: int,
    buffer_nonempty: bool,
    min_utterance_ms: int,
    max_utterance_ms: int,
    end_silence_ms: int,
) -> bool:
    """True when RMS VAD should flush the buffered utterance to STT."""
    if speaking_ms >= max_utterance_ms:
        return True
    return buffer_nonempty and silent_ms > end_silence_ms and speaking_ms >= min_utterance_ms


def float32_to_pcm16(samples: list[float]) -> bytes:
    out = bytearray()
    for s in samples:
        clamped = max(-1.0, min(1.0, s))
        out.extend(struct.pack("<h", int(clamped * 32767)))
    return bytes(out)
