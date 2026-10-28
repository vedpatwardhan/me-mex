import json
import pytest
from pathlib import Path
from pydantic import BaseModel
from app.services.llm_tracer import LLMTracer


class SampleResponseModel(BaseModel):
    message: str
    status_code: int


def test_llm_tracer_session_and_step_recording(tmp_path: Path):
    tracer = LLMTracer(base_dir=tmp_path)
    session_id = tracer.start_session(session_prefix="test_run")
    assert "test_run" in session_id

    # Log step 1: chat completion
    p1 = tracer.log_call(
        caller="ExecutiveOrchestrator.classify_intent",
        model="test-model",
        messages=[{"role": "user", "content": "hello"}],
        duration_seconds=0.123,
        temperature=0.0,
        max_tokens=100,
        response_raw="Hi there!",
        response_parsed="Hi there!",
        status="SUCCESS",
    )
    assert p1 is not None
    assert p1.exists()
    assert "01_ExecutiveOrchestrator.classify_intent.json" == p1.name

    with open(p1, "r", encoding="utf-8") as f:
        data1 = json.load(f)
    assert data1["caller"] == "ExecutiveOrchestrator.classify_intent"
    assert data1["step_index"] == 1
    assert data1["duration_seconds"] == 0.123
    assert data1["request"]["messages"] == [{"role": "user", "content": "hello"}]
    assert data1["response"]["raw_text"] == "Hi there!"

    # Log step 2: structured completion
    p2 = tracer.log_call(
        caller="DepartmentPersonaAgent[Everything].subgraph_expansion",
        model="test-model",
        messages=[{"role": "user", "content": "expand"}],
        duration_seconds=0.456,
        temperature=0.2,
        max_tokens=500,
        response_raw='{"message": "done", "status_code": 200}',
        response_parsed={"message": "done", "status_code": 200},
        response_model_name="SampleResponseModel",
        status="SUCCESS",
    )
    assert p2 is not None
    assert p2.exists()
    assert "02_DepartmentPersonaAgent[Everything].subgraph_expansion.json" == p2.name

    # Check index.jsonl
    index_file = tmp_path / "index.jsonl"
    assert index_file.exists()
    with open(index_file, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 2
    assert lines[0]["caller"] == "ExecutiveOrchestrator.classify_intent"
    assert lines[1]["caller"] == "DepartmentPersonaAgent[Everything].subgraph_expansion"


def test_llm_tracer_caller_fallback_detection(tmp_path: Path):
    tracer = LLMTracer(base_dir=tmp_path)
    tracer.start_session("fallback")

    def helper_function():
        return tracer.log_call(
            caller=None,  # Should trigger inspect.stack() fallback
            model="test-model",
            messages=[{"role": "user", "content": "fallback"}],
            duration_seconds=0.05,
            temperature=0.0,
            max_tokens=50,
            status="SUCCESS",
        )

    p = helper_function()
    assert p is not None
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "helper_function" in data["caller"]


def test_llm_tracer_fail_safe_on_invalid_directory():
    # Points to a read-only or invalid path
    invalid_tracer = LLMTracer(base_dir=Path("/dev/null/not_a_dir"))
    res = invalid_tracer.log_call(
        caller="TestCaller",
        model="test-model",
        messages=[],
        duration_seconds=0.01,
        temperature=0.0,
        max_tokens=10,
    )
    # Fail-safe: must return None and NOT raise
    assert res is None
