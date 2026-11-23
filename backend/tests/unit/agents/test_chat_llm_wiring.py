from app.agents.workers import route_intent
from app.llm import get_chains
from app.models import Project
from app.prompts import _read_raw_prompt, load_prompt
from langchain_core.prompts import ChatPromptTemplate


def test_intradoc_prompt_json_examples_compatible_with_chat_template():
    """JSON schema blocks use literal braces; LangChain f-string templates require doubling."""
    _read_raw_prompt.cache_clear()
    for name, human, kwargs in (
        ("passage_concept_extraction", "{chunk_payload}", {"doc_title": "{doc_title}"}),
        ("consolidate_concepts", "{reduce_payload}", {"doc_title": "{doc_title}"}),
        (
            "worker_route",
            "{payload}",
            {"project_scope": "{project_scope}"},
        ),
    ):
        ChatPromptTemplate.from_messages(
            [
                ("system", load_prompt(name, **kwargs)),
                ("human", human),
            ]
        )


def test_route_uses_langchain_supervisor():
    p = Project(_id="p", name="t", introduction="scope")
    assert route_intent("what relates to X?", {}, p).worker == "retrieval"


def test_intradoc_chain_invoke():
    analysis = get_chains().intradoc.invoke(
        {
            "text": "We propose a new manipulation policy.",
            "doc_title": "Paper",
            "user_intent": "deep read",
        }
    )
    assert len(analysis["concepts"]) >= 1
    assert analysis["concepts"][0]["title"]
    assert analysis["doc_description"]
    assert analysis["passages"]
