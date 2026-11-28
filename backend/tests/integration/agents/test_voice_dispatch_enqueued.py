import time
from dataclasses import replace

import pytest
from app.llm import get_chains, set_chains_override
from app.llm.schemas import WorkerRoute
from langchain_core.runnables import RunnableLambda
from tests.sse_util import iter_sse_data


@pytest.mark.dock_turn_plane
def test_turn_dispatch_retrieval(client, project, voice_context_json, mock_vllm_chat):
    base = get_chains()
    set_chains_override(
        replace(
            base,
            supervisor=RunnableLambda(
                lambda _inp: WorkerRoute(
                    worker="retrieval",
                    intent="retrieval",
                    dispatch=True,
                )
            ),
        )
    )
    r = client.post(
        "/api/conversation/turn/stream",
        json={
            "text": "What relates to grasping?",
            "thread_id": "voice-dispatch",
            "context_json": voice_context_json,
        },
    )
    assert r.status_code == 200
    end = None
    for chunk in iter_sse_data(r):
        if chunk.get("type") == "turn_end":
            end = chunk
    assert end is not None
    assert end.get("dispatched") is True
    assert end.get("job_id")
    time.sleep(0.3)
    from app.agents import job_runtime

    job = job_runtime.get_job(end["job_id"])
    assert job is not None
    assert job.get("status") in ("done", "awaiting_approval", "running")
    br = client.get(
        "/api/agent/session/briefing",
        params={"project_id": project.id, "thread_id": "voice-dispatch"},
    )
    jobs = br.json().get("active_jobs") or []
    if job.get("status") == "done":
        assert not any(j.get("job_id") == end["job_id"] for j in jobs)
    else:
        assert any(j.get("job_id") == end["job_id"] for j in jobs)
