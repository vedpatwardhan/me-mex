from app.llm import get_chains


def test_mock_vllm_chat_fixture(mock_vllm_chat, store, project):
    from app.agents.workers import conversation_worker
    from app.db import ToolContext

    ctx = ToolContext(project_id=project.id, thread_id="t", store=store)
    out = conversation_worker(ctx, "hi")
    assert out["reply"] == "Fixed assistant reply for tests."


def test_recorded_intradoc_fixture(recorded_intra_doc_chunks):
    analysis = get_chains().intradoc.invoke(
        {
            "text": "passage one\n\npassage two",
            "doc_title": "FixtureDoc",
            "user_intent": "deep read",
        }
    )
    titles = {c["title"] for c in analysis["concepts"]}
    assert "Sim-to-real transfer" in titles
    assert "Contact-rich manipulation" in titles
    assert analysis["passages"]
    assert all(concept["passage_indices"] for concept in analysis["concepts"])
