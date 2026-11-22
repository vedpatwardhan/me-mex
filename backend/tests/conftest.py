import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ.setdefault("TESTING", "1")
_run_live_llm_tests = os.environ.get("ME_MEX_RUN_LIVE_LLM_TESTS") == "1"
_xdist_worker = os.environ.get("PYTEST_XDIST_WORKER")
if _xdist_worker:
    os.environ["DB_NAME"] = f"test-me-mex-{_xdist_worker}"
else:
    os.environ.setdefault("DB_NAME", "test-me-mex")
if not _run_live_llm_tests:
    os.environ.setdefault("CHAT_LLM_MODE", "stub")
    os.environ.setdefault("DECISION_SCORER_MODE", "mock")
import app.db.store as store_module
from app.db.store import Store
from app.llm.chains import (
    AgentChains,
    get_chains,
    set_chains_override,
    set_recorded_intradoc,
)
from app.services.decision_scorer import set_decision_scorer_override
from langchain_core.runnables import RunnableLambda
from main import app

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def reset_store_singleton():
    store_module._store = None
    yield
    store_module._store = None


@pytest.fixture(autouse=True)
def reset_job_runtime():
    """Keep the process-local job ledger isolated between tests."""
    from app.agents import job_runtime

    with job_runtime._registry_lock:
        job_runtime._jobs.clear()
        job_runtime._by_thread.clear()
        job_runtime._cancel_events.clear()
        job_runtime._resume_events.clear()
    yield
    with job_runtime._registry_lock:
        job_runtime._jobs.clear()
        job_runtime._by_thread.clear()
        job_runtime._cancel_events.clear()
        job_runtime._resume_events.clear()


@pytest.fixture(autouse=True)
def reset_llm_overrides():
    set_chains_override(None)
    set_recorded_intradoc(None)
    set_decision_scorer_override(None)
    yield
    set_chains_override(None)
    set_recorded_intradoc(None)
    set_decision_scorer_override(None)


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
def voice_context_json(project):
    return {
        "voice_turn": True,
        "active_project_id": project.id,
        "project_id": project.id,
        "custom_fields": {},
    }


@pytest.fixture
def empty_project(store):
    return store.create_project(name="Empty Project")


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


@pytest.fixture
def robotics_seed_graph(store, project_scoped):
    """Small graph for W4/W5/W11."""
    from app.models import Edge, Node, NodeKind, new_id

    pid = project_scoped.id
    hub = Node(
        _id=new_id("hub"),
        title="Manipulation hub",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=pid,
    )
    store.upsert_node(hub)
    root = Node(
        _id=new_id("root"),
        title="ERA paper",
        description="gist",
        node_kind=NodeKind.ROOT,
        project_id=pid,
    )
    store.upsert_node(root)
    for i in range(9):
        n = Node(
            _id=new_id("leaf"),
            title=f"Leaf {i}",
            description="",
            node_kind=NodeKind.CONCEPT_M,
            project_id=pid,
        )
        store.upsert_node(n)
        store.add_edge(
            Edge(
                _id=new_id("edge"),
                source_id=hub.id,
                target_id=n.id,
                project_id=pid,
            )
        )
    return {"hub_id": hub.id, "root_id": root.id, "project_id": pid}


@pytest.fixture
def tmpdir_checkpoint(tmp_path, monkeypatch):
    from app.services import checkpoints as cp_mod

    monkeypatch.setattr(cp_mod.settings, "CHECKPOINTS_DIR", str(tmp_path / "cp"))
    return tmp_path / "cp"


@pytest.fixture
def mock_vllm_chat():
    """Fixed assistant reply via LangChain chain override."""
    base = get_chains()
    set_chains_override(
        AgentChains(
            supervisor=base.supervisor,
            conversation=RunnableLambda(lambda _: "Fixed assistant reply for tests."),
            gist_draft=base.gist_draft,
            project_scope=base.project_scope,
            retrieval_summary=base.retrieval_summary,
            intradoc=base.intradoc,
        )
    )


@pytest.fixture
def recorded_intra_doc_chunks():
    path = FIXTURES / "intradoc" / "recorded_chunks.json"
    data = json.loads(path.read_text())
    set_recorded_intradoc(data)
    return data
