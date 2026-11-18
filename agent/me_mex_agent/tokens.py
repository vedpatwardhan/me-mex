"""Dev LiveKit access tokens (local server keys only)."""

from __future__ import annotations

from livekit import api


def create_access_token(
    *,
    api_key: str,
    api_secret: str,
    room: str,
    identity: str,
) -> str:
    grant = api.VideoGrants(room_join=True, room=room)
    token = api.AccessToken(api_key, api_secret)
    token.with_identity(identity).with_grants(grant)
    return token.to_jwt()
