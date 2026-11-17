from app.db import ToolContext
from app.models import NodeKind
from app.tools import gist


def test_create_root_gist(store, project):
    ctx = ToolContext(project_id=project.id, thread_id="t1", store=store)
    out = gist.create_or_update_root_gist(ctx, title="Paper A", gist="Two line gist.")
    node = store.get_node(out["root_id"])
    assert node.node_kind == NodeKind.ROOT
    assert node.description == "Two line gist."


def test_promote_todo(store, project):
    ctx = ToolContext(project_id=project.id, thread_id="t1", store=store)
    todo = gist.create_todo(ctx, title="Follow up", body="read more")
    gist.promote_todo_to_concept_m(ctx, todo_id=todo["node_id"])
    node = store.get_node(todo["node_id"])
    assert node.node_kind == NodeKind.CONCEPT_M
