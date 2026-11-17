import pytest

from app.db import ToolContext
from app.errors import ImmutableNodeViolation
from app.models import NodeKind
from app.tools import gist, reorg


def test_preview_and_apply(store, project):
    ctx = ToolContext(project_id=project.id, thread_id="r1", store=store)
    hub = gist.create_todo(ctx, title="Hub", body="")
    gist.promote_todo_to_concept_m(ctx, todo_id=hub["node_id"])
    child = gist.create_note(ctx, title="Child", body="")
    prop = reorg.write_reorg_proposal(
        ctx,
        proposal={
            "before": {},
            "after": {},
            "moves": [{"node_id": child["node_id"], "parent_id": hub["node_id"]}],
        },
    )
    preview = reorg.preview_reorg_diff(ctx, proposal_id=prop["proposal_id"])
    assert preview["proposal_id"] == prop["proposal_id"]
    reorg.apply_reorg_plan(ctx, proposal_id=prop["proposal_id"])


def test_delete_root_forbidden(store, project):
    ctx = ToolContext(project_id=project.id, thread_id="r1", store=store)
    root = gist.create_or_update_root_gist(ctx, title="R", gist="g")
    with pytest.raises(ImmutableNodeViolation):
        reorg.delete_node(ctx, node_id=root["root_id"])
