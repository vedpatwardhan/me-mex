# Decision training data (Phase 1 bootstrap)

Generate held-out JSONL from robotics tier notes (train **LoRA on Colab** — not in CI):

```bash
cd me-mex/backend
uv run python -m app.bootstrap.notes_to_jsonl
uv run python -m app.bootstrap.split_train_eval data/decision_training/robotics/bootstrap.jsonl --out-dir data/decision_training/robotics
uv run python scripts/eval_decision_model.py --val data/decision_training/robotics/val.jsonl
```

Mock scorer CI:

```bash
uv run python scripts/eval_decision_model.py --val tests/fixtures/decision/tiny_val.jsonl
```

Live LoRA gate:

```bash
DECISION_SCORER_MODE=live uv run pytest tests/integration/decision -m vllm
```

See [colab/RUNBOOK.md](../../colab/RUNBOOK.md) for adapter training.