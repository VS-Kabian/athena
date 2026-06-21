import pytest
from unittest.mock import patch, AsyncMock
from athena.agents.graph import run_research
from athena.search.base import SearchHit


@pytest.mark.asyncio
async def test_orchestration_uses_fast_synthesis_uses_strong():
    seen = {"decompose": None, "synth": None}

    async def fake_decompose(topic, n, llm):
        seen["decompose"] = llm["model"]
        return ["q1"]

    async def fake_synth(topic, ev, llm, **k):
        seen["synth"] = llm["model"]
        return ("# Report", ["u1"], {"u1": "c"})

    hits = [SearchHit("u1", "A", "s", 0, "ddg")]
    with patch("athena.agents.graph.decompose", side_effect=fake_decompose), \
         patch("athena.agents.graph.synthesize_sections", side_effect=fake_synth), \
         patch("athena.agents.graph.bus.publish", AsyncMock()), \
         patch("athena.agents.graph.bus.is_cancelled", return_value=False), \
         patch("athena.agents.graph.arxiv_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.github_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.extract_entities", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.filter_by_relevance", side_effect=lambda t, h: h), \
         patch("athena.agents.graph.multi_search", AsyncMock(return_value=hits)), \
         patch("athena.agents.graph.persist_sources", AsyncMock()), \
         patch("athena.agents.graph.recall", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.remember", AsyncMock()), \
         patch("athena.agents.graph.select_sources", side_effect=lambda a, n=20, entities=None: list(a.values())), \
         patch("athena.agents.graph.fetch_many", AsyncMock(return_value={"u1": "c"})), \
         patch("athena.agents.graph.assemble_content", side_effect=lambda s, d: {"u1": "c"}), \
         patch("athena.agents.graph.build_evidence", return_value=[{"url": "u1", "text": "c", "score": 0.9}]), \
         patch("athena.agents.graph.factcheck", return_value={"risk": 0.0, "total": 1, "unsupported": 0, "flagged": []}), \
         patch("athena.agents.graph.select_span", side_effect=lambda t, x, max_chars=400: x), \
         patch("athena.agents.graph.persist_report", AsyncMock()):
        await run_research("r", "topic", rounds=1,
                           llm={"provider": "deepseek", "model": "deepseek-reasoner", "api_key": "k"},
                           providers=[], mode="broadcast",
                           llm_fast={"provider": "groq", "model": "llama-3.3-70b-versatile", "api_key": "k"})
    assert seen["decompose"] == "llama-3.3-70b-versatile"   # orchestration -> fast
    assert seen["synth"] == "deepseek-reasoner"             # synthesis -> strong


@pytest.mark.asyncio
async def test_absent_llm_fast_uses_strong_everywhere():
    seen = {"decompose": None}

    async def fake_decompose(topic, n, llm):
        seen["decompose"] = llm["model"]
        return ["q1"]

    hits = [SearchHit("u1", "A", "s", 0, "ddg")]
    with patch("athena.agents.graph.decompose", side_effect=fake_decompose), \
         patch("athena.agents.graph.synthesize_sections", AsyncMock(return_value=("# Report", ["u1"], {"u1": "c"}))), \
         patch("athena.agents.graph.bus.publish", AsyncMock()), \
         patch("athena.agents.graph.bus.is_cancelled", return_value=False), \
         patch("athena.agents.graph.arxiv_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.github_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.extract_entities", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.filter_by_relevance", side_effect=lambda t, h: h), \
         patch("athena.agents.graph.multi_search", AsyncMock(return_value=hits)), \
         patch("athena.agents.graph.persist_sources", AsyncMock()), \
         patch("athena.agents.graph.recall", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.remember", AsyncMock()), \
         patch("athena.agents.graph.select_sources", side_effect=lambda a, n=20, entities=None: list(a.values())), \
         patch("athena.agents.graph.fetch_many", AsyncMock(return_value={"u1": "c"})), \
         patch("athena.agents.graph.assemble_content", side_effect=lambda s, d: {"u1": "c"}), \
         patch("athena.agents.graph.build_evidence", return_value=[{"url": "u1", "text": "c", "score": 0.9}]), \
         patch("athena.agents.graph.factcheck", return_value={"risk": 0.0, "total": 1, "unsupported": 0, "flagged": []}), \
         patch("athena.agents.graph.select_span", side_effect=lambda t, x, max_chars=400: x), \
         patch("athena.agents.graph.persist_report", AsyncMock()):
        await run_research("r", "topic", rounds=1,
                           llm={"provider": "groq", "model": "strong-model", "api_key": "k"},
                           providers=[], mode="broadcast")  # no llm_fast
    assert seen["decompose"] == "strong-model"  # defaults to strong when no fast model given
