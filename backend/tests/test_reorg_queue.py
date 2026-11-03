"""Unit tests for Phase 4 reorg queue (FIFO/FILO + sibling deferral)."""

from app.services.reorg_queue import ReorgQueue, ReorgWorkItem


def _item(
    hub_id: str, kind: str = "discover", parent: str | None = "P"
) -> ReorgWorkItem:
    return ReorgWorkItem(
        hub_id=hub_id,
        kind=kind,  # type: ignore[arg-type]
        tree_parent_id=parent,
    )


def test_discover_fifo_order():
    q = ReorgQueue()
    q.enqueue_discover_fifo(_item("A"))
    q.enqueue_discover_fifo(_item("B"))
    assert q.pop_front().hub_id == "A"
    assert q.pop_front().hub_id == "B"


def test_cascade_filo_prepended_before_discover_tail():
    q = ReorgQueue()
    q.enqueue_discover_fifo(_item("A"))
    q.enqueue_discover_fifo(_item("B"))
    q.prepend_cascade_filo(_item("P", kind="cascade", parent=None))
    assert q.pop_front().hub_id == "P"
    assert q.pop_front().hub_id == "A"


def test_sibling_deferral_while_discover_siblings_in_queue():
    q = ReorgQueue()
    q.enqueue_discover_fifo(_item("child1", parent="P"))
    q.enqueue_discover_fifo(_item("child2", parent="P"))
    assert q.should_defer_parent_cascade("P") is True
    q.pop_front()
    assert q.should_defer_parent_cascade("P") is True
    q.pop_front()
    assert q.should_defer_parent_cascade("P") is False
