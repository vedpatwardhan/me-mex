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
TTS_BACKEND = os.getenv("TTS_BACKEND", "auto").strip().lower()
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "en-US-AriaNeural")

_KOKORO_VOICE_TO_EDGE: dict[str, str] = {
    "af": "en-US-AriaNeural",
    "af_heart": "en-US-AriaNeural",
    "am": "en-US-GuyNeural",
    "bf": "en-GB-SoniaNeural",
}

app = FastAPI(title="Me-Mex speech sidecar", version="0.1.0")

_whisper_model = None
_kokoro_pipeline = None
_resolved_tts_backend: str | None = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel(STT_MODEL, device=STT_DEVICE, compute_type=STT_COMPUTE)
    return _whisper_model


def _get_kokoro():
    global _kokoro_pipeline
    if _kokoro_pipeline is None:
        from kokoro import KPipeline

        _kokoro_pipeline = KPipeline(lang_code="a")
    return _kokoro_pipeline


def _kokoro_available() -> bool:
    try:
        import kokoro  # noqa: F401
    except ImportError:
        return False
    return True


def _edge_available() -> bool:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return True


def _resolve_tts_backend() -> str:
    global _resolved_tts_backend
    if _resolved_tts_backend is not None:
        return _resolved_tts_backend
    if TTS_BACKEND == "kokoro":
        if not _kokoro_available():
            raise RuntimeError("TTS_BACKEND=kokoro but kokoro is not installed")
        _resolved_tts_backend = "kokoro"
    elif TTS_BACKEND == "edge":
        if not _edge_available():
            raise RuntimeError("TTS_BACKEND=edge but edge-tts is not installed")
        _resolved_tts_backend = "edge"
    else:
        if _kokoro_available():
            _resolved_tts_backend = "kokoro"
        elif _edge_available():
            _resolved_tts_backend = "edge"
        else:
            raise RuntimeError(
                "No TTS backend: install kokoro (Python <3.13) or edge-tts (Python 3.13+)"
            )
    return _resolved_tts_backend


def _edge_voice_name(voice: str) -> str:
    if voice in _KOKORO_VOICE_TO_EDGE:
        return _KOKORO_VOICE_TO_EDGE[voice]
    if "Neural" in voice or voice.startswith(("en-", "es-", "fr-")):
        return voice
    return EDGE_TTS_VOICE


def _mp3_bytes_to_wav(mp3: bytes) -> bytes:
    import subprocess

    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "wav",
            "pipe:1",
        ],
        input=mp3,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError("ffmpeg mp3→wav failed (apt install ffmpeg on Colab): " + err)
    return proc.stdout


async def _synthesize_edge(text: str, voice: str, speed: float) -> bytes:
    import edge_tts

    edge_voice = _edge_voice_name(voice)
    rate_pct = round((speed - 1.0) * 100)
    rate = f"{rate_pct:+d}%"
    communicate = edge_tts.Communicate(text, edge_voice, rate=rate)
    mp3 = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3.extend(chunk["data"])
    if not mp3:
        raise RuntimeError("edge-tts produced no audio")
    return _mp3_bytes_to_wav(bytes(mp3))


def _synthesize_kokoro(text: str, voice: str, speed: float) -> bytes:

    import numpy as np
    import soundfile as sf

    pipeline = _get_kokoro()
    generator = pipeline(text, voice=voice, speed=speed)
    chunks = []
    for _, _, audio in generator:
        chunks.append(np.asarray(audio, dtype=np.float32))
    if not chunks:
        raise RuntimeError("kokoro produced no audio")
    wav = np.concatenate(chunks)
    buf = io.BytesIO()
    sf.write(buf, wav, 24000, format="WAV")
    return buf.getvalue()


@app.get("/health")
def health() -> dict[str, str]:
    try:
        tts = _resolve_tts_backend()
    except RuntimeError as exc:
        tts = f"unavailable ({exc})"
    return {"status": "ok", "stt": STT_MODEL, "tts": tts}


@app.post("/stt/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> JSONResponse:  # noqa: B008
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
async def synthesize(body: TTSRequest) -> Response:
    try:
        backend = _resolve_tts_backend()
        if backend == "kokoro":
            wav = _synthesize_kokoro(body.text, body.voice, body.speed)
        else:
            wav = await _synthesize_edge(body.text, body.voice, body.speed)
    except RuntimeError as exc:
        return JSONResponse(status_code=503, content={"detail": str(exc)})
    return Response(content=wav, media_type="audio/wav")
