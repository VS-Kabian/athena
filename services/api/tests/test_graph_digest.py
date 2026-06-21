import pytest
from unittest.mock import patch, AsyncMock
from athena.agents.graph import _round_digest, _read_top, _fanout_search
from athena.search.base import SearchHit


@pytest.mark.asyncio
async def test_fanout_searches_question_plus_entity_variants():
    calls = []
    async def fake_ms(q, providers, mode="broadcast", k=8):
        calls.append(q)
        return [SearchHit(f"https://{len(calls)}.com", "T", "s", rank=0, provider="ddg")]
    with patch("athena.agents.graph.multi_search", side_effect=fake_ms):
        out = await _fanout_search("what is RAG", ["LangChain", "LlamaIndex"], [], "broadcast", 8)
    assert "what is RAG" in calls
    assert any("LangChain" in c for c in calls)   # entity-grounded reformulation searched too
    assert len(out) >= 1


@pytest.mark.asyncio
async def test_fanout_with_no_entities_still_adds_authority_variant():
    calls = []
    async def fake_ms(q, providers, mode="broadcast", k=8):
        calls.append(q)
        return [SearchHit("https://a.com", "T", "s", rank=0, provider="ddg")]
    with patch("athena.agents.graph.multi_search", side_effect=fake_ms):
        await _fanout_search("topic", [], [], "broadcast", 8)
    # R1: even with no entities, the plain query + one authority-intent variant are issued
    assert "topic" in calls and len(calls) == 2
    assert any("documentation" in q or "specification" in q for q in calls)


def test_round_digest_includes_snippets():
    hits = {
        "u1": {"hit": SearchHit("u1", "Title One", "snippet body alpha", 0, "ddg"), "relevance": 0.9},
        "u2": {"hit": SearchHit("u2", "Title Two", "snippet body beta", 0, "ddg"), "relevance": 0.8},
    }
    d = _round_digest(hits, top_n=2)
    assert "Title One" in d and "snippet body alpha" in d
    assert "Title Two" in d and "snippet body beta" in d


def test_round_digest_orders_by_relevance_and_caps():
    hits = {f"u{i}": {"hit": SearchHit(f"u{i}", f"T{i}", f"s{i}", 0, "ddg"), "relevance": i / 10}
            for i in range(10)}
    d = _round_digest(hits, top_n=3)
    lines = d.splitlines()
    assert len(lines) == 3 and lines[0].startswith("T9")  # highest relevance first


def test_round_digest_prefers_fetched_content_over_snippet():
    hits = {"u1": {"hit": SearchHit("u1", "Title", "short snippet", 0, "ddg"),
                   "relevance": 0.9, "content": "FULL EXTRACTED PAGE TEXT"}}
    d = _round_digest(hits, top_n=1)
    assert "FULL EXTRACTED PAGE TEXT" in d and "short snippet" not in d


@pytest.mark.asyncio
async def test_read_top_fetches_and_stores_content_midloop():
    all_hits = {"u1": {"hit": SearchHit("https://u1.com", "T1", "s", 0, "ddg"), "relevance": 0.9}}
    events = []
    async def pub(rid, ev): events.append(ev)
    with patch("athena.agents.graph.bus.publish", side_effect=pub), \
         patch("athena.agents.graph.fetch_many", AsyncMock(return_value={"https://u1.com": "REAL PAGE CONTENT"})):
        await _read_top("r", all_hits, 1)
    assert all_hits["u1"]["content"] == "REAL PAGE CONTENT"          # content stored for reuse at synthesis
    assert any(e["type"] == "reading" for e in events)


@pytest.mark.asyncio
async def test_read_top_skips_already_read_sources():
    all_hits = {"u1": {"hit": SearchHit("https://u1.com", "T1", "s", 0, "ddg"), "relevance": 0.9, "content": "already"}}
    fm = AsyncMock(return_value={})
    with patch("athena.agents.graph.bus.publish", AsyncMock()), \
         patch("athena.agents.graph.fetch_many", fm):
        await _read_top("r", all_hits, 1)
    fm.assert_not_called()   # nothing left to read
