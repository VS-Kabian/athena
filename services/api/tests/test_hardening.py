import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from athena.api.app import app

@pytest.mark.asyncio
async def test_test_key_valid_model_provider():
    with patch("athena.api.keys.get_key", AsyncMock(return_value="gsk-real")), \
         patch("athena.gateway.registry.list_models", AsyncMock(return_value=["llama-3.3-70b"])), \
         patch("athena.gateway.llm.complete", AsyncMock(return_value="hi")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/keys/groq/test")
    assert r.json()["ok"] is True

@pytest.mark.asyncio
async def test_test_key_invalid():
    async def boom(*a, **k): raise RuntimeError("GroqException - Invalid API Key (401)")
    with patch("athena.api.keys.get_key", AsyncMock(return_value="bad")), \
         patch("athena.gateway.registry.list_models", AsyncMock(return_value=["m"])), \
         patch("athena.gateway.llm.complete", side_effect=boom):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/keys/groq/test")
    body = r.json()
    assert body["ok"] is False and "invalid" in body["message"].lower()

@pytest.mark.asyncio
async def test_test_key_search_provider_just_checks_presence():
    with patch("athena.api.keys.get_key", AsyncMock(return_value="tvly-x")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/keys/tavily/test")
    assert r.json()["ok"] is True

@pytest.mark.asyncio
async def test_run_research_clamps_rounds(monkeypatch):
    # rounds > 5 must be clamped; we just assert the inner gets <=5
    seen = {}
    async def fake_inner(run_id, topic, rounds, *args, **kwargs):
        seen["rounds"] = rounds
        return "# ok"
    with patch("athena.agents.graph._run_research_inner", side_effect=fake_inner):
        from athena.agents.graph import run_research
        await run_research("r", "t", 99, {"provider": "g", "model": "m"}, [], "broadcast")
    assert seen["rounds"] == 5
