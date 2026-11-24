"""JSON file checkpointer for LangGraph session state."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from app.config import settings

_store_lock = threading.RLock()


class JsonCheckpointStore:
    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or settings.CHECKPOINTS_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, thread_id: str) -> Path:
        safe = thread_id.replace("/", "_")
        return self.base_dir / safe / "latest.json"

    def save(self, thread_id: str, state: dict[str, Any]) -> None:
        with _store_lock:
            path = self._path(thread_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(state, indent=2, default=str)
            tmp = path.with_name("latest.json.tmp")
            tmp.write_text(payload)
            tmp.replace(path)

    def load(self, thread_id: str) -> dict[str, Any] | None:
        with _store_lock:
            path = self._path(thread_id)
            if not path.exists():
                return None
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                backup = path.with_name("latest.json.bak")
                if path.exists():
                    path.replace(backup)
                return None

    def clear(self, thread_id: str) -> None:
        path = self._path(thread_id)
        if path.exists():
            path.unlink()
