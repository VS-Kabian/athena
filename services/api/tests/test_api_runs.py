import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from athena.api.app import app

@pytest.mark.asyncio
async def test_start_research_returns_run_id():
    with patch("athena.api.runs.create_run", AsyncMock(return_value="run-123")), \
         patch("athena.api.runs.asyncio.create_task"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/research", json={
                "topic":"x","rounds":2,"llm":{"provider":"groq","model":"m","api_key":"k"},
                "search":{"providers":["ddg"],"mode":"broadcast"}})
            assert r.status_code == 200 and r.json()["run_id"] == "run-123"

@pytest.mark.asyncio
async def test_cancel_sets_flag():
    with patch("athena.api.runs.bus.cancel") as m, \
         patch("athena.api.runs.execute", AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/research/run-123/cancel")
            assert r.status_code == 200; m.assert_called_once_with("run-123")

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/health")
        assert r.json()["ok"] is True and "db" in r.json()

@pytest.mark.asyncio
async def test_unknown_provider_models_returns_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/providers/notaprovider/models")
        assert r.status_code == 404   # was an unhandled KeyError -> 500

@pytest.mark.asyncio
async def test_start_research_does_not_persist_plaintext_keys():
    import json
    captured = {}
    async def cap_create(topic, rounds, params): captured.update(params); return "rid"

    class _DummyTask:
        def add_done_callback(self, cb): pass
        def done(self): return True
    def cap_task(coro): coro.close(); return _DummyTask()

    with patch("athena.api.runs.create_run", side_effect=cap_create), \
         patch("athena.api.runs.get_key", AsyncMock(return_value="VAULTKEY")), \
         patch("athena.api.runs.run_research", AsyncMock(return_value="")), \
         patch("athena.api.runs.asyncio.create_task", side_effect=cap_task):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/research", json={
                "topic": "t", "rounds": 1,
                "llm": {"provider": "groq", "model": "m", "api_key": "sk-secret-llm"},
                "verifier": {"provider": "deepseek", "model": "v", "api_key": "sk-secret-ver"},
                "search": {"providers": ["tavily"], "mode": "broadcast", "keys": {"tavily": "tvly-secret"}}})
    assert r.status_code == 200
    blob = json.dumps(captured)
    assert "sk-secret-llm" not in blob and "sk-secret-ver" not in blob and "tvly-secret" not in blob
    assert captured["llm"].get("api_key") is None          # llm key stripped from persisted params
    assert captured["verifier"].get("api_key") is None     # verifier key stripped too
    assert captured["search"]["keys"] == {}                # search provider keys stripped
    assert captured["llm"]["model"] == "m"                 # non-secret fields preserved


@pytest.mark.asyncio
async def test_create_run_is_idempotent_against_db_retry():
    import uuid
    from athena.api.runs import create_run
    seen = {}
    async def cap_exec(q, *args): seen["q"] = q; seen["args"] = args
    with patch("athena.api.runs.execute", side_effect=cap_exec):
        rid = await create_run("topic", 2, {"x": 1})
    assert "on conflict (id) do nothing" in seen["q"].lower()   # a retried INSERT won't duplicate
    assert seen["args"][0] == rid                               # id generated client-side, passed in
    uuid.UUID(rid)                                              # ...and is a valid uuid


@pytest.mark.asyncio
async def test_plan_endpoint_returns_subquestions():
    with patch("athena.agents.planner.decompose", AsyncMock(return_value=["q1", "q2"])), \
         patch("athena.agents.planner.extract_entities", AsyncMock(return_value=["LangChain"])), \
         patch("athena.api.runs.get_key", AsyncMock(return_value="k")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/plan", json={"topic": "t", "llm": {"provider": "g", "model": "m", "api_key": "k"}})
    assert r.status_code == 200
    assert r.json()["sub_questions"] == ["q1", "q2"] and r.json()["entities"] == ["LangChain"]
