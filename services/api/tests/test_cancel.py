import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from athena.agents.graph import run_research


@pytest.mark.asyncio
async def test_run_research_handles_cancellederror():
    events = []
    async def pub(rid, ev): events.append(ev)
    async def boom(*a, **k): raise asyncio.CancelledError()
    with patch("athena.agents.graph.bus.publish", side_effect=pub), \
         patch("athena.agents.graph.bus.is_cancelled", return_value=False), \
         patch("athena.agents.graph.decompose", side_effect=boom), \
         patch("athena.db.execute", new=AsyncMock()):
        out = await run_research("r", "t", rounds=1,
                                 llm={"provider": "g", "model": "m", "api_key": "k"},
                                 providers=[], mode="broadcast")
    assert out == ""
    assert any(e["type"] == "cancelled" for e in events)   # clean cancel, not a crash


@pytest.mark.asyncio
async def test_semaphore_serializes_when_full():
    import athena.runner as runner
    runner._sem = asyncio.Semaphore(1)        # cap = 1 for this test
    order = []
    async def fake_inner(*a, **k):
        order.append("start"); await asyncio.sleep(0.05); order.append("end"); return "# ok"
    try:
        with patch("athena.agents.graph._run_research_inner", side_effect=fake_inner), \
             patch("athena.agents.graph.bus.publish", AsyncMock()):
            await asyncio.gather(
                run_research("a", "t", 1, {"provider": "g", "model": "m"}, [], "broadcast"),
                run_research("b", "t", 1, {"provider": "g", "model": "m"}, [], "broadcast"))
    finally:
        runner._sem = None
    assert order == ["start", "end", "start", "end"]   # serialized, never interleaved
