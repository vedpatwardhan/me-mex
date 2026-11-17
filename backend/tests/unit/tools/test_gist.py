from app.v2.db import ToolContext
from app.v2.models import NodeKind
from app.v2.tools import gist


def test_create_root_gist(v2_store, v2_project):
    ctx = ToolContext(project_id=v2_project.id, thread_id="t1", store=v2_store)
    out = gist.create_or_update_root_gist(ctx, title="Paper A", gist="Two line gist.")
    node = v2_store.get_node(out["root_id"])
    assert node.node_kind == NodeKind.ROOT
    assert node.description == "Two line gist."


def test_promote_todo(v2_store, v2_project):
    ctx = ToolContext(project_id=v2_project.id, thread_id="t1", store=v2_store)
    todo = gist.create_todo(ctx, title="Follow up", body="read more")
    gist.promote_todo_to_concept_m(ctx, todo_id=todo["node_id"])
    node = v2_store.get_node(todo["node_id"])
    assert node.node_kind == NodeKind.CONCEPT_M
