from app.db import ToolContext
from app.tools import project as project_tools


def test_update_scope_syncs_genesis(store, project):
    ctx = ToolContext(project_id=project.id, thread_id="p1", store=store)
    intro = "What: robotics. Where: sim. Why: better policies."
    project_tools.update_project_scope(ctx, introduction=intro)
    p = store.get_project(project.id)
    assert p.introduction == intro
    genesis = store.get_node(p.genesis_node_id)
    assert genesis.description == intro
