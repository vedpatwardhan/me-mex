from app.v2.agents.workers import route_intent
from app.v2.models import V2Project


def test_routes_retrieval():
    p = V2Project(_id="p1", name="n", introduction="Robotics scope")
    w = route_intent("What relates to grasping?", {}, p)
    assert w == "retrieval"


def test_routes_scope_when_empty():
    p = V2Project(_id="p1", name="n", introduction="")
    w = route_intent("hello", {}, p)
    assert w == "project_scope"
