import asyncio
import json
from fastapi import APIRouter, Request, Query
from sse_starlette.sse import EventSourceResponse
from app.agents.orchestrator import orchestrator

router = APIRouter(prefix="/api/sse", tags=["SSE Telemetry"])


@router.get("/retrieval")
async def stream_retrieval_telemetry(
    request: Request, query: str = Query("latent world models")
):
    """Stream real-time SSE events for multi-persona graph traversal telemetry during retrieval."""

    async def event_generator():
        async for event in orchestrator.execute_retrieval_flow(query):
            if await request.is_disconnected():
                print("[SSE] Client disconnected from retrieval stream.")
                break
            yield {"event": event["event"], "data": json.dumps(event)}

    return EventSourceResponse(event_generator())


@router.get("/ingestion")
async def stream_ingestion_telemetry(
    request: Request,
    title: str = Query("JEPA Latent World Model"),
    content: str = Query(
        "Joint-Embedding Predictive Architecture for robotics latent rollouts."
    ),
):
    """Stream real-time SSE events for ingestion debate, concept creation, passage linking, and macro patching."""

    async def event_generator():
        async for event in orchestrator.execute_ingestion_flow(title, content):
            if await request.is_disconnected():
                print("[SSE] Client disconnected from ingestion stream.")
                break
            yield {"event": event["event"], "data": json.dumps(event)}

    return EventSourceResponse(event_generator())
