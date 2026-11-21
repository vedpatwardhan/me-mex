"""Silero VAD utterance collection (local CPU) with flush-on-mute."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from livekit import rtc
from livekit.agents.vad import VADEventType

from voice_agent.audio_util import (
    float32_to_pcm16,
    frame_to_mono_floats,
    pcm16_mono_to_wav,
)

if TYPE_CHECKING:
    from livekit.agents.vad import VAD

_log = logging.getLogger(__name__)

VOICE_VAD = os.getenv("VOICE_VAD", "silero").strip().lower()
MIN_UTTERANCE_MS = int(os.getenv("VOICE_MIN_UTTERANCE_MS", "400"))
MAX_UTTERANCE_MS = int(os.getenv("VOICE_MAX_UTTERANCE_MS", "60000"))
MIN_SILENCE_MS = int(os.getenv("VOICE_MIN_SILENCE_MS", "550"))


def voice_vad_mode() -> str:
    return VOICE_VAD if VOICE_VAD in ("silero", "rms") else "silero"


def load_silero_vad() -> VAD:
    from livekit.plugins import silero

    min_speech_s = max(MIN_UTTERANCE_MS / 1000.0, 0.05)
    min_silence_s = max(MIN_SILENCE_MS / 1000.0, 0.25)
    max_buffered_s = max(MAX_UTTERANCE_MS / 1000.0, 1.0)
    vad = silero.VAD.load(
        min_speech_duration=min_speech_s,
        min_silence_duration=min_silence_s,
        max_buffered_speech=max_buffered_s,
    )
    _log.info(
        "Silero VAD loaded (min_speech=%.2fs min_silence=%.2fs max_buffer=%.1fs)",
        min_speech_s,
        min_silence_s,
        max_buffered_s,
    )
    return vad


def frame_to_mono_rtc_frame(frame: rtc.AudioFrame) -> rtc.AudioFrame:
    floats, _ = frame_to_mono_floats(frame)
    if not floats:
        return frame
    pcm = float32_to_pcm16(floats)
    return rtc.AudioFrame(
        data=pcm,
        sample_rate=frame.sample_rate,
        num_channels=1,
        samples_per_channel=len(floats),
    )


def vad_frames_to_wav(frames: list[rtc.AudioFrame]) -> tuple[bytes, float]:
    if not frames:
        return b"", 0.0
    sample_rate = frames[0].sample_rate
    pcm = b"".join(bytes(f.data) for f in frames)
    if not pcm:
        return b"", 0.0
    duration_s = (len(pcm) / 2.0) / float(sample_rate) if sample_rate else 0.0
    wav = pcm16_mono_to_wav(pcm, sample_rate=sample_rate)
    return wav, duration_s


UtteranceCallback = Callable[[bytes, float, str], Awaitable[None]]


class PushToTalkBuffer:
    """Accumulate mic audio while unmuted; emit wav only on explicit flush (mute)."""

    def __init__(
        self,
        on_utterance: UtteranceCallback,
        *,
        min_utterance_ms: int = MIN_UTTERANCE_MS,
        max_utterance_ms: int = MAX_UTTERANCE_MS,
    ) -> None:
        self._on_utterance = on_utterance
        self._min_utterance_s = min_utterance_ms / 1000.0
        self._max_utterance_s = max_utterance_ms / 1000.0
        self._frames: list[rtc.AudioFrame] = []
        self._duration_s = 0.0
        self._closed = False

    def clear(self) -> None:
        self._frames = []
        self._duration_s = 0.0

    def push_frame(self, frame: rtc.AudioFrame) -> None:
        if self._closed:
            return
        mono = frame_to_mono_rtc_frame(frame)
        self._frames.append(mono)
        rate = mono.sample_rate or 48000
        self._duration_s += len(mono.data) / 2.0 / float(rate)
        while self._duration_s > self._max_utterance_s and self._frames:
            dropped = self._frames.pop(0)
            dr = dropped.sample_rate or rate
            self._duration_s -= len(dropped.data) / 2.0 / float(dr)

    async def flush_mute(self) -> None:
        if self._closed or not self._frames:
            self.clear()
            return
        frames = list(self._frames)
        self.clear()
        wav, duration_s = vad_frames_to_wav(frames)
        if duration_s < self._min_utterance_s or not wav:
            return
        await self._on_utterance(wav, duration_s, "mute")

    async def aclose(self) -> None:
        self._closed = True
        self.clear()


class SileroUtteranceCollector:
    """Legacy Silero VAD collector (tests); production uses PushToTalkBuffer."""

    def __init__(
        self,
        vad: VAD,
        on_utterance: UtteranceCallback,
        *,
        min_utterance_ms: int = MIN_UTTERANCE_MS,
    ) -> None:
        self._vad = vad
        self._on_utterance = on_utterance
        self._min_utterance_s = min_utterance_ms / 1000.0
        self._vad_stream = vad.stream()
        self._in_speech = False
        self._speech_frames: list[rtc.AudioFrame] = []
        self._event_task: asyncio.Task[None] | None = None
        self._closed = False

    async def start(self) -> None:
        self._event_task = asyncio.create_task(self._read_events(), name="silero_vad_events")

    async def _read_events(self) -> None:
        try:
            async for ev in self._vad_stream:
                if ev.type == VADEventType.START_OF_SPEECH:
                    self._in_speech = True
                    self._speech_frames = list(ev.frames)
                elif ev.type == VADEventType.END_OF_SPEECH:
                    self._in_speech = False
                    self._speech_frames = []
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            _log.exception("Silero VAD event reader failed")

    def push_frame(self, frame: rtc.AudioFrame) -> None:
        if self._closed:
            return
        mono = frame_to_mono_rtc_frame(frame)
        if self._in_speech:
            self._speech_frames.append(mono)
        self._vad_stream.push_frame(mono)

    async def flush_mute(self) -> None:
        """Commit in-progress speech when the user mutes (push-to-talk)."""
        if self._closed:
            return
        frames = list(self._speech_frames) if self._in_speech else []
        self._vad_stream.flush()
        self._in_speech = False
        self._speech_frames = []
        if frames:
            await self._maybe_emit(frames, "mute")

    async def _maybe_emit(self, frames: list[rtc.AudioFrame], reason: str) -> None:
        wav, duration_s = vad_frames_to_wav(frames)
        if duration_s < self._min_utterance_s or not wav:
            return
        await self._on_utterance(wav, duration_s, reason)

    async def aclose(self) -> None:
        self._closed = True
        if self._event_task is not None:
            self._event_task.cancel()
            await asyncio.gather(self._event_task, return_exceptions=True)
        await self._vad_stream.aclose()
