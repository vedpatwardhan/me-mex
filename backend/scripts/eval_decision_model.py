#!/usr/bin/env python3
"""Evaluate DecisionScorer against val JSONL — dry-run without vLLM by default."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.v2.services.decision_scorer import MockDecisionScorer, ScorerNode


def ranking_hit(probs: dict[str, float], labels: dict[str, float]) -> float:
    if not labels:
        return 0.0
    gold = max(labels.items(), key=lambda x: x[1])[0]
    pred = max(probs.items(), key=lambda x: x[1])[0]
    return 1.0 if pred == gold else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    default_val = BACKEND_DIR / "tests" / "fixtures" / "decision" / "tiny_val.jsonl"
    parser.add_argument("--val", type=Path, default=default_val)
    parser.add_argument(
        "--out",
        type=Path,
        default=BACKEND_DIR / "data" / "decision_training" / "eval_report.json",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    scorer = MockDecisionScorer()
    hits = []
    if not args.val.exists():
        if args.dry_run:
            report = {
                "accuracy_top1": 1.0,
                "n": 0,
                "dry_run": True,
                "note": "no val file",
            }
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
            return
        raise SystemExit(f"val file missing: {args.val}")
    for line in args.val.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        q = row["query_node"]
        frontier = [
            ScorerNode(id=f["id"], title=f["title"], node_kind=f["node_kind"])
            for f in row["frontier"]
        ]
        query = ScorerNode(id=q["id"], title=q["title"], node_kind=q["node_kind"])
        probs = scorer.score(query, frontier)
        hits.append(ranking_hit(probs, row.get("label_relevance", {})))
    report = {
        "accuracy_top1": sum(hits) / max(len(hits), 1),
        "n": len(hits),
        "dry_run": args.dry_run,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
