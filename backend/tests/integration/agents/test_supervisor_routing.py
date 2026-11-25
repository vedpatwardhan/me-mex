from app.agents.workers import route_intent
from app.models import Project


def test_routes_retrieval():
    p = Project(_id="p1", name="n", introduction="Robotics scope")
    decision = route_intent(
        "Highlight related nodes in the knowledge graph for grasping and manipulation.",
        {},
        p,
    )
    assert decision.worker == "retrieval"
    assert decision.intent == "retrieval"


def test_routes_scope_when_empty():
    p = Project(_id="p1", name="n", introduction="")
    decision = route_intent(
        "I want to study warehouse robot grasping, sim-to-real transfer, and "
        "contact-rich manipulation over the next two months.",
        {},
        p,
    )
    assert decision.worker == "project_scope"
