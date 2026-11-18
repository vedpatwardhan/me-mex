#!/usr/bin/env python3
"""Evaluate DecisionScorer against val JSONL — mock by default, --live for Colab gateway reranker."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.decision_scorer import (
    HttpDecisionScorer,
    MockDecisionScorer,
    ScorerNode,
)


def ranking_hit(probs: dict[str, float], labels: dict[str, float]) -> float:
    if not labels:
        return 0.0
    gold = max(labels.items(), key=lambda x: x[1])[0]
    pred = max(probs.items(), key=lambda x: x[1])[0]
    return 1.0 if pred == gold else 0.0


def coverage_ok(probs: dict[str, float], frontier_ids: set[str]) -> bool:
    return set(probs.keys()) == frontier_ids


def main() -> None:
    parser = argparse.ArgumentParser()
    default_val = BACKEND_DIR / "tests" / "fixtures" / "decision" / "tiny_val.jsonl"
    parser.add_argument("--val", type=Path, default=default_val)
    parser.add_argument(
        "--out",
        type=Path,
        default=BACKEND_DIR / "data" / "decision_training" / "eval_report.json",
    )
    parser.add_argument(
        "--gate",
        type=Path,
        default=BACKEND_DIR / "data" / "decision_training" / "eval_gate.json",
        help='Optional threshold file: {"accuracy_top1_min": 0.0}',
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use HttpDecisionScorer (DECISION_SCORER_MODE=live)",
    )
    args = parser.parse_args()

    if args.live:
        os.environ.setdefault("DECISION_SCORER_MODE", "live")
        scorer = HttpDecisionScorer()
        mode = "live"
    else:
        scorer = MockDecisionScorer()
        mode = "mock"

    hits: list[float] = []
    coverages: list[float] = []

    if not args.val.exists():
        if args.dry_run:
            report = {
                "accuracy_top1": 1.0,
                "n": 0,
                "dry_run": True,
                "mode": mode,
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
            ScorerNode(
                id=f["id"],
                title=f["title"],
                node_kind=f["node_kind"],
                gist=f.get("gist", ""),
            )
            for f in row["frontier"]
        ]
        query = ScorerNode(
            id=q["id"],
            title=q["title"],
            node_kind=q["node_kind"],
            gist=q.get("gist", ""),
        )
        probs = scorer.score(query, frontier)
        frontier_ids = {f.id for f in frontier}
        hits.append(ranking_hit(probs, row.get("label_relevance", {})))
        coverages.append(1.0 if coverage_ok(probs, frontier_ids) else 0.0)

    report = {
        "accuracy_top1": sum(hits) / max(len(hits), 1),
        "coverage_frac": sum(coverages) / max(len(coverages), 1),
        "n": len(hits),
        "dry_run": args.dry_run,
        "mode": mode,
        "val_path": str(args.val),
    }

    if args.gate.exists():
        gate = json.loads(args.gate.read_text())
        min_acc = float(gate.get("accuracy_top1_min", 0.0))
        report["gate_accuracy_top1_min"] = min_acc
        report["gate_passed"] = report["accuracy_top1"] >= min_acc
    else:
        report["gate_note"] = "Set accuracy_top1_min in eval_gate.json after baseline"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if report.get("gate_passed") is False:
        raise SystemExit("eval gate failed")


if __name__ == "__main__":
    main()
