from __future__ import annotations

from app.v2.db import ToolContext


def update_project_scope(ctx: ToolContext, *, introduction: str) -> dict:
    ctx.store.update_project_scope(ctx.project_id, introduction)
    return {"project_id": ctx.project_id, "introduction": introduction}
