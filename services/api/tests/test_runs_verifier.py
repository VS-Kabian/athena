import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from athena.api.app import app


@pytest.mark.asyncio
async def test_start_research_threads_verifier_and_patient():
    async def fake_run(*a, **k):
        return "# R"

    class _DummyTask:
        def add_done_callback(self, cb): pass
        def done(self): return True

    def cap(coro):
        coro.close()   # we only inspect the call args; don't run the background task
        return _DummyTask()   # runner.register() needs a task-like object

    with patch("athena.api.runs.run_research", side_effect=fake_run) as rr, \
         patch("athena.api.runs.create_run", AsyncMock(return_value="rid")), \
         patch("athena.api.runs.get_key", AsyncMock(return_value="k")), \
         patch("athena.api.runs.asyncio.create_task", side_effect=cap):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/research", json={
                "topic": "t", "rounds": 1,
                "llm": {"provider": "deepseek", "model": "w", "api_key": "k"},
                "verifier": {"provider": "groq", "model": "v", "api_key": "k"},
                "patient": True,
                "search": {"providers": [], "mode": "broadcast", "keys": {}},
            })
    assert r.status_code == 200
    # run_research(run_id, topic, rounds, llm, providers, mode, deep, llm_fast, report_type, verifier, patient)
    a = rr.call_args.args
    assert isinstance(a[9], dict) and a[9]["model"] == "v"   # verifier (index 9)
    assert a[10] is True                                     # patient (index 10)
