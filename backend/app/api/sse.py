import asyncio
import json
from typing import Optional
from fastapi import APIRouter, Request, Query
from sse_starlette.sse import EventSourceResponse
from app.agents.orchestrator import orchestrator

router = APIRouter(prefix="/api/sse", tags=["SSE Telemetry"])


@router.get("/chat")
async def stream_chat_telemetry(
    request: Request,
    query: str = Query("Hello"),
    project_id: str = Query("global"),
):
    """Stream real-time SSE events over unified chat gateway."""

    async def event_generator():
        async for event in orchestrator.process_user_message(
            query, project_id=project_id
        ):
            if await request.is_disconnected():
                print("[SSE] Client disconnected from chat stream.")
                break
            yield {"event": event["event"], "data": json.dumps(event)}

    return EventSourceResponse(event_generator())
