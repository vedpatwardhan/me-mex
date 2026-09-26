from app.db import db_engine
from app.models import ProjectWorkspace, GraphNode, GraphEdge, ChatMessageRecord


def test_project_workspace_crud():
    """Verify ProjectWorkspace creation, retrieval, and storage in test-me-mex database."""
    proj = ProjectWorkspace(
        _id="proj_robotics",
        name="Robotics Steering",
        description="Workspace for policy steering.",
    )
    db_engine.upsert_project(proj)

    projects = db_engine.get_projects()
    assert len(projects) >= 2
    assert any(p.id == "proj_robotics" for p in projects)

    fetched = db_engine.get_project("proj_robotics")
    assert fetched is not None
    assert fetched.name == "Robotics Steering"


def test_node_and_edge_project_scoping():
    """Verify get_nodes and get_edges isolate entities based on project_ids."""
    scoped_node = GraphNode(
        _id="concept_scoped_policy",
        title="Scoped Policy Learning",
        text_body="Policy learning node.",
        project_ids=["global", "proj_robotics"],
    )
    db_engine.upsert_node(scoped_node)

    scoped_edge = GraphEdge(
        _id="edge_scoped_policy",
        source_id="concept_scoped_policy",
        target_id="concept_action_mpc",
        is_directional=True,
        text_body="Scoped policy link",
        project_ids=["global", "proj_robotics"],
    )
    db_engine.upsert_edge(scoped_edge)

    # Scoped queries
    global_nodes = db_engine.get_nodes("global")
    robotics_nodes = db_engine.get_nodes("proj_robotics")
    unrelated_nodes = db_engine.get_nodes("proj_unrelated")

    assert any(n.id == "concept_scoped_policy" for n in global_nodes)
    assert any(n.id == "concept_scoped_policy" for n in robotics_nodes)
    assert not any(n.id == "concept_scoped_policy" for n in unrelated_nodes)

    global_edges = db_engine.get_edges("global")
    robotics_edges = db_engine.get_edges("proj_robotics")
    unrelated_edges = db_engine.get_edges("proj_unrelated")

    assert any(e.id == "edge_scoped_policy" for e in global_edges)
    assert any(e.id == "edge_scoped_policy" for e in robotics_edges)
    assert not any(e.id == "edge_scoped_policy" for e in unrelated_edges)


def test_chat_message_persistence_and_isolation():
    """Verify chat message persistence and isolation per project."""
    m1 = ChatMessageRecord(
        _id="msg_r_1",
        project_id="proj_robotics",
        sender="user",
        text="Hello robotics",
    )
    m2 = ChatMessageRecord(
        _id="msg_g_1",
        project_id="global",
        sender="user",
        text="Hello global",
    )
    db_engine.upsert_message(m1)
    db_engine.upsert_message(m2)

    r_history = db_engine.get_chat_history("proj_robotics")
    g_history = db_engine.get_chat_history("global")

    assert len(r_history) == 1
    assert r_history[0].id == "msg_r_1"

    assert any(m.id == "msg_g_1" for m in g_history)
    assert not any(m.id == "msg_r_1" for m in g_history)
