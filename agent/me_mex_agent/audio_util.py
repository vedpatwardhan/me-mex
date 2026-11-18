"""PCM → WAV helpers for Colab STT."""

from __future__ import annotations

import io
import struct
import wave


def pcm16_mono_to_wav(pcm: bytes, sample_rate: int = 48000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def float32_to_pcm16(samples: list[float]) -> bytes:
    out = bytearray()
    for s in samples:
        clamped = max(-1.0, min(1.0, s))
        out.extend(struct.pack("<h", int(clamped * 32767)))
    return bytes(out)
