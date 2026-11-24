"""Apply inverse effects during turn revert."""

from __future__ import annotations

from typing import Any

from app.db import ToolContext


def apply_effect_inverse(
    *,
    store,
    project_id: str,
    thread_id: str,
    effect: dict[str, Any],
) -> tuple[bool, str | None]:
    kind = str(effect.get("kind") or "")
    inverse = effect.get("inverse") or {}
    ctx = ToolContext(project_id=project_id, thread_id=thread_id, store=store)

    if kind == "placement_edges":
        edge_ids = inverse.get("edge_ids") or []
        for eid in edge_ids:
            try:
                store.remove_edge(str(eid))
            except Exception:  # noqa: BLE001, S110
                pass
        return True, None

    if kind == "project_scope":
        prev = inverse.get("previous_introduction")
        if prev is not None:
            from app.tools import project as project_tools

            project_tools.update_project_scope(ctx, introduction=str(prev))
        return True, None

    if kind == "gist_root":
        root_id = inverse.get("root_id")
        if root_id:
            try:
                from app.tools import reorg as reorg_tools

                reorg_tools.delete_node(ctx, node_id=str(root_id))
            except Exception as exc:  # noqa: BLE001
                return False, str(exc)
        return True, None

    if kind == "pending_approval":
        approval_id = inverse.get("approval_id")
        if approval_id:
            try:
                store.resolve_approval(str(approval_id), "dismiss")
            except Exception:  # noqa: BLE001, S110
                pass
        return True, None

    if kind == "job_dispatch":
        return True, None

    if kind == "reorg_apply":
        return False, "reorg revert not supported in v1"

    return True, None
