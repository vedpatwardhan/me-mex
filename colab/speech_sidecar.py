#!/usr/bin/env python3
"""
CPU speech HTTP API for Colab (no GPU).

  POST /stt/transcribe   multipart field \"audio\" (wav/webm)
  POST /tts/synthesize   JSON { \"text\": \"...\", \"voice\": \"af\" } → audio/wav

Run: uvicorn speech_sidecar:app --host 127.0.0.1 --port 7861
"""

from __future__ import annotations

import io
import os
import tempfile
from typing import Literal

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

STT_MODEL = os.getenv("WHISPER_MODEL", "tiny")
STT_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
STT_COMPUTE = os.getenv("WHISPER_COMPUTE", "int8")
KOKORO_VOICE = os.getenv("KOKORO_DEFAULT_VOICE", "af_heart")

app = FastAPI(title="Me-Mex speech sidecar", version="0.1.0")

_whisper_model = None
_kokoro_pipeline = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel(
            STT_MODEL, device=STT_DEVICE, compute_type=STT_COMPUTE
        )
    return _whisper_model


def _get_kokoro():
    global _kokoro_pipeline
    if _kokoro_pipeline is None:
        from kokoro import KPipeline

        _kokoro_pipeline = KPipeline(lang_code="a")
    return _kokoro_pipeline


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "stt": STT_MODEL, "tts": "kokoro"}


@app.post("/stt/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> JSONResponse:
    data = await audio.read()
    suffix = ".wav"
    if audio.filename and "." in audio.filename:
        suffix = "." + audio.filename.rsplit(".", 1)[-1].lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    language = None
    try:
        model = _get_whisper()
        segments, info = model.transcribe(path, beam_size=1)
        language = getattr(info, "language", None)
        text = " ".join(s.text.strip() for s in segments).strip()
    finally:
        os.unlink(path)
    return JSONResponse({"text": text, "language": language})


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    voice: str = KOKORO_VOICE
    speed: float = 1.0
    format: Literal["wav"] = "wav"


@app.post("/tts/synthesize")
def synthesize(body: TTSRequest) -> Response:
    import numpy as np
    import soundfile as sf

    pipeline = _get_kokoro()
    generator = pipeline(body.text, voice=body.voice, speed=body.speed)
    chunks = []
    for _, _, audio in generator:
        chunks.append(np.asarray(audio, dtype=np.float32))
    if not chunks:
        return Response(status_code=422, content=b"no audio generated")
    wav = np.concatenate(chunks)
    buf = io.BytesIO()
    sf.write(buf, wav, 24000, format="WAV")
    return Response(content=buf.getvalue(), media_type="audio/wav")
