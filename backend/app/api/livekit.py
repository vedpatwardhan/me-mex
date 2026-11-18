"""LiveKit dev token endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter(prefix="/api/livekit", tags=["livekit"])


class TokenRequest(BaseModel):
    room: str = Field(default="me-mex", min_length=1)
    identity: str = Field(default="user", min_length=1)


@router.post("/token")
def issue_token(body: TokenRequest):
    try:
        from livekit import api
    except ImportError as e:
        raise HTTPException(501, "livekit package not installed") from e
    grant = api.VideoGrants(room_join=True, room=body.room)
    token = api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
    token.with_identity(body.identity).with_grants(grant)
    return {
        "token": token.to_jwt(),
        "url": settings.LIVEKIT_URL,
    }
