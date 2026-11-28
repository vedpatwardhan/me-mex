#!/usr/bin/env python3
"""
Unified HTTP entry for cloudflared → local Me-Mex backend.

Exposes:
  - /v1/*                    → vLLM OpenAI API (chat, models, …)
  - POST /v1/decision/score  → cross-encoder reranker (DecisionScorer contract)

Optionally proxies /stt/* and /tts/* to speech_sidecar when SPEECH_URL is set.

Run on Colab: uvicorn inference_gateway:app --host 0.0.0.0 --port 7860
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

_COLAB = Path(__file__).resolve().parent
if str(_COLAB) not in sys.path:
    sys.path.insert(0, str(_COLAB))
from reranker_service import reranker_model_name, score_batch
from voice_speak import stream_voice_speak

VLLM_BASE = os.getenv("VLLM_BASE", "http://127.0.0.1:8000/v1").rstrip("/")
SPEECH_BASE = os.getenv("SPEECH_BASE", "http://127.0.0.1:7861").rstrip("/")

app = FastAPI(title="Me-Mex inference gateway", version="0.2.0")

_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))


@app.on_event("shutdown")
async def _shutdown() -> None:
    await _client.aclose()


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "vllm": VLLM_BASE,
        "speech": SPEECH_BASE,
        "reranker_model": reranker_model_name(),
    }


async def _proxy_vllm(request: Request, path: str) -> Response:
    """Forward request to vLLM /v1/{path}."""
    url = f"{VLLM_BASE}/{path}"
    body = await request.body()
    headers = {
        k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")
    }
    upstream = await _client.request(
        request.method,
        url,
        headers=headers,
        content=body,
        params=request.query_params,
    )
    if "text/event-stream" in upstream.headers.get("content-type", ""):
        return StreamingResponse(
            upstream.aiter_bytes(),
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type"),
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def vllm_proxy(path: str, request: Request) -> Response:
    if path == "decision/score" and request.method == "POST":
        return await decision_score(request)
    if path == "voice/speak" and request.method == "POST":
        body = await request.json()
        return StreamingResponse(
            stream_voice_speak(body, http_client=_client),
            media_type="text/event-stream",
        )
    return await _proxy_vllm(request, path)


async def decision_score(request: Request) -> JSONResponse:
    """
    Body: { query_node, frontier[] } → { relevance_probs }.

    Cross-encoder softmax over frontier (no vLLM / no LoRA).
    """
    body = await request.json()
    query = body.get("query_node") or {}
    frontier = body.get("frontier") or []
    if not frontier:
        return JSONResponse({"relevance_probs": {}})

    frontier_ids = {str(n["id"]) for n in frontier}
    try:
        probs = score_batch(query, frontier)
    except Exception as exc:  # noqa: BLE001
        n = len(frontier)
        uniform = 1.0 / n
        probs = {fid: uniform for fid in frontier_ids}
        return JSONResponse({"relevance_probs": probs, "warning": f"fallback uniform: {exc}"})

    return JSONResponse({"relevance_probs": probs})


async def _proxy_speech(request: Request, path: str) -> Response:
    url = f"{SPEECH_BASE}/{path}"
    body = await request.body()
    upstream = await _client.request(
        request.method,
        url,
        content=body,
        headers={
            k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")
        },
    )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


@app.api_route("/stt/{path:path}", methods=["POST", "GET"])
async def stt_proxy(path: str, request: Request) -> Response:
    return await _proxy_speech(request, f"stt/{path}")


@app.api_route("/tts/{path:path}", methods=["POST", "GET"])
async def tts_proxy(path: str, request: Request) -> Response:
    return await _proxy_speech(request, f"tts/{path}")
