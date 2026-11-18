from unittest.mock import MagicMock, patch

from app.agents import workers
from app.db import ToolContext
from app.models import Node, NodeKind, Project


def test_retrieval_defaults_to_genesis_when_no_selection():
    genesis_id = "genesis_p1"
    child_id = "child_1"
    pid = "p1"
    project = Project(
        _id=pid,
        name="Test",
        introduction="",
        genesis_node_id=genesis_id,
    )
    genesis = Node(
        _id=genesis_id,
        title="Genesis",
        description="root",
        node_kind=NodeKind.ROOT,
        project_id=pid,
    )
    child = Node(
        _id=child_id,
        title="Child hub",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=pid,
    )

    store = MagicMock()
    store.get_project.return_value = project

    def get_node(nid: str) -> Node:
        return genesis if nid == genesis_id else child

    store.get_node.side_effect = get_node
    store.neighbors.return_value = [child_id]

    ctx = ToolContext(store=store, project_id=pid, thread_id="t1")
    chains = MagicMock()
    chains.retrieval_summary.invoke.return_value = "ok"
    with patch.object(workers, "get_decision_scorer") as mock_scorer:
        mock_scorer.return_value.score.return_value = {child_id: 1.0}
        with patch.object(workers, "get_chains", return_value=chains):
            with patch.object(workers.link, "highlight_nodes", return_value={}):
                workers.retrieval_worker(ctx, "what relates?", context={})
    first_query = mock_scorer.return_value.score.call_args_list[0][0][0]
    assert first_query.id == genesis_id