"""Sentence-chunk TTS pipeline for streaming conversation tokens."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")

_ENV_TRUE = frozenset({"1", "true", "yes"})


def pipelined_tts_enabled() -> bool:
    return os.getenv("VOICE_TTS_PIPELINED", "true").lower() in _ENV_TRUE


def _max_chars() -> int:
    try:
        return max(40, int(os.getenv("VOICE_TTS_SEGMENT_MAX_CHARS", "180")))
    except ValueError:
        return 180


def _min_chars() -> int:
    try:
        return max(1, int(os.getenv("VOICE_TTS_SEGMENT_MIN_CHARS", "12")))
    except ValueError:
        return 12


def extract_segments(buffer: str, *, flush: bool = False) -> tuple[list[str], str]:
    """Split buffer into speakable segments; return (segments, remainder)."""
    max_c = _max_chars()
    min_c = _min_chars()
    segments: list[str] = []
    rest = buffer

    while rest:
        m = _SENTENCE_END.search(rest)
        if m and m.end() >= min_c:
            chunk = rest[: m.end()].strip()
            rest = rest[m.end() :].lstrip()
            if len(chunk) >= min_c:
                segments.append(chunk)
            continue
        if len(rest) > max_c:
            cut = rest.rfind(" ", 0, max_c)
            if cut < min_c:
                cut = max_c
            chunk = rest[:cut].strip()
            rest = rest[cut:].lstrip()
            if len(chunk) >= min_c:
                segments.append(chunk)
            continue
        break

    if flush and rest.strip():
        tail = rest.strip()
        if len(tail) >= min_c or not segments:
            segments.append(tail)
        rest = ""
    return segments, rest


class TtsPipeline:
    """Queue text segments → synthesize with one-ahead prefetch → play."""

    def __init__(
        self,
        *,
        synthesize: Any,
        play_wav: Any,
        cancel_event: asyncio.Event,
        session: Any,
        room: Any,
    ) -> None:
        self._synthesize = synthesize
        self._play_wav = play_wav
        self._cancel = cancel_event
        self._session = session
        self._room = room
        self._buffer = ""
        self._queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=16)
        self._worker_task: asyncio.Task | None = None

    def feed_token(self, text: str) -> None:
        if not text:
            return
        self._buffer += text
        segs, self._buffer = extract_segments(self._buffer, flush=False)
        for seg in segs:
            self._enqueue(seg)

    def flush(self) -> None:
        segs, self._buffer = extract_segments(self._buffer, flush=True)
        for seg in segs:
            self._enqueue(seg)

    def _enqueue(self, segment: str) -> None:
        if self._cancel.is_set():
            return
        try:
            self._queue.put_nowait(segment)
        except asyncio.QueueFull:
            pass

    async def start(self) -> None:
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._run())

    async def finish(self) -> None:
        self.flush()
        await self._queue.put(None)
        if self._worker_task:
            await self._worker_task
            self._worker_task = None

    async def cancel(self) -> None:
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        self._worker_task = None

    async def _run(self) -> None:
        prefetch: asyncio.Task[bytes] | None = None
        while not self._cancel.is_set():
            segment = await self._queue.get()
            if segment is None:
                break
            if prefetch is None:
                prefetch = asyncio.create_task(self._synthesize(segment))
                continue
            wav = await prefetch
            prefetch = asyncio.create_task(self._synthesize(segment))
            if self._cancel.is_set():
                prefetch.cancel()
                return
            await self._play_wav(self._room, self._session, wav)
        if prefetch and not self._cancel.is_set():
            wav = await prefetch
            await self._play_wav(self._room, self._session, wav)
