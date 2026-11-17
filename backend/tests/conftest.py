import os
import sys

import pytest
from fastapi.testclient import TestClient

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DB_NAME", "test-me-mex")
from main import app  # noqa: E402
import app.db.store as store_module  # noqa: E402
from app.db.store import Store  # noqa: E402


@pytest.fixture(autouse=True)
def reset_store_singleton():
    store_module._store = None
    yield
    store_module._store = None


@pytest.fixture
def mongo_db_name():
    return os.environ.get("DB_NAME", "test-me-mex")


@pytest.fixture
def store(mongo_db_name) -> Store:
    store = Store(db_name=mongo_db_name)
    for coll in (
        "nodes",
        "edges",
        "projects",
        "passages",
        "documents",
        "staging",
        "pending_approvals",
        "highlights",
        "reorg_proposals",
    ):
        store._db[coll].delete_many({})
    yield store
    store.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def project(store):
    return store.create_project(name="Test Project")


@pytest.fixture
def project_scoped(store):
    p = store.create_project(name="Scoped Project")
    from app.db import ToolContext
    from app.tools import project as project_tools

    ctx = ToolContext(project_id=p.id, thread_id="scope", store=store)
    project_tools.update_project_scope(
        ctx, introduction="Robotics: manipulation, sim-to-real, VLA policies."
    )
    return store.get_project(p.id)
