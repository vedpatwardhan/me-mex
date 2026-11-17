"""Join robotics tier markdown → decision trace JSONL (no training here)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _parse_deeper_read(path: Path) -> dict[str, dict]:
    """Map title fragment → gist row."""
    roots: dict[str, dict] = {}
    if not path.exists():
        return roots
    text = path.read_text(encoding="utf-8")
    for block in re.split(r"\n##+ ", text):
        if not block.strip():
            continue
        lines = block.strip().splitlines()
        title = lines[0].strip()
        gist = " ".join(l.strip() for l in lines[1:4] if l.strip())[:500]
        key = title[:80].lower()
        roots[key] = {"title": title, "gist": gist, "node_kind": "ROOT"}
    return roots


def emit_synthetic_rows(notes_root: dict) -> list[dict]:
    """Minimal synthetic placement traces for bootstrap smoke tests."""
    rows = []
    ids = list(notes_root.keys())[:5]
    if len(ids) < 2:
        return rows
    query_id = ids[0]
    frontier = [
        {"id": k, "title": notes_root[k]["title"], "node_kind": "ROOT"} for k in ids[1:]
    ]
    labels = {frontier[0]["id"]: 1.0}
    for f in frontier[1:]:
        labels[f["id"]] = 0.0
    rows.append(
        {
            "project_id": "robotics",
            "provenance": "bootstrap_notes",
            "query_node": {
                "id": query_id,
                "title": notes_root[query_id]["title"],
                "node_kind": "ROOT",
            },
            "frontier": frontier,
            "label_relevance": labels,
            "model_relevance_probs": {},
            "user_expanded_ids": [frontier[0]["id"]],
        }
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path(__file__).resolve().parents[5] / "docs",
        help="cortex-os docs with deeper_read_notes.md",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[3]
        / "data"
        / "decision_training"
        / "robotics"
        / "bootstrap.jsonl",
    )
    args = parser.parse_args()
    roots = _parse_deeper_read(args.docs_dir / "deeper_read_notes.md")
    rows = emit_synthetic_rows(roots)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print(f"Wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
