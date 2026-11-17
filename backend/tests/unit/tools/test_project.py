from app.v2.db import ToolContext
from app.v2.tools import project as project_tools


def test_update_scope_syncs_genesis(v2_store, v2_project):
    ctx = ToolContext(project_id=v2_project.id, thread_id="p1", store=v2_store)
    intro = "What: robotics. Where: sim. Why: better policies."
    project_tools.update_project_scope(ctx, introduction=intro)
    p = v2_store.get_project(v2_project.id)
    assert p.introduction == intro
    genesis = v2_store.get_node(p.genesis_node_id)
    assert genesis.description == intro
