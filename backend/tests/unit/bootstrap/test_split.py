import json

from app.bootstrap.split_train_eval import split_rows


def test_split_reproducible():
    rows = [{"id": str(i), "text": f"row{i}"} for i in range(20)]
    a, b = split_rows(rows, val_fraction=0.2, seed=42)
    c, d = split_rows(rows, val_fraction=0.2, seed=42)
    assert [r["id"] for r in a] == [r["id"] for r in c]
    assert len(a) + len(b) == 20
    assert 1 <= len(b) <= 8
