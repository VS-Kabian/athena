"""Key-vault tests.

IMPORTANT: these run against the live database, so they use throwaway provider names
(prefixed `zztest_`) and clean up after themselves. They must NEVER write to real
provider rows (groq/gemini/deepseek/tavily/serper), or they would overwrite a user's
saved keys.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from athena.api.app import app
from athena.api import keys

P1 = "zztest_alpha"
P2 = "zztest_beta"
P3 = "zztest_gamma"
P4 = "zztest_delta"


@pytest.mark.asyncio
async def test_set_get_roundtrip():
    try:
        await keys.set_key(P1, "sk-test-1234567890")
        assert await keys.get_key(P1) == "sk-test-1234567890"
    finally:
        await keys.delete_key(P1)


@pytest.mark.asyncio
async def test_list_keys_masks():
    try:
        await keys.set_key(P2, "tvly-abcdefgh1234")
        listed = {k["provider"]: k for k in await keys.list_keys()}
        assert listed[P2]["set"] is True
        assert "tvly" in listed[P2]["masked"] or "•" in listed[P2]["masked"]
        assert "abcdefgh" not in listed[P2]["masked"]  # middle hidden
    finally:
        await keys.delete_key(P2)


@pytest.mark.asyncio
async def test_delete_key():
    await keys.set_key(P3, "ser-xyz9876")
    await keys.delete_key(P3)
    assert await keys.get_key(P3) is None


@pytest.mark.asyncio
async def test_key_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        try:
            r = await c.put(f"/api/keys/{P4}", json={"api_key": "AIza-secret-0001"})
            assert r.status_code == 200
            r2 = await c.get("/api/keys")
            provs = {k["provider"] for k in r2.json()["keys"]}
            assert P4 in provs
        finally:
            r3 = await c.delete(f"/api/keys/{P4}")
            assert r3.status_code == 200
