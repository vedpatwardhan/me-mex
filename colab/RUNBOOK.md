# Colab LoRA training (user-run)

1. Upload `backend/data/decision_training/robotics/train.jsonl` and `val.jsonl`.
2. Fine-tune LoRA on `mistralai/Ministral-3-8B-Instruct-2512` (PEFT).
3. Serve with vLLM: `--enable-lora` and your adapter path.
4. Set local `.env`: `COLAB_VLLM_URL`, `LORA_ADAPTER_ID`.
5. Run `uv run pytest -m vllm` manually when Colab is up.

This repository does **not** execute training jobs during implementation.