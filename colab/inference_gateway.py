#!/usr/bin/env python3
"""
Unified HTTP entry for cloudflared → local Me-Mex backend.

Exposes:
  - /v1/*                    → vLLM OpenAI API (chat, models, …)
  - POST /v1/decision/score  → LoRA relevance batch (DecisionScorer contract)

Optionally proxies /stt/* and /tts/* to speech_sidecar when SPEECH_URL is set.

Run on Colab: uvicorn inference_gateway:app --host 0.0.0.0 --port 7860
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

VLLM_BASE = os.getenv("VLLM_BASE", "http://127.0.0.1:8000/v1").rstrip("/")
SPEECH_BASE = os.getenv("SPEECH_BASE", "http://127.0.0.1:7861").rstrip("/")
DEFAULT_CHAT_MODEL = os.getenv(
    "LLM_MODEL_NAME", "mistralai/Ministral-3-8B-Instruct-2512"
)
DEFAULT_LORA_ID = os.getenv("LORA_ADAPTER_ID", "decision-lora")
DECISION_MAX_NEW_TOKENS = int(os.getenv("DECISION_MAX_NEW_TOKENS", "1024"))

app = FastAPI(title="Me-Mex inference gateway", version="0.1.0")

_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))


@app.on_event("shutdown")
async def _shutdown() -> None:
    await _client.aclose()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "vllm": VLLM_BASE, "speech": SPEECH_BASE}


async def _proxy_vllm(request: Request, path: str) -> Response:
    """Forward request to vLLM /v1/{path}."""
    url = f"{VLLM_BASE}/{path}"
    body = await request.body()
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
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
    return await _proxy_vllm(request, path)


def _build_decision_prompt(query: dict, frontier: list[dict]) -> str:
    lines = [
        "Score relevance of each frontier node to the query node.",
        'Return JSON only: {"relevance_probs": {"<frontier_id>": <0-1 float>, ...}}',
        "Probabilities must sum to 1.0 over all frontier ids.",
        "",
        f"QUERY: id={query.get('id')} kind={query.get('node_kind')} title={query.get('title')}",
    ]
    if query.get("gist"):
        lines.append(f"  gist: {query.get('gist')[:400]}")
    lines.append("FRONTIER:")
    for n in frontier:
        lines.append(
            f"  - id={n.get('id')} kind={n.get('node_kind')} title={n.get('title')}"
        )
    return "\n".join(lines)


def _parse_relevance_probs(text: str, frontier_ids: set[str]) -> dict[str, float]:
    text = text.strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    data = json.loads(text)
    raw = data.get("relevance_probs", data)
    probs = {str(k): float(v) for k, v in raw.items() if k in frontier_ids}
    if len(probs) != len(frontier_ids):
        missing = frontier_ids - set(probs.keys())
        raise ValueError(f"missing frontier ids in model output: {missing}")
    total = sum(probs.values())
    if total <= 0:
        raise ValueError("non-positive probability sum")
    return {k: v / total for k, v in probs.items()}


async def decision_score(request: Request) -> JSONResponse:
    """
    Body: { query_node, frontier[], adapter_id? } → { relevance_probs }.

    Uses vLLM chat completion with LoRA when adapter_id is set.
    """
    body = await request.json()
    query = body.get("query_node") or {}
    frontier = body.get("frontier") or []
    adapter_id = body.get("adapter_id") or DEFAULT_LORA_ID
    if not frontier:
        return JSONResponse({"relevance_probs": {}})

    frontier_ids = {str(n["id"]) for n in frontier}
    prompt = _build_decision_prompt(query, frontier)
    payload: dict[str, Any] = {
        "model": DEFAULT_CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": DECISION_MAX_NEW_TOKENS,
    }
    # vLLM OpenAI-compatible LoRA: model name = adapter id when enable-lora is on
    if adapter_id:
        payload["model"] = adapter_id

    try:
        resp = await _client.post(f"{VLLM_BASE}/chat/completions", json=payload)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        probs = _parse_relevance_probs(content, frontier_ids)
    except Exception as exc:
        # Uniform fallback so smoke tests can run before LoRA is calibrated
        n = len(frontier)
        uniform = 1.0 / n
        probs = {fid: uniform for fid in frontier_ids}
        return JSONResponse(
            {"relevance_probs": probs, "warning": f"fallback uniform: {exc}"}
        )

    return JSONResponse({"relevance_probs": probs})


async def _proxy_speech(request: Request, path: str) -> Response:
    url = f"{SPEECH_BASE}/{path}"
    body = await request.body()
    upstream = await _client.request(
        request.method,
        url,
        content=body,
        headers={
            k: v
            for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length")
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
