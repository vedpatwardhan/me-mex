import pytest

pytestmark = pytest.mark.livekit


def test_livekit_token_endpoint(client):
    r = client.post("/api/livekit/token", json={"room": "me-mex", "identity": "pytest"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("token")
    assert body.get("url")
