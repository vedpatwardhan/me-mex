import os
import sys

import pytest
from fastapi.testclient import TestClient

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DB_NAME", "test-me-mex")
os.environ.setdefault("ME_MEX_V2", "1")

from main import app  # noqa: E402
import app.v2.db.store as store_module  # noqa: E402
from app.v2.db.store import V2Store  # noqa: E402


@pytest.fixture(autouse=True)
def reset_v2_store_singleton():
    store_module._store = None
    yield
    store_module._store = None


@pytest.fixture
def mongo_db_name():
    return os.environ.get("DB_NAME", "test-me-mex")


@pytest.fixture
def v2_store(mongo_db_name) -> V2Store:
    store = V2Store(db_name=mongo_db_name)
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
def v2_project(v2_store):
    return v2_store.create_project(name="Test Project")


@pytest.fixture
def v2_project_scoped(v2_store):
    p = v2_store.create_project(name="Scoped Project")
    from app.v2.db import ToolContext
    from app.v2.tools import project as project_tools

    ctx = ToolContext(project_id=p.id, thread_id="scope", store=v2_store)
    project_tools.update_project_scope(
        ctx, introduction="Robotics: manipulation, sim-to-real, VLA policies."
    )
    return v2_store.get_project(p.id)
