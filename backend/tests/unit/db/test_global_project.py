import pytest
from app.db.store import GLOBAL_PROJECT_ID
from app.errors import NotFoundError


def test_ensure_global_project_creates_genesis(store):
    project = store.ensure_global_project()
    assert project.id == GLOBAL_PROJECT_ID
    assert project.introduction == ""
    nodes = store.list_nodes(GLOBAL_PROJECT_ID)
    assert len(nodes) == 1
    assert nodes[0].id == project.genesis_node_id
    assert nodes[0].metadata.get("genesis") is True


def test_ensure_global_project_idempotent(store):
    first = store.ensure_global_project()
    second = store.ensure_global_project()
    assert first.id == second.id
    assert len(store.list_nodes(GLOBAL_PROJECT_ID)) == 1


def test_global_not_found_before_seed(store):
    with pytest.raises(NotFoundError):
        store.get_project(GLOBAL_PROJECT_ID)
