import pytest
from app.agents import session_plane
from app.models import Node, NodeKind, new_id
from app.services.checkpoints import JsonCheckpointStore


@pytest.mark.voice_plane
def test_transcript_append(tmpdir_checkpoint, monkeypatch):
    monkeypatch.setattr(session_plane, "_checkpoint", JsonCheckpointStore(str(tmpdir_checkpoint)))
    session_plane.append_transcript_turn("thr", role="user", text="hi")
    state = session_plane._checkpoint.load("thr")
    assert state["transcript"][-1]["text"] == "hi"


@pytest.mark.voice_plane
def test_routing_memory_is_bounded_and_includes_committed_graph_nodes(
    store, project, tmpdir_checkpoint, monkeypatch
):
    monkeypatch.setattr(session_plane, "_checkpoint", JsonCheckpointStore(str(tmpdir_checkpoint)))
    thread_id = "routing-memory-test"
    root = Node(
        _id=new_id("root"),
        title="The DAWN paper",
        description="Gist",
        node_kind=NodeKind.ROOT,
        project_id=project.id,
    )
    store.upsert_node(root)

    for index in range(10):
        session_plane.append_transcript_turn(
            thread_id,
            role="user" if index % 2 == 0 else "assistant",
            text=f"turn-{index}: " + "x" * 700,
        )
    session_plane.record_recent_graph_change(
        store=store,
        project_id=project.id,
        thread_id=thread_id,
        operation="gist_root",
        payload={},
        result={"result": {"root_id": root.id}},
    )

    memory = session_plane.build_routing_memory(thread_id)

    assert len(memory["recent_turns"]) == 6
    assert all(len(turn["text"]) <= 500 for turn in memory["recent_turns"])
    assert memory["recent_graph_changes"] == [
        {
            "operation": "gist_root",
            "nodes": [{"id": root.id, "title": "The DAWN paper", "node_kind": "ROOT"}],
        }
    ]
    assert "The DAWN paper" in memory["summary"]
