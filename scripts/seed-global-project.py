#!/usr/bin/env python3
"""Ensure the default global project exists (genesis node, empty scope)."""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.db.store import Store


def main() -> int:
    store = Store(db_name=os.environ.get("DB_NAME"))
    try:
        project = store.ensure_global_project()
        print(
            f"global project ready: id={project.id} genesis={project.genesis_node_id}",
            flush=True,
        )
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
