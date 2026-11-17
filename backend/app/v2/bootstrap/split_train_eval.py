"""Split bootstrap JSONL into train/val (deterministic hash split)."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def split_rows(
    rows: list[dict[str, Any]], *, val_fraction: float = 0.2, seed: int = 0
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministic hold-out by row id hash (seed mixes into bucket)."""
    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("id", row))
        h = int(hashlib.md5(f"{seed}:{key}".encode()).hexdigest(), 16) % 1000
        (val if h < int(val_fraction * 1000) else train).append(row)
    return train, val


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    train, val = [], []
    for line in args.input.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = row.get("query_node", {}).get("id", line)
        h = int(hashlib.md5(key.encode()).hexdigest(), 16) % 1000
        (val if h < args.val_ratio * 1000 else train).append(row)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "train.jsonl").write_text(
        "\n".join(json.dumps(r) for r in train) + "\n"
    )
    (args.out_dir / "val.jsonl").write_text(
        "\n".join(json.dumps(r) for r in val) + "\n"
    )
    print(f"train={len(train)} val={len(val)} -> {args.out_dir}")


if __name__ == "__main__":
    main()
