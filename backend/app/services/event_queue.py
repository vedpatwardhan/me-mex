import time
from typing import Dict, List, Any
from app.models import ProjectEventRecord


class EphemeralEventQueue:
    """In-memory event queue keeping max 15 recent events per project (zero DB storage)."""

    def __init__(self, default_limit: int = 15):
        self.default_limit = default_limit
        self.queues: Dict[str, List[ProjectEventRecord]] = {}

    def push(self, project_id: str, event_data: Dict[str, Any]):
        """Push event into project-scoped FIFO queue capped at 15 items."""
        import uuid

        event_type = (
            event_data.get("event_type") or event_data.get("event") or "system_event"
        )
        rec = ProjectEventRecord(
            _id=f"evt_{uuid.uuid4().hex[:8]}",
            project_id=project_id,
            event_type=event_type,
            data=event_data,
            timestamp=event_data.get("timestamp") or time.time(),
        )

        if project_id not in self.queues:
            self.queues[project_id] = []
        self.queues[project_id].append(rec)
        if len(self.queues[project_id]) > self.default_limit:
            self.queues[project_id] = self.queues[project_id][-self.default_limit :]

    def get_events(
        self, project_id: str = "global", limit: int = 15
    ) -> List[ProjectEventRecord]:
        """Retrieve recent events in chronological order."""
        events = self.queues.get(project_id, [])
        return sorted(events[-limit:], key=lambda e: e.timestamp)

    def clear(self):
        """Wipe all queues (for testing)."""
        self.queues.clear()


event_queue = EphemeralEventQueue()
