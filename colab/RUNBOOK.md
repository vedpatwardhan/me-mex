# Colab inference stack (user-run)

Topology: **[TOPOLOGY.md](./TOPOLOGY.md)**, operator notebook **[me_mex_inference_stack.ipynb](./me_mex_inference_stack.ipynb)**.

## Bootstrap JSONL (local, eval / future fine-tune)

```bash
cd me-mex/backend
uv run python -m app.bootstrap.notes_to_jsonl
uv run python -m app.bootstrap.split_train_eval data/decision_training/robotics/bootstrap.jsonl --out-dir data/decision_training/robotics
```

Decision routing uses an **off-the-shelf cross-encoder** on the gateway (`BGE_RERANKER_MODEL`, default `BAAI/bge-reranker-base`). No LoRA train step required for Phase 1.

## Colab serve

1. Follow notebook: deps (§2) → vLLM **without** `--enable-lora` (§5) → speech sidecar (§6) → **gateway** (§7) → cloudflared (§8).
2. First `decision/score` call downloads the reranker weights (CPU).

## Local verify

```bash
# backend/.env
COLAB_VLLM_URL=https://YOUR_SUBDOMAIN.trycloudflare.com/v1
CHAT_LLM_MODE=live
DECISION_SCORER_MODE=live
LLM_MODEL_NAME=mistralai/Ministral-3-8B-Instruct-2512
```

```bash
cd me-mex/backend
DECISION_SCORER_MODE=live uv run pytest tests/integration/decision -m vllm
uv run python scripts/eval_decision_model.py --val data/decision_training/robotics/val.jsonl --live
```

## Legacy

[`train_decision_lora.py`](./train_decision_lora.py) — **deprecated** JSON LoRA path; superseded by gateway reranker ([05 §3](../docs/05-models-and-runtime.md)).