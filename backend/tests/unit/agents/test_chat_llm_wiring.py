from app.agents.workers import run_intradoc_extract
from app.agents.workers import conversation_worker, route_intent
from app.db import ToolContext
from app.models import Project
from app.services.chat_llm import StubChatLLM, get_chat_llm


def test_route_uses_chat_llm():
    p = Project(_id="p", name="t", introduction="scope")
    assert route_intent("what relates to X?", {}, p) == "retrieval"
    assert isinstance(get_chat_llm(), StubChatLLM)


def test_conversation_worker_calls_llm(store, project):
    ctx = ToolContext(project_id=project.id, thread_id="u1", store=store)
    out = conversation_worker(ctx, "hello there")
    assert out["graph_write"] is False
    assert "[stub]" in out["reply"]


def test_intradoc_extract_pipeline():
    concepts = run_intradoc_extract(
        text="We propose a new manipulation policy.",
        doc_title="Paper",
        user_intent="deep read",
    )
    assert len(concepts) >= 1
    assert concepts[0]["title"]
