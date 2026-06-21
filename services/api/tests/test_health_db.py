import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from athena.api.app import app


@pytest.mark.asyncio
async def test_health_reports_db_status():
    with patch("athena.db.fetch", AsyncMock(return_value=[{"?column?": 1}])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/health")
    assert r.json() == {"ok": True, "db": True}


@pytest.mark.asyncio
async def test_health_db_false_when_unreachable():
    with patch("athena.db.fetch", AsyncMock(side_effect=ConnectionError("down"))):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/health")
    assert r.json()["db"] is False


@pytest.mark.asyncio
async def test_db_retries_once_on_connection_error():
    calls = {"n": 0}

    class FakeConn:
        async def fetch(self, q, *a):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("transient")
            return [{"ok": 1}]

    class FakeAcquire:
        async def __aenter__(self): return FakeConn()
        async def __aexit__(self, *a): return False

    class FakePool:
        def acquire(self): return FakeAcquire()
        async def close(self): pass

    import athena.db as db
    db._pool = FakePool()
    with patch("athena.db.get_pool", AsyncMock(return_value=db._pool)):
        out = await db.fetch("select 1")
    assert calls["n"] == 2 and out == [{"ok": 1}]   # retried once, then succeeded
    db._pool = None
