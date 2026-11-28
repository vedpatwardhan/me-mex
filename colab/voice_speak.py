"""LLM token stream + parallel localhost TTS segments (SSE)."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

VLLM_BASE = os.getenv("VLLM_BASE", "http://127.0.0.1:8000/v1").rstrip("/")
SPEECH_BASE = os.getenv("SPEECH_BASE", "http://127.0.0.1:7861").rstrip("/")
DEFAULT_MODEL = os.getenv(
    "VOICE_SPEAK_MODEL", os.getenv("VLLM_MODEL", "mistralai/Ministral-8B-Instruct-2410")
)
DEFAULT_VOICE = os.getenv("EDGE_TTS_DEFAULT_VOICE", "af_heart")

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001f600-\U0001f64f"
    "\U0001f300-\U0001f5ff"
    "\U0001f680-\U0001f6ff"
    "\U0001f900-\U0001f9ff"
    "\u2600-\u26ff"
    "\u2700-\u27bf"
    "]+",
    flags=re.UNICODE,
)


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


def _strip_emojis(text: str) -> str:
    if not text:
        return text
    return _EMOJI_PATTERN.sub("", text)


def _sse_payload(obj: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode()


async def _synthesize_wav(client: httpx.AsyncClient, text: str, voice: str) -> bytes:
    r = await client.post(
        f"{SPEECH_BASE}/tts/synthesize",
        json={"text": text[:2000], "voice": voice},
        timeout=120.0,
    )
    r.raise_for_status()
    return r.content


async def stream_voice_speak(
    body: dict[str, Any],
    *,
    http_client: httpx.AsyncClient,
) -> AsyncIterator[bytes]:
    messages = body.get("messages") or []
    model = body.get("model") or DEFAULT_MODEL
    temperature = float(body.get("temperature", 0.7))
    max_tokens = body.get("max_tokens")
    top_p = float(body.get("top_p", 0.95))
    voice = str(body.get("voice") or DEFAULT_VOICE)

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "stream": True,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    segment_buffer = ""
    audio_out: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=64)
    segment_in: asyncio.Queue[str | None] = asyncio.Queue(maxsize=32)

    async def tts_worker() -> None:
        while True:
            segment = await segment_in.get()
            if segment is None:
                break
            try:
                wav = await _synthesize_wav(http_client, segment, voice)
                if wav:
                    await audio_out.put(
                        _sse_payload(
                            {
                                "type": "audio",
                                "format": "wav",
                                "data": base64.b64encode(wav).decode("ascii"),
                            }
                        )
                    )
            except (httpx.HTTPError, OSError) as exc:
                await audio_out.put(_sse_payload({"type": "error", "message": f"tts: {exc}"}))

    tts_task = asyncio.create_task(tts_worker())

    async def flush_audio() -> AsyncIterator[bytes]:
        while True:
            try:
                item = audio_out.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is None:
                break
            yield item

    async def enqueue_segment(text: str) -> None:
        cleaned = text.strip()
        if cleaned:
            await segment_in.put(cleaned)

    url = f"{VLLM_BASE}/chat/completions"
    try:
        async with http_client.stream("POST", url, json=payload, timeout=300.0) as upstream:
            if upstream.status_code != 200:
                err = await upstream.aread()
                yield _sse_payload(
                    {
                        "type": "error",
                        "message": f"llm {upstream.status_code}: {err.decode('utf-8', errors='ignore')[:500]}",
                    }
                )
                return

            async for line in upstream.aiter_lines():
                line = line.strip()
                if not line or line == "data: [DONE]":
                    continue
                if not line.startswith("data: "):
                    continue
                try:
                    chunk = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "") or ""
                if not content:
                    continue
                sanitized = _strip_emojis(content)
                if not sanitized:
                    continue
                yield _sse_payload({"type": "token", "content": sanitized})
                segment_buffer += sanitized
                segs, segment_buffer = extract_segments(segment_buffer, flush=False)
                for seg in segs:
                    await enqueue_segment(seg)
                async for audio_chunk in flush_audio():
                    yield audio_chunk

            segs, segment_buffer = extract_segments(segment_buffer, flush=True)
            for seg in segs:
                await enqueue_segment(seg)
            await segment_in.put(None)
            await tts_task
            async for audio_chunk in flush_audio():
                yield audio_chunk
    except (httpx.HTTPError, OSError) as exc:
        await segment_in.put(None)
        if not tts_task.done():
            tts_task.cancel()
        yield _sse_payload({"type": "error", "message": str(exc)})
    finally:
        if not tts_task.done():
            await segment_in.put(None)
            try:
                await tts_task
            except asyncio.CancelledError:
                pass

    yield b"data: [DONE]\n\n"
