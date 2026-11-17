import pytest

from app.db import ToolContext
from app.errors import ImmutableNodeViolation
from app.models import NodeKind
from app.tools import gist, reorg


def test_preview_and_apply(v2_store, v2_project):
    ctx = ToolContext(project_id=v2_project.id, thread_id="r1", store=v2_store)
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


def test_delete_root_forbidden(v2_store, v2_project):
    ctx = ToolContext(project_id=v2_project.id, thread_id="r1", store=v2_store)
    root = gist.create_or_update_root_gist(ctx, title="R", gist="g")
    with pytest.raises(ImmutableNodeViolation):
        reorg.delete_node(ctx, node_id=root["root_id"])
