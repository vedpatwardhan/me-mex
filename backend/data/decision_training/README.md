# Decision training data (Phase 1 bootstrap)

Join **`deeper_read_notes.md`** + **`overall_insights.md`** only (`select_papers` is not used here).

## Alignment report (run first)

```bash
cd me-mex/backend
uv run python -m app.bootstrap.notes_to_jsonl --report-only --docs-dir ../../docs
```

Outputs:

- `robotics/alignment_report.json`
- `robotics/alignment_report.md` (unmatched cites + fuzzy candidates for manual doc fixes)

Stdout summary: `matched=… unmatched=… ambiguous=… roots=…`

Re-run until unmatched is acceptable, then emit JSONL. Use `--strict` to block emit while unmatched &gt; 0.

## Generate JSONL + split

```bash
uv run python -m app.bootstrap.notes_to_jsonl --docs-dir ../../docs
uv run python -m app.bootstrap.split_train_eval data/decision_training/robotics/bootstrap.jsonl --out-dir data/decision_training/robotics
```

Last run (reference): **750** bootstrap rows → **592** train / **158** val; alignment **501** matched cites, **53** unmatched, **564** ROOTs indexed.

## Eval (mock vs live)

```bash
uv run python scripts/eval_decision_model.py --val data/decision_training/robotics/val.jsonl
DECISION_SCORER_MODE=live uv run python scripts/eval_decision_model.py --val data/decision_training/robotics/val.jsonl --live
```

Set `accuracy_top1_min` in [`eval_gate.json`](eval_gate.json) after baselines.

## Colab LoRA

Upload `train.jsonl` / `val.jsonl`. Train: [`colab/train_decision_lora.py`](../../colab/train_decision_lora.py). Deploy: [`colab/RUNBOOK.md`](../../colab/RUNBOOK.md).

Live gate:

```bash
DECISION_SCORER_MODE=live uv run pytest tests/integration/decision -m vllm
```