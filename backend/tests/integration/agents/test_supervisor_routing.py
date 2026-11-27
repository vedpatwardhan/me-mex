from dataclasses import replace

from app.agents.workers import route_intent
from app.llm import get_chains, set_chains_override
from app.llm.schemas import WorkerRoute
from app.models import Project
from langchain_core.runnables import RunnableLambda


def test_routes_retrieval():
    set_chains_override(
        replace(
            get_chains(),
            supervisor=RunnableLambda(
                lambda _inputs: WorkerRoute(worker="retrieval", intent="retrieval", dispatch=True)
            ),
        )
    )
    p = Project(_id="p1", name="n", introduction="Robotics scope")
    decision = route_intent(
        "Highlight related nodes in the knowledge graph for grasping and manipulation.",
        {},
        p,
    )
    assert decision.worker == "retrieval"
    assert decision.intent == "retrieval"


def test_routes_scope_when_empty():
    set_chains_override(
        replace(
            get_chains(),
            supervisor=RunnableLambda(
                lambda _inputs: WorkerRoute(
                    worker="project_scope",
                    intent="scope_conversation",
                    dispatch=True,
                )
            ),
        )
    )
    p = Project(_id="p1", name="n", introduction="")
    decision = route_intent(
        "I want to study warehouse robot grasping, sim-to-real transfer, and "
        "contact-rich manipulation over the next two months.",
        {},
        p,
    )
    assert decision.worker == "project_scope"
