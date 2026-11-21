from app.agents.workers import route_intent
from app.models import Project


def test_routes_retrieval():
    p = Project(_id="p1", name="n", introduction="Robotics scope")
    decision = route_intent("What relates to grasping?", {}, p)
    assert decision.worker == "retrieval"
    assert decision.intent == "retrieval"


def test_routes_scope_when_empty():
    p = Project(_id="p1", name="n", introduction="")
    decision = route_intent("hello", {}, p)
    assert decision.worker == "project_scope"
