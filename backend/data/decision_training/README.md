# Decision training data

- Generate bootstrap JSONL:  
  `uv run python -m app.bootstrap.notes_to_jsonl`
- Split:  
  `uv run python -m app.bootstrap.split_train_eval data/decision_training/robotics/bootstrap.jsonl --out-dir data/decision_training/robotics`
- Eval (dry-run mock scorer):  
  `uv run python backend/scripts/eval_decision_model.py --val backend/data/decision_training/robotics/val.jsonl`

**LoRA training** runs on Colab only — see [colab/RUNBOOK.md](../../colab/RUNBOOK.md). No training runs in CI.