import os
import sys
from typing import Generator

try:
    import pytest

    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

    class _MockPytest:
        def fixture(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

    pytest = _MockPytest()

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Set test database name before importing backend modules
os.environ["DB_NAME"] = "test-me-mex"

from fastapi.testclient import TestClient
from main import app
from app.db import db_engine
from app.models import ProjectWorkspace, GraphNode, GraphEdge, ChatMessageRecord


def reset_test_database():
    """Clear all collections in test-me-mex (MongoDB or in-memory) and seed initial test data."""
    if db_engine.use_mongo:
        db_engine.db.nodes.delete_many({})
        db_engine.db.edges.delete_many({})
        db_engine.db.projects.delete_many({})
        db_engine.db.chat_messages.delete_many({})
        db_engine.db.documents.delete_many({})
        db_engine.db.passages.delete_many({})
    else:
        db_engine.mem_nodes.clear()
        db_engine.mem_edges.clear()
        db_engine.mem_projects.clear()
        db_engine.mem_messages.clear()
        db_engine.mem_documents.clear()
        db_engine.mem_passages.clear()

    # Seed default global project
    global_proj = ProjectWorkspace(
        _id="global",
        name="Global Master Graph",
        description="Master superset database across all paradigms and literature.",
    )
    db_engine.upsert_project(global_proj)

    # Seed baseline test nodes
    n1 = GraphNode(
        _id="concept_world_models",
        title="World Models",
        text_body="# World Models\nGeneral paradigm of generative world models in robotics.",
        metadata={"domain_tags": ["world_models"]},
        project_ids=["global"],
    )
    n2 = GraphNode(
        _id="concept_pixel_world_models",
        title="Pixel-Space World Models",
        text_body="# Pixel-Space World Models\nGenerates future raw RGB frames directly.",
        metadata={"domain_tags": ["pixel_space"], "status": "HISTORICAL_SUPERSEDED"},
        passage_pointers=["pass_pixel_01"],
        project_ids=["global"],
    )
    n3 = GraphNode(
        _id="concept_latent_world_models",
        title="Latent-Space World Models",
        text_body="# Latent-Space World Models\nGenerates representations in latent space for 100x faster planning.",
        metadata={"domain_tags": ["latent_space"], "status": "PRIMARY_ACTIVE"},
        passage_pointers=["pass_latent_01"],
        project_ids=["global"],
    )
    n4 = GraphNode(
        _id="concept_action_mpc",
        title="Action Planning via MPC",
        text_body="# Action Planning via MPC\nTrajectory optimization over world model rollouts.",
        metadata={"domain_tags": ["planning", "mpc"]},
        project_ids=["global"],
    )
    for n in [n1, n2, n3, n4]:
        db_engine.upsert_node(n)

    # Seed baseline test edges
    e1 = GraphEdge(
        _id="edge_pixel_to_mpc",
        source_id="concept_pixel_world_models",
        target_id="concept_action_mpc",
        is_directional=True,
        text_body="Historical MPC rollout over raw pixel predictions.",
        weight=0.3,
        status="HISTORICAL_SUPERSEDED",
        project_ids=["global"],
    )
    e2 = GraphEdge(
        _id="edge_latent_to_mpc",
        source_id="concept_latent_world_models",
        target_id="concept_action_mpc",
        is_directional=True,
        text_body="Primary SOTA 100x speedup for MPC action planning in latent space.",
        weight=1.0,
        status="PRIMARY_ACTIVE",
        project_ids=["global"],
    )
    e3 = GraphEdge(
        _id="edge_pixel_parallel_latent",
        source_id="concept_pixel_world_models",
        target_id="concept_latent_world_models",
        is_directional=False,
        text_body="Parallel generative world model paradigms operating on raw pixels vs latent embeddings.",
        weight=1.0,
        status="PRIMARY_ACTIVE",
        project_ids=["global"],
    )
    for e in [e1, e2, e3]:
        db_engine.upsert_edge(e)


def teardown_test_database():
    """Wipe all collections in test-me-mex (MongoDB or in-memory) at test completion."""
    if db_engine.use_mongo:
        db_engine.db.nodes.delete_many({})
        db_engine.db.edges.delete_many({})
        db_engine.db.projects.delete_many({})
        db_engine.db.chat_messages.delete_many({})
        db_engine.db.documents.delete_many({})
        db_engine.db.passages.delete_many({})
    else:
        db_engine.mem_nodes.clear()
        db_engine.mem_edges.clear()
        db_engine.mem_projects.clear()
        db_engine.mem_messages.clear()
        db_engine.mem_documents.clear()
        db_engine.mem_passages.clear()


@pytest.fixture(autouse=True)
def clean_test_db() -> Generator[None, None, None]:
    """Autouse fixture resetting test-me-mex before each test and guaranteeing teardown afterwards."""
    reset_test_database()
    try:
        yield
    finally:
        teardown_test_database()


@pytest.fixture
def test_client() -> Generator[TestClient, None, None]:
    """TestClient fixture targeting main FastAPI application."""
    with TestClient(app) as client:
        yield client
