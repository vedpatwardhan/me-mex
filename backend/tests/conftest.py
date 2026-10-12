import os
import sys
import time
import json
from typing import Generator

import pytest

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Set environment to testing mode
os.environ["TESTING"] = "1"

from fastapi.testclient import TestClient
from main import app
from app.db import db_engine
from app.config import settings
from app.services.llm_gateway import llm_gateway
from app.services.event_queue import event_queue
from app.models import ProjectWorkspace, GraphNode, GraphEdge, ChatMessageRecord

# Global tracking across tests for the terminal summary and metrics log
_TEST_TIMINGS = []
_TEST_START_TIME = time.time()


@pytest.fixture(scope="session", autouse=True)
def configure_worker_database(request):
    """Configures worker-isolated MongoDB database name based on pytest-xdist worker_id.
    Worker 1 (gw0) -> test-me-mex-w1
    Worker 2 (gw1) -> test-me-mex-w2
    Single process / master -> test-me-mex
    """
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    if worker_id == "gw0":
        db_name = "test-me-mex-w1"
    elif worker_id == "gw1":
        db_name = "test-me-mex-w2"
    else:
        db_name = "test-me-mex"

    os.environ["DB_NAME"] = db_name
    reset_test_database()
    yield
    teardown_test_database()


def reset_test_database():
    """Clear all collections in isolated worker DB (MongoDB or in-memory) and seed initial test data."""
    if db_engine.use_mongo and db_engine.db is not None:
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

    event_queue.clear()

    # Seed default global project
    global_proj = ProjectWorkspace(
        _id="global",
        name="Global Master Graph",
        description="Master superset database across all paradigms and literature.",
    )
    db_engine.upsert_project(global_proj)

    # Seed primordial Universal Genesis Concept Node ('Everything')
    genesis_node = GraphNode(
        _id="concept_genesis",
        node_type="CONCEPT",
        title="Everything",
        description="# Everything\nPrimordial universal knowledge anchor. High-level root concept connecting all domain paradigms and foundational literature.",
        metadata={
            "immutable": False,
            "is_genesis": True,
            "status": "PRIMARY_ACTIVE",
        },
        project_ids=["global"],
    )
    db_engine.upsert_node(genesis_node)

    # Seed baseline test nodes
    n1 = GraphNode(
        _id="concept_world_models",
        title="World Models",
        description="# World Models\nGeneral paradigm of generative world models in robotics.",
        metadata={"domain_tags": ["world_models"]},
        project_ids=["global"],
    )
    n2 = GraphNode(
        _id="concept_pixel_world_models",
        title="Pixel-Space World Models",
        description="# Pixel-Space World Models\nGenerates future raw RGB frames directly.",
        metadata={"domain_tags": ["pixel_space"], "status": "HISTORICAL_SUPERSEDED"},
        passage_ids=["pass_pixel_01"],
        project_ids=["global"],
    )
    n3 = GraphNode(
        _id="concept_latent_world_models",
        title="Latent-Space World Models",
        description="# Latent-Space World Models\nGenerates representations in latent space for 100x faster planning.",
        metadata={"domain_tags": ["latent_space"], "status": "PRIMARY_ACTIVE"},
        passage_ids=["pass_latent_01"],
        project_ids=["global"],
    )
    n4 = GraphNode(
        _id="concept_action_mpc",
        title="Action Planning via MPC",
        description="# Action Planning via MPC\nTrajectory optimization over world model rollouts.",
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
        description="Historical MPC rollout over raw pixel predictions.",
        weight=0.3,
        status="HISTORICAL_SUPERSEDED",
        project_ids=["global"],
    )
    e2 = GraphEdge(
        _id="edge_latent_to_mpc",
        source_id="concept_latent_world_models",
        target_id="concept_action_mpc",
        is_directional=True,
        description="Primary SOTA 100x speedup for MPC action planning in latent space.",
        weight=1.0,
        status="PRIMARY_ACTIVE",
        project_ids=["global"],
    )
    e3 = GraphEdge(
        _id="edge_pixel_parallel_latent",
        source_id="concept_pixel_world_models",
        target_id="concept_latent_world_models",
        is_directional=False,
        description="Parallel generative world model paradigms operating on raw pixels vs latent embeddings.",
        weight=1.0,
        status="PRIMARY_ACTIVE",
        project_ids=["global"],
    )
    for e in [e1, e2, e3]:
        db_engine.upsert_edge(e)


def teardown_test_database():
    """Wipe all collections in isolated worker DB (MongoDB or in-memory) at test completion."""
    if db_engine.use_mongo and db_engine.db is not None:
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

    event_queue.clear()


@pytest.fixture(autouse=True)
def clean_test_db() -> Generator[None, None, None]:
    """Autouse fixture resetting worker DB before each test and guaranteeing teardown afterwards."""
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


def pytest_runtest_setup(item):
    """Pre-flight check: automatically skip tests requiring vLLM if the remote server is offline."""
    if "vllm" in item.keywords:
        force_llm = os.getenv("SKIP_LLM", "0") != "1"
        if not llm_gateway.is_server_available() and not force_llm:
            pytest.skip("vLLM server offline or unreachable (SKIP_LLM=1)")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        _TEST_TIMINGS.append((item.nodeid, report.duration, report.outcome.upper()))
    elif report.when == "setup" and report.skipped:
        _TEST_TIMINGS.append((item.nodeid, 0.0, "SKIPPED"))


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Renders formatted timing summary and slowest-first breakdown, writing metrics to test_run_summary.log."""
    t_end = time.time()
    total_elapsed = t_end - _TEST_START_TIME
    start_time_str = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(_TEST_START_TIME)
    )
    end_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t_end))

    passed_count = len(terminalreporter.stats.get("passed", []))
    failed_count = len(terminalreporter.stats.get("failed", []))
    skipped_count = len(terminalreporter.stats.get("skipped", []))

    summary_lines = [
        "",
        "=" * 60,
        "⏱️  [COMMAND TIMING SUMMARY]",
        f"    Started:       {start_time_str}",
        f"    Ended:         {end_time_str}",
        f"    Total Elapsed: {total_elapsed:.2f}s ({total_elapsed/60:.2f} mins)",
        f"    Passed:        {passed_count} | Failed: {failed_count} | Skipped: {skipped_count}",
        "=" * 60,
        "",
        "--- INDIVIDUAL TEST DURATION BREAKDOWN (Slowest First) ---",
    ]

    # Collect stats from terminalreporter
    records = []
    for stat_name, icon in [("passed", "✓"), ("failed", "❌"), ("skipped", "⏭️")]:
        for rep in terminalreporter.stats.get(stat_name, []):
            dur = getattr(rep, "duration", 0.0)
            name = rep.nodeid.split("::")[-1]
            records.append((name, dur, icon))

    records.sort(key=lambda x: x[1], reverse=True)
    for name, dur, icon in records:
        summary_lines.append(f"  {icon} [{dur:6.2f}s] {name}")
    summary_lines.append("")

    summary_text = "\n".join(summary_lines)

    # Print to console
    terminalreporter.write_sep(
        "=", "TIMING BREAKDOWN & METRICS SUMMARY", bold=True, cyan=True
    )
    terminalreporter.write_line(summary_text)

    # Save to metrics log file
    log_path = os.path.join(backend_dir, "test_run_summary.log")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(summary_text)
    except Exception as e:
        terminalreporter.write_line(f"Failed to write test_run_summary.log: {e}")
