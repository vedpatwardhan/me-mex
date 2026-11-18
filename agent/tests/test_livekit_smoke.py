import pytest

pytestmark = pytest.mark.livekit


def test_token_module_importable():
    pytest.importorskip("livekit")
    from me_mex_agent.tokens import create_access_token

    tok = create_access_token(
        api_key="devkey",
        api_secret="secret",
        room="me-mex",
        identity="tester",
    )
    assert isinstance(tok, str)
    assert len(tok) > 20
