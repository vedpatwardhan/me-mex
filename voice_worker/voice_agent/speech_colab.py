"""Colab gateway STT/TTS (same paths as backend ColabSpeechClient)."""

from __future__ import annotations

import os
from typing import Any

import httpx


def _base_url() -> str:
    raw = os.getenv("COLAB_INFERENCE_BASE_URL", "").strip().rstrip("/")
    if not raw:
        return ""
    if raw.endswith("/v1"):
        raw = raw[:-3].rstrip("/")
    return raw


def speech_enabled() -> bool:
    return bool(_base_url())


async def transcribe_wav(audio: bytes, *, filename: str = "utterance.wav") -> dict[str, Any]:
    base = _base_url()
    if not base:
        raise RuntimeError("COLAB_INFERENCE_BASE_URL is not set")
    async with httpx.AsyncClient(timeout=120.0) as client:
        files = {"audio": (filename, audio, "audio/wav")}
        r = await client.post(f"{base}/stt/transcribe", files=files)
        r.raise_for_status()
        return r.json()


async def synthesize_wav(text: str, *, voice: str = "af") -> bytes:
    base = _base_url()
    if not base:
        raise RuntimeError("COLAB_INFERENCE_BASE_URL is not set")
    text = (text or "").strip()
    if not text:
        return b""
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            f"{base}/tts/synthesize",
            json={"text": text, "voice": voice},
        )
        r.raise_for_status()
        return r.content
