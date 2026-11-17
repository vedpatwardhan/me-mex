# Colab LoRA training (user-run)

Topology and multi-service notebook: **[TOPOLOGY.md](./TOPOLOGY.md)**, **[me_mex_inference_stack.ipynb](./me_mex_inference_stack.ipynb)**.

## Bootstrap JSONL (local)

```bash
cd me-mex/backend
uv run python -m app.bootstrap.notes_to_jsonl
uv run python -m app.bootstrap.split_train_eval data/decision_training/robotics/bootstrap.jsonl --out-dir data/decision_training/robotics
```

## Train on Colab

1. Upload `backend/data/decision_training/robotics/train.jsonl` and `val.jsonl`.
2. Fine-tune LoRA on **`mistralai/Ministral-3-8B-Instruct-2512`** (PEFT / Unsloth) → save to `/content/decision-lora`.
3. Serve with vLLM (notebook §5):

   ```text
   --enable-lora --lora-modules decision-lora=/content/decision-lora
   ```

4. Run **gateway + cloudflared** (notebook §7–§8), not raw vLLM port, so `/v1/decision/score` works.

## Local verify

```bash
# backend/.env
COLAB_VLLM_URL=https://YOUR_SUBDOMAIN.trycloudflare.com/v1
CHAT_LLM_MODE=live
DECISION_SCORER_MODE=live
LORA_ADAPTER_ID=decision-lora
```

```bash
cd me-mex/backend
DECISION_SCORER_MODE=live uv run pytest tests/integration/decision -m vllm
uv run python scripts/eval_decision_model.py --val data/decision_training/robotics/val.jsonl
```

Training jobs are **not** executed in CI.