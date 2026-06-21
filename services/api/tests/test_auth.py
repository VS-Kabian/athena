import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from athena.api.app import app


@pytest.mark.asyncio
async def test_protected_route_rejects_missing_token_when_configured():
    with patch("athena.api.auth.settings.athena_api_token", "s3cret"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/keys")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_rejects_wrong_token():
    with patch("athena.api.auth.settings.athena_api_token", "s3cret"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/keys", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_accepts_correct_token():
    with patch("athena.api.auth.settings.athena_api_token", "s3cret"), \
         patch("athena.api.app.list_keys", AsyncMock(return_value=[])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/keys", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200 and r.json() == {"keys": []}


@pytest.mark.asyncio
async def test_auth_open_by_default_for_localhost():
    # token unset (default) -> no auth required, preserving the localhost dev experience
    with patch("athena.api.app.list_keys", AsyncMock(return_value=[])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/keys")
    assert r.status_code == 200


def test_stream_route_is_public_other_routes_protected():
    from athena.api.runs import router, public_router
    assert router.dependencies          # sensitive routes carry require_auth
    assert not public_router.dependencies   # SSE stream stays open (capability = run-id UUID)


@pytest.mark.asyncio
async def test_health_is_open_even_with_token_set():
    with patch("athena.api.auth.settings.athena_api_token", "s3cret"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True


@pytest.mark.asyncio
async def test_lifespan_requires_token_in_prod():
    from cryptography.fernet import Fernet
    from athena.api import app as appmod
    key = Fernet.generate_key().decode()
    with patch("athena.api.app.settings.athena_env", "prod"), \
         patch("athena.api.app.settings.athena_secret", key), \
         patch("athena.api.app.settings.athena_api_token", None):
        with pytest.raises(RuntimeError, match="ATHENA_API_TOKEN"):
            async with appmod.lifespan(appmod.app):
                pass


@pytest.mark.asyncio
async def test_lifespan_rejects_invalid_fernet_secret_in_prod():
    from athena.api import app as appmod
    with patch("athena.api.app.settings.athena_env", "prod"), \
         patch("athena.api.app.settings.athena_secret", "not-a-valid-fernet-key"), \
         patch("athena.api.app.settings.athena_api_token", "tok"):
        with pytest.raises(RuntimeError, match="Fernet"):
            async with appmod.lifespan(appmod.app):
                pass
