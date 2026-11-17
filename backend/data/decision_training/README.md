# Decision training data (Phase 1 bootstrap)

Join **`deeper_read_notes.md`** + **`overall_insights.md`** only (`select_papers` is not used here).

**Training semantics:** Each **paper** (parenthetical cite → ROOT + gist) is the **query**. Each **flat subsection** (`## Section — ### Subsection` title) is a **class** on the frontier. The model scores relevance over **all** subsections; label 1.0 on subsection(s) where that paper is cited in the numbered notes. No nested graph hops in bootstrap v1.

**Excluded** top-level `##` blocks in `overall_insights.md`: **General Notes**, **Blogs**, **Podcast(s)** — not parsed for cites, classes, or alignment stats.

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

Last run (reference): **485** paper→subsection rows → **378** train / **107** val; alignment **501** matched cites, **53** unmatched, **564** ROOTs indexed.

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