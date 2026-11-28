# Me-Mex Colab inference topology (L4)

This document describes how **four remote capabilities** — chat LLM, **cross-encoder reranker**, STT, TTS — run on one Colab VM and how your **local** stack connects. Canon: [05-models-and-runtime.md](../docs/05-models-and-runtime.md) §5–6, [10 M1](../docs/10-open-questions.md#6-resolved-decisions-locked).

---

## Design principle

| Runs on Colab | Runs locally (your Mac) |
|---------------|-------------------------|
| Model weights only (vLLM GPU, gateway + speech CPU) | FastAPI, MongoDB, LangGraph, checkpoints, React UI, **LiveKit** |
| Stateless HTTP | Durable `thread_id`, graph data, voice room |

**LiveKit never terminates on Colab.** Audio flows: browser ↔ **local** LiveKit server ↔ local agent worker. The worker calls Colab over **HTTPS** for STT/TTS/LLM — same pattern as chat today, not a second WebRTC path through the tunnel.

---

## Process layout (one Colab VM)

```text
                    cloudflared quick tunnel (HTTPS)
                              │
                              ▼
              ┌───────────────────────────────────┐
              │  inference_gateway  :7860         │
              │  • GET/POST /v1/*  → proxy vLLM   │
              │  • POST /v1/voice/speak (SSE)      │
              │  • POST /v1/decision/score (CPU)    │
              │  • POST /stt/* /tts/*  → speech   │
              └───────────┬─────────────┬─────────┘
                          │             │
              ┌───────────▼───┐   ┌─────▼─────────────┐
              │ vLLM  :8000   │   │ speech_sidecar    │
              │ GPU (L4)      │   │ :7861 CPU         │
              │ Ministral 8B  │   │ base.en + edge-tts│
              └───────────────┘   └───────────────────┘
              (BGE reranker loads inside gateway process, CPU)
```

**Why one public port?** Your backend sets `COLAB_INFERENCE_BASE_URL` to the tunnel host and calls `{base}/v1/chat/completions` and `{base}/v1/decision/score` ([`HttpDecisionScorer`](../backend/app/services/decision_scorer.py)). Speech uses the same `{base}/stt/*` and `/tts/*`. A single **gateway** on `:7860` keeps **one** Cloudflare URL for everything.

**VRAM:** Only vLLM uses the L4 GPU. Reranker, Whisper, and edge-tts stay on **CPU**.

---

## Local connection map

| Local component | Remote call | Env (backend / worker) |
|-----------------|-------------|----------------------|
| LangChain chat (`llm_gateway`) | `POST …/v1/chat/completions` (SSE stream) | `COLAB_INFERENCE_BASE_URL`, `CHAT_LLM_MODE=live` |
| `HttpDecisionScorer` | `POST …/v1/decision/score` | `DECISION_SCORER_MODE=live` |
| LiveKit worker STT (Phase 2) | `POST …/stt/transcribe` | `COLAB_INFERENCE_BASE_URL` |
| LiveKit worker TTS (Phase 2) | `POST …/tts/synthesize` | same |

---

## Model checkpoint alignment

| Role | Recommended HF id | Notes |
|------|-------------------|--------|
| vLLM chat | `mistralai/Ministral-3-8B-Instruct-2512` | Tool calling |
| Optional reasoning chat | `mistralai/Ministral-3-8B-Reasoning-2512` | Match `LLM_MODEL_NAME` to served weights |
| Decision reranker | `BAAI/bge-reranker-base` (env `BGE_RERANKER_MODEL`) | Gateway CPU; first request downloads |

---

## Local `.env` (inference)

```bash
COLAB_INFERENCE_BASE_URL=https://YOUR_SUBDOMAIN.trycloudflare.com
CHAT_LLM_MODE=live
DECISION_SCORER_MODE=live
LLM_MODEL_NAME=mistralai/Ministral-3-8B-Instruct-2512
```

Verify:

```bash
cd me-mex/backend
DECISION_SCORER_MODE=live uv run pytest tests/integration/decision -m vllm
```

---

## Operational notes

1. **Session lifetime:** Colab disconnects → tunnel URL changes → update `.env`.
2. **FP8 on L4:** If OOM, use FP8 weights and lower `--max-model-len` / `--gpu-memory-utilization`.
3. **Phase 1 exit:** vLLM + gateway (reranker loaded) + tunnel; `pytest -m vllm`; optional bootstrap `--live` eval.

---

## Files in `colab/`

| File | Purpose |
|------|---------|
| [me_mex_inference_stack.ipynb](./me_mex_inference_stack.ipynb) | Operator notebook |
| [inference_gateway.py](./inference_gateway.py) | Public HTTP surface |
| [reranker_service.py](./reranker_service.py) | Cross-encoder batch scoring |
| [speech_sidecar.py](./speech_sidecar.py) | CPU Whisper + edge-tts |
| [RUNBOOK.md](./RUNBOOK.md) | **Primary operator guide** (bring-up, verify, optional eval) |
