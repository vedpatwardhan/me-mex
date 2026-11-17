from app.agents.workers import route_intent
from app.llm import get_chains
from app.models import Project


def test_route_uses_langchain_supervisor():
    p = Project(_id="p", name="t", introduction="scope")
    assert route_intent("what relates to X?", {}, p) == "retrieval"


def test_intradoc_chain_invoke():
    concepts = get_chains().intradoc.invoke(
        {
            "text": "We propose a new manipulation policy.",
            "doc_title": "Paper",
            "user_intent": "deep read",
        }
    )
    assert len(concepts) >= 1
    assert concepts[0]["title"]
