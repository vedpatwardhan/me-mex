from app.agents.context_preprocessor import (
    apply_custom_fields_to_text,
    block_graph_writes_without_scope,
    prioritize_project_scope_until_complete,
)


def test_custom_fields_append_to_text():
    out = apply_custom_fields_to_text(
        "link paper",
        {"custom_fields": {"root_id": "r1", "arxiv_id": "1234.5678"}},
    )
    assert "root_id=r1" in out
    assert "arxiv_id=1234.5678" in out


def test_scope_blocks_write_workers():
    assert block_graph_writes_without_scope("", "gist") is True
    assert block_graph_writes_without_scope("Robotics.", "gist") is False
    assert block_graph_writes_without_scope("", "conversation") is False


def test_p1_scope_takes_priority_over_routes():
    assert prioritize_project_scope_until_complete("", "gist", {}) == "project_scope"
    assert prioritize_project_scope_until_complete("", "retrieval", {}) == "retrieval"
    assert prioritize_project_scope_until_complete("", "conversation", {}) == "conversation"
    assert prioritize_project_scope_until_complete("Robotics.", "gist", {}) == "gist"
    assert (
        prioritize_project_scope_until_complete(
            "",
            "intradoc",
            {"custom_fields": {"resume_job_id": "j1"}},
        )
        == "intradoc"
    )
