import asyncio
from contextlib import ExitStack

import pytest
from unittest.mock import patch, AsyncMock
from athena.agents.graph import run_research
from athena.search.base import SearchHit

COMMON = dict(providers=[], mode="broadcast")


def _patches(events):
    async def rec(rid, ev):
        events.append(ev)

    hits = [SearchHit("u1", "A", "s", 0, "ddg")]
    return [
        patch("athena.agents.graph.bus.publish", side_effect=rec),
        patch("athena.agents.graph.bus.is_cancelled", return_value=False),
        patch("athena.agents.graph.arxiv_search", AsyncMock(return_value=[])),
        patch("athena.agents.graph.github_search", AsyncMock(return_value=[])),
        patch("athena.agents.graph.decompose", AsyncMock(return_value=["q1"])),
        patch("athena.agents.graph.extract_entities", AsyncMock(return_value=[])),
        patch("athena.agents.graph.filter_by_relevance", side_effect=lambda t, h: h),
        patch("athena.agents.graph.multi_search", AsyncMock(return_value=hits)),
        patch("athena.agents.graph.persist_sources", AsyncMock()),
        patch("athena.agents.graph.recall", AsyncMock(return_value=[])),
        patch("athena.agents.graph.remember", AsyncMock()),
        patch("athena.agents.graph.select_sources", side_effect=lambda a, n=20, entities=None: list(a.values())),
        patch("athena.agents.graph.fetch_many", AsyncMock(return_value={"u1": "c"})),
        patch("athena.agents.graph.assemble_content", side_effect=lambda s, d: {"u1": "c"}),
        patch("athena.agents.graph.build_evidence", return_value=[{"url": "u1", "text": "c", "score": 0.9}]),
        patch("athena.agents.graph.synthesize_sections", AsyncMock(return_value=("# R [1]", ["u1"], {"u1": "c"}))),
        patch("athena.agents.graph.factcheck", return_value={"risk": 0.0, "total": 1, "unsupported": 0, "flagged": []}),
        patch("athena.agents.graph.select_span", side_effect=lambda t, x, max_chars=400: x),
        patch("athena.agents.graph.persist_report", AsyncMock()),
    ]


@pytest.mark.asyncio
async def test_verifier_runs_and_emits_event():
    events = []
    with ExitStack() as st:
        for p in _patches(events):
            st.enter_context(p)
        with patch("athena.agents.graph.verify_report",
                   AsyncMock(return_value=("# R corrected [1]", ["⚠ [verifier: corrected] x"]))) as vr:
            out = await run_research("r", "t", rounds=1,
                                     llm={"provider": "deepseek", "model": "w", "api_key": "k"},
                                     verifier={"provider": "groq", "model": "v", "api_key": "k"}, **COMMON)
    vr.assert_awaited_once()
    assert out == "# R corrected [1]"
    assert any(e["type"] == "verify" for e in events)


@pytest.mark.asyncio
async def test_no_verifier_skips_verification():
    events = []
    with ExitStack() as st:
        for p in _patches(events):
            st.enter_context(p)
        with patch("athena.agents.graph.verify_report", AsyncMock()) as vr:
            await run_research("r", "t", rounds=1,
                               llm={"provider": "deepseek", "model": "w", "api_key": "k"}, **COMMON)
    vr.assert_not_called()
    assert not any(e["type"] == "verify" for e in events)


@pytest.mark.asyncio
async def test_patient_mode_extends_time_budget():
    seen = {}
    real_wait = asyncio.wait_for

    async def fake_wait(coro, timeout=None):
        seen["timeout"] = timeout
        return await real_wait(coro, timeout=timeout)

    with ExitStack() as st:
        for p in _patches([]):
            st.enter_context(p)
        with patch("athena.agents.graph.verify_report", AsyncMock(return_value=("# R", []))), \
             patch("athena.agents.graph.asyncio.wait_for", side_effect=fake_wait):
            await run_research("r", "t", rounds=1,
                               llm={"provider": "g", "model": "w", "api_key": "k"}, patient=True, **COMMON)
    assert seen["timeout"] == 2700
