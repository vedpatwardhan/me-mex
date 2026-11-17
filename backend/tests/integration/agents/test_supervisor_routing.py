from app.agents.workers import route_intent
from app.models import Project


def test_routes_retrieval():
    p = Project(_id="p1", name="n", introduction="Robotics scope")
    w = route_intent("What relates to grasping?", {}, p)
    assert w == "retrieval"


def test_routes_scope_when_empty():
    p = Project(_id="p1", name="n", introduction="")
    w = route_intent("hello", {}, p)
    assert w == "project_scope"
