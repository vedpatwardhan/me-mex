"""Per-xdist-worker directories for Mongo, checkpoints, and traces (pytest)."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def xdist_worker_label() -> str:
    return os.environ.get("PYTEST_XDIST_WORKER") or "master"


def configure_pytest_worker_runtime() -> Path:
    """Set env vars before importing app.config. Returns the worker runtime root."""
    os.environ.setdefault("TESTING", "1")
    worker = xdist_worker_label()

    if worker != "master":
        os.environ["DB_NAME"] = f"test-me-mex-{worker}"
    else:
        os.environ.setdefault("DB_NAME", "test-me-mex")

    runtime_root = BACKEND_DIR / "data" / "pytest_runtime" / worker
    for sub in ("checkpoints", "llm_traces", "decision_traces"):
        (runtime_root / sub).mkdir(parents=True, exist_ok=True)

    os.environ["CHECKPOINTS_DIR"] = str(runtime_root / "checkpoints")
    os.environ["ME_MEX_TRACE_DIR"] = str(runtime_root / "llm_traces")
    os.environ["DECISION_TRACE_DIR"] = str(runtime_root / "decision_traces")
    os.environ.setdefault("DECISION_TRACE_ENABLED", "false")

    return runtime_root
