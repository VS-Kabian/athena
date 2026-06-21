"""GraphRAG memory (Phase 3): triple extraction, gated persistence, neighborhood retrieval."""
import pytest
from unittest.mock import patch, AsyncMock

from athena.agents import graphmem
from athena.agents.graphmem import extract_triples, extract_and_store, neighborhood, _norm
from athena.search.base import SearchHit

LLM = {"provider": "g", "model": "m", "api_key": "k"}


def test_norm_lowercases_and_collapses_whitespace():
    assert _norm("  LangGraph   Runtime ") == "langgraph runtime"


@pytest.mark.asyncio
async def test_extract_triples_parses_and_filters_malformed():
    async def fake(*a, **k):
        return '[["LangGraph", "is", "a framework"], ["bad"], ["A", "rel", "B"]]'
    with patch.object(graphmem, "complete", side_effect=fake):
        out = await extract_triples("some text", LLM)
    assert ("LangGraph", "is", "a framework") in out and ("A", "rel", "B") in out
    assert all(len(t) == 3 for t in out)        # the 1-element malformed triple is dropped


@pytest.mark.asyncio
async def test_extract_and_store_is_gated_off_by_default(monkeypatch):
    monkeypatch.setattr(graphmem.settings, "graphrag", False)
    called = {"complete": 0}
    async def fake(*a, **k):
        called["complete"] += 1
        return "[]"
    with patch.object(graphmem, "complete", side_effect=fake):
        n = await extract_and_store("r", {"u": {"validated": True, "content": "x",
                                                "hit": SearchHit("https://a", "t", "s", 0, "p")}}, LLM)
    assert n == 0 and called["complete"] == 0   # flag off -> no model calls at all


@pytest.mark.asyncio
async def test_extract_and_store_persists_when_enabled(monkeypatch):
    monkeypatch.setattr(graphmem.settings, "graphrag", True)
    rows = []
    async def fake_exec(q, *a):
        rows.append((q, a))
    async def fake_complete(*a, **k):
        return '[["LangGraph", "uses", "graphs"]]'
    hits = {"u": {"validated": True, "content": "LangGraph uses graphs", "relevance": 0.9,
                  "hit": SearchHit("https://a.com", "t", "s", 0, "p")}}
    with patch.object(graphmem, "complete", side_effect=fake_complete), \
         patch.object(graphmem, "execute", side_effect=fake_exec):
        n = await extract_and_store("r", hits, LLM)
    assert n >= 1
    assert any("kg_relations" in q for q, _ in rows) and any("kg_entities" in q for q, _ in rows)


@pytest.mark.asyncio
async def test_neighborhood_gated_off_returns_empty(monkeypatch):
    monkeypatch.setattr(graphmem.settings, "graphrag", False)
    assert await neighborhood(["LangGraph"]) == ""


@pytest.mark.asyncio
async def test_neighborhood_returns_relationship_block_when_enabled(monkeypatch):
    monkeypatch.setattr(graphmem.settings, "graphrag", True)
    async def fake_fetch(q, *a):
        return [{"subject": "LangGraph", "predicate": "uses", "object": "graphs"}]
    with patch.object(graphmem, "fetch", side_effect=fake_fetch):
        block = await neighborhood(["LangGraph"])
    assert "LangGraph uses graphs" in block and "KNOWN RELATIONSHIPS" in block
