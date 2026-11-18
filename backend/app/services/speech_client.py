"""HTTP client for Colab speech gateway (/stt, /tts)."""

from __future__ import annotations

from typing import Any

import httpx
from app.config import settings


class ColabSpeechClient:
    def __init__(self, base_url: str | None = None, timeout: float = 120.0):
        if base_url is not None:
            raw = base_url.rstrip("/")
        elif settings.colab_inference_configured:
            raw = settings.COLAB_INFERENCE_BASE_URL.rstrip("/")
        else:
            raw = ""
        self.base_url = raw
        self.timeout = timeout

    def enabled(self) -> bool:
        return bool(self.base_url)

    async def transcribe(self, audio: bytes, filename: str = "audio.wav") -> dict[str, Any]:
        if not self.enabled():
            raise RuntimeError("COLAB_INFERENCE_BASE_URL is not set")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            files = {"audio": (filename, audio, "audio/wav")}
            r = await client.post(f"{self.base_url}/stt/transcribe", files=files)
            r.raise_for_status()
            return r.json()

    async def synthesize(self, text: str, voice: str = "af") -> bytes:
        if not self.enabled():
            raise RuntimeError("COLAB_INFERENCE_BASE_URL is not set")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/tts/synthesize",
                json={"text": text, "voice": voice},
            )
            r.raise_for_status()
            return r.content
