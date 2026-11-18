# Colab inference — operator runbook

Bring up **remote inference** for Me-Mex v2 on a Colab GPU VM: **Ministral chat (vLLM)**, **BGE cross-encoder decision routing**, and (optional) **speech** — all behind **one HTTPS URL**.

**See also:** [TOPOLOGY.md](./TOPOLOGY.md) · [me_mex_inference_stack.ipynb](./me_mex_inference_stack.ipynb) · [docs/05-models-and-runtime.md](../docs/05-models-and-runtime.md)

---

## 1. What runs where

| Capability | Colab process | Path (via tunnel) | Local env |
|------------|---------------|-------------------|-----------|
| **Chat / tools** | vLLM `:8000` (GPU) | `POST …/v1/chat/completions` | `COLAB_VLLM_URL`, `CHAT_LLM_MODE=live` |
| **Decision routing** | Gateway CPU (cross-encoder) | `POST …/v1/decision/score` | `DECISION_SCORER_MODE=live` |
| **STT / TTS** (Phase 2) | `speech_sidecar` `:7861` | `POST …/stt/*`, `…/tts/*` | `COLAB_SPEECH_BASE_URL` (no `/v1`) |

**Public entrypoint:** `inference_gateway` on **`:7860`**. Point cloudflared here — not at vLLM `:8000`.

**Reranker:** `BGE_RERANKER_MODEL` (default `BAAI/bge-reranker-base`) loads in the gateway process on CPU. First `/health` or `/v1/decision/score` may download weights from Hugging Face.

---

## 2. Prerequisites

**Colab:** GPU runtime (T4/L4); Hugging Face login for Ministral (notebook §2); `colab/` files on the VM (`inference_gateway.py`, `reranker_service.py`, `scoring_text.py`, `speech_sidecar.py`, `requirements-colab.txt`).

**Mac:** `uv sync`; `backend/.env` from [`.env.example`](../backend/.env.example). Mongo only if you run full pytest/e2e — not required for gateway smoke alone.

---

## 3. Colab bring-up

Follow the notebook in order: **§0 → §1 → §2 → §5 → §6 → §7 → §8 → §9**.

| Step | Action |
|------|--------|
| §2 | Install deps; HF login |
| §5 | vLLM on `127.0.0.1:8000` (Ministral Instruct + tool parser) |
| §6 | Speech sidecar on `7861` (Phase 1 optional; Phase 2 voice) |
| §7 | Gateway on `0.0.0.0:7860` with `BGE_RERANKER_MODEL` |
| §8 | `cloudflared tunnel --url http://127.0.0.1:7860` |

### vLLM (reference)

```bash
vllm serve mistralai/Ministral-3-8B-Instruct-2512 \
  --host 127.0.0.1 --port 8000 \
  --tokenizer-mode mistral \
  --config-format mistral \
  --load-format mistral \
  --enable-auto-tool-choice \
  --tool-call-parser mistral \
  --max-model-len 8192 \
  --max-num-seqs 4 \
  --gpu-memory-utilization 0.90 \
  --enable-prefix-caching
```

### Gateway (reference)

```bash
export VLLM_BASE=http://127.0.0.1:8000/v1
export SPEECH_BASE=http://127.0.0.1:7861
export BGE_RERANKER_MODEL=BAAI/bge-reranker-base
export LLM_MODEL_NAME=mistralai/Ministral-3-8B-Instruct-2512
uvicorn inference_gateway:app --host 0.0.0.0 --port 7860
```

Paste the tunnel hostname into local config (§4).

---

## 4. Local `.env`

```env
COLAB_VLLM_URL=https://YOUR_SUBDOMAIN.trycloudflare.com/v1
CHAT_LLM_MODE=live
DECISION_SCORER_MODE=live
LLM_MODEL_NAME=mistralai/Ministral-3-8B-Instruct-2512
LLM_TIMEOUT=180

# Phase 2 voice (same host, no /v1):
# COLAB_SPEECH_BASE_URL=https://YOUR_SUBDOMAIN.trycloudflare.com
```

`COLAB_VLLM_URL` **must end with `/v1`**. Backend uses:

- `{COLAB_VLLM_URL}/chat/completions`
- `{COLAB_VLLM_URL}/decision/score`

`LLM_MODEL_NAME` must match the weights vLLM is serving.

---

## 5. Verification

### Health

```bash
curl -sS "https://YOUR_SUBDOMAIN.trycloudflare.com/health"
```

Expect `status`, `vllm`, `reranker_model`.

### Decision `/v1/decision/score`

```bash
curl -sS -X POST "https://YOUR_SUBDOMAIN.trycloudflare.com/v1/decision/score" \
  -H "Content-Type: application/json" \
  -d '{
    "query_node": {"id": "q", "title": "query", "node_kind": "ROOT"},
    "frontier": [
      {"id": "a", "title": "A", "node_kind": "CONCEPT_M"},
      {"id": "b", "title": "B", "node_kind": "CONCEPT_M"}
    ]
  }'
```

Expect `relevance_probs` with keys `a` and `b`, probabilities summing ≈ 1.

### Backend (Mac)

```bash
cd me-mex/backend
DECISION_SCORER_MODE=live uv run pytest tests/integration/decision -m vllm -v
```

Marker `vllm` = live **inference gateway** (chat proxy + reranker). Phase 1 ops gate per [docs/11-testing.md](../docs/11-testing.md).

### Chat (optional)

`CHAT_LLM_MODE=live` and `POST /api/agent/turn`, or call `llm_gateway` directly.

---

## 6. Optional — reranker quality eval (local)

**Not part of Colab bring-up.** After the tunnel works, you can score held-out bootstrap rows on your Mac:

```bash
cd me-mex/backend
# Generate val.jsonl if needed — see backend/data/decision_training/README.md
DECISION_SCORER_MODE=live uv run python scripts/eval_decision_model.py \
  --val data/decision_training/robotics/val.jsonl --live \
  --out data/decision_training/eval_report.json
```

Optional thresholds: `data/decision_training/eval_gate.json`.

---

## 7. Phase 1 ops checklist

- [ ] vLLM healthy on Colab `8000`
- [ ] Gateway `/health` shows reranker model
- [ ] Tunnel URL in `COLAB_VLLM_URL` (with `/v1`)
- [ ] `pytest -m vllm` (decision integration) green
- [ ] (Optional) `eval_decision_model.py --live` + saved report
- [ ] (Optional) full `uv run pytest` with Mongo

---

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| 404 on `/v1/decision/score` | Tunnel must target gateway **`:7860`**, not vLLM `:8000` |
| Decision fails, chat works | `COLAB_VLLM_URL` must include `/v1` |
| vLLM OOM | Lower `--max-model-len`, reduce `--gpu-memory-utilization`, or FP8 weights |
| Slow first decision | BGE download; warm with `/health` |
| Uniform probs + `warning` in JSON | Check gateway logs, HF access, Colab CPU RAM |
| Tunnel broke | New Colab session → new URL → update `.env` |

---

## 9. Files in `colab/`

| File | Purpose |
|------|---------|
| [me_mex_inference_stack.ipynb](./me_mex_inference_stack.ipynb) | Operator notebook |
| [inference_gateway.py](./inference_gateway.py) | vLLM proxy, `/v1/decision/score`, speech proxy |
| [reranker_service.py](./reranker_service.py) | Cross-encoder scoring |
| [scoring_text.py](./scoring_text.py) | Pair text formatting |
| [speech_sidecar.py](./speech_sidecar.py) | Whisper + Kokoro |
| [requirements-colab.txt](./requirements-colab.txt) | Notebook pip pins |
| [TOPOLOGY.md](./TOPOLOGY.md) | Architecture diagram |

---

## 10. Phase 2 voice

Same tunnel host; set `COLAB_SPEECH_BASE_URL` without `/v1`. LiveKit stays local. Notebook §10.
