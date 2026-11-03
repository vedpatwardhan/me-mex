"""Phase 4 reorg work queue: discover FIFO, cascade FILO, sibling deferral."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Literal, Optional

from app.models import GraphNode
from app.services.graph_analytics import MutableTreeIndex

ReorgWorkKind = Literal["discover", "cascade"]


@dataclass
class ReorgWorkItem:
    """Hub to split; partition command is built at dequeue time."""

    hub_id: str
    kind: ReorgWorkKind
    tree_parent_id: Optional[str] = None


def cascade_parent_id(
    tree: MutableTreeIndex, hub_id: str, hub_node: Optional[GraphNode]
) -> Optional[str]:
    """Tree parent to check for overload after orphans land (Genesis may check itself)."""
    parent_id = tree.parent_of(hub_id)
    if parent_id:
        return parent_id
    if hub_node and (
        hub_node.metadata.get("is_genesis")
        or hub_node.title.strip().lower() == "everything"
    ):
        return hub_id
    return None


class ReorgQueue:
    """
    Hybrid FIFO/FILO queue for scratchpad Phase 4.

    - Discover-selected hub IDs enqueue at tail (FIFO among discover hubs).
    - Cascade parent hub IDs prepend at head (FILO) when overload detected post-orphan.
    - Sibling deferral: parent cascade blocked while discover siblings share tree parent.
    """

    def __init__(self) -> None:
        self._pending: Deque[ReorgWorkItem] = deque()

    def enqueue_discover_fifo(self, item: ReorgWorkItem) -> None:
        self._pending.append(item)

    def prepend_cascade_filo(self, item: ReorgWorkItem) -> None:
        self._pending.appendleft(item)

    def pop_front(self) -> Optional[ReorgWorkItem]:
        if not self._pending:
            return None
        return self._pending.popleft()

    def __bool__(self) -> bool:
        return bool(self._pending)

    def pending_discover_sibling_count(self, tree_parent_id: Optional[str]) -> int:
        """Discover splits sharing this tree parent still waiting in queue."""
        return sum(
            1
            for item in self._pending
            if item.kind == "discover" and item.tree_parent_id == tree_parent_id
        )

    def should_defer_parent_cascade(self, tree_parent_id: Optional[str]) -> bool:
        return self.pending_discover_sibling_count(tree_parent_id) > 0
