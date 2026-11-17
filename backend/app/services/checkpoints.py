"""JSON file checkpointer for LangGraph session state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.config import settings


class JsonCheckpointStore:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or settings.CHECKPOINTS_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, thread_id: str) -> Path:
        safe = thread_id.replace("/", "_")
        return self.base_dir / safe / "latest.json"

    def save(self, thread_id: str, state: dict[str, Any]) -> None:
        path = self._path(thread_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, default=str))

    def load(self, thread_id: str) -> Optional[dict[str, Any]]:
        path = self._path(thread_id)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def clear(self, thread_id: str) -> None:
        path = self._path(thread_id)
        if path.exists():
            path.unlink()
