import threading
import pytest
from unittest.mock import patch, AsyncMock
from athena.agents.graph import run_research, _seed_specialists, _fanout_search, _cap_pool
from athena.search.base import SearchHit


def test_cap_pool_keeps_all_validated_and_strongest():
    # bounding the pool must keep every validated source + the strongest of the rest (undilute ratio)
    all_hits = {f"v{i}": {"validated": True, "trust": 0.8, "relevance": 0.7} for i in range(6)}
    all_hits.update({f"b{i}": {"validated": False, "trust": 0.43, "relevance": 0.6} for i in range(40)})
    capped = _cap_pool(all_hits, cap=20)
    assert len(capped) == 20
    assert sum(1 for v in capped.values() if v["validated"]) == 6   # no validated source dropped
    small = {"a": {"validated": False, "trust": 0.5, "relevance": 0.5}}
    assert _cap_pool(small, cap=20) is small                        # under cap -> unchanged


@pytest.mark.asyncio
async def test_fanout_search_adds_authority_query_variant():
    """R1: an authority-intent query is issued to surface primary sources (docs/specs/standards)."""
    seen = []
    async def fake_multi(q, providers, mode="broadcast", k=10):
        seen.append(q); return []
    with patch("athena.agents.graph.multi_search", side_effect=fake_multi):
        await _fanout_search("what is MCP", [], [], "broadcast", 8)
    assert "what is MCP" in seen                                          # plain query still issued
    assert any("documentation" in q or "specification" in q for q in seen)  # ...plus authority variant


@pytest.mark.asyncio
async def test_specialist_seeding_drops_off_topic_low_relevance():
    """R2: an off-topic specialist seed (low relevance) must not enter the pool."""
    from athena.agents import graph as G
    events = []
    async def pub(rid, ev): events.append(ev)
    paper = {"url": "https://arxiv.org/abs/9999.00001", "title": "Unrelated physics",
             "snippet": "s", "content": "c", "source_type": "paper"}
    def low_rel(t, hits):
        for h in hits:
            h.relevance = 0.2          # below SPECIALIST_REL_FLOOR
        return hits
    all_hits: dict = {}
    with patch("athena.agents.graph.bus.publish", side_effect=pub), \
         patch("athena.agents.graph.arxiv_search", AsyncMock(return_value=[paper])), \
         patch("athena.agents.graph.github_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.filter_by_relevance", side_effect=low_rel):
        await G._seed_specialists("r", "topic", all_hits)
    assert all_hits == {}              # off-topic specialist seed excluded from the pool

@pytest.mark.asyncio
async def test_two_rounds_emit_events_and_collect_sources():
    events = []
    async def fake_publish(run_id, ev): events.append(ev)
    hits = [SearchHit("https://a.com", "A", "s", 0, "ddg"), SearchHit("https://b.com", "B", "s", 0, "ddg")]
    with patch("athena.agents.graph.bus.publish", side_effect=fake_publish), \
         patch("athena.agents.graph.bus.is_cancelled", return_value=False), \
         patch("athena.agents.graph.arxiv_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.github_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.filter_by_relevance", side_effect=lambda topic, hits: hits), \
         patch("athena.agents.graph.decompose", AsyncMock(return_value=["q1"])), \
         patch("athena.agents.graph.extract_entities", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.refine", AsyncMock(return_value=["q2"])), \
         patch("athena.agents.graph.multi_search", AsyncMock(return_value=hits)), \
         patch("athena.agents.graph.persist_sources", AsyncMock()), \
         patch("athena.agents.graph.recall", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.remember", AsyncMock()), \
         patch("athena.agents.graph.select_sources", side_effect=lambda all_hits, n=20, entities=None: list(all_hits.values())), \
         patch("athena.agents.graph.fetch_many", AsyncMock(return_value={"https://a.com": "content"})), \
         patch("athena.agents.graph.assemble_content", side_effect=lambda sel, docs: {"https://a.com": "content"}), \
         patch("athena.agents.graph.build_evidence", return_value=[{"url": "https://a.com", "text": "content", "score": 0.9}]), \
         patch("athena.agents.graph.synthesize_sections", AsyncMock(return_value=("# Report", ["https://a.com"], {"https://a.com": "content"}))), \
         patch("athena.agents.graph.factcheck", return_value={"risk": 0.0, "total": 1, "unsupported": 0, "flagged": []}), \
         patch("athena.agents.graph.persist_report", AsyncMock()):
        report = await run_research("run1", "topic", rounds=2,
                                    llm={"provider": "groq", "model": "m", "api_key": "k"},
                                    providers=[], mode="broadcast")
    types = [e["type"] for e in events]
    assert "round_start" in types and "source" in types and "done" in types
    assert "validated" in types and "quality" in types and "fetching" in types
    assert report.startswith("# Report")

@pytest.mark.asyncio
async def test_deep_mode_does_not_bail_before_min_rounds():
    """R3: a 'stop' at round 1 is ignored (evidence too thin); the agent keeps going, then stops once
    the round adds nothing new (plateau) — never the full budget."""
    events = []
    async def fake_publish(run_id, ev): events.append(ev)
    hits = [SearchHit("https://a.com", "A", "s", 0, "ddg")]   # same hit every round -> plateau after R1
    with patch("athena.agents.graph.bus.publish", side_effect=fake_publish), \
         patch("athena.agents.graph.bus.is_cancelled", return_value=False), \
         patch("athena.agents.graph.arxiv_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.github_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.filter_by_relevance", side_effect=lambda topic, hits: hits), \
         patch("athena.agents.graph.decompose", AsyncMock(return_value=["q1"])), \
         patch("athena.agents.graph.extract_entities", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.refine", AsyncMock(return_value=["q2"])), \
         patch("athena.agents.graph.reflect", AsyncMock(return_value={"action": "stop", "questions": [], "reason": "covered"})), \
         patch("athena.agents.graph.multi_search", AsyncMock(return_value=hits)), \
         patch("athena.agents.graph.persist_sources", AsyncMock()), \
         patch("athena.agents.graph.recall", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.remember", AsyncMock()), \
         patch("athena.agents.graph.select_sources", side_effect=lambda all_hits, n=20, entities=None: list(all_hits.values())), \
         patch("athena.agents.graph.fetch_many", AsyncMock(return_value={"https://a.com": "content"})), \
         patch("athena.agents.graph.assemble_content", side_effect=lambda sel, docs: {"https://a.com": "content"}), \
         patch("athena.agents.graph.build_evidence", return_value=[{"url": "https://a.com", "text": "content", "score": 0.9}]), \
         patch("athena.agents.graph.synthesize_sections", AsyncMock(return_value=("# Report", ["https://a.com"], {"https://a.com": "content"}))), \
         patch("athena.agents.graph.factcheck", return_value={"risk": 0.0, "total": 1, "unsupported": 0, "flagged": []}), \
         patch("athena.agents.graph.persist_report", AsyncMock()):
        report = await run_research("run1", "topic", rounds=5,
                                    llm={"provider": "groq", "model": "m", "api_key": "k"},
                                    providers=[], mode="broadcast", deep=True)
    rounds_seen = sum(1 for e in events if e["type"] == "round_start")
    assert rounds_seen >= 2          # did NOT bail at round 1 despite reflect returning 'stop'
    assert rounds_seen < 5           # but stopped early on plateau, not the full round budget
    assert report.startswith("# Report")


@pytest.mark.asyncio
async def test_plan_seeds_questions_and_skips_decompose():
    events = []
    async def fake_publish(run_id, ev): events.append(ev)
    hits = [SearchHit("https://a.com", "A", "s", 0, "ddg")]
    with patch("athena.agents.graph.bus.publish", side_effect=fake_publish), \
         patch("athena.agents.graph.bus.is_cancelled", return_value=False), \
         patch("athena.agents.graph.arxiv_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.github_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.filter_by_relevance", side_effect=lambda t, h: h), \
         patch("athena.agents.graph.decompose", AsyncMock(return_value=["AUTO Q"])) as dec, \
         patch("athena.agents.graph.extract_entities", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.multi_search", AsyncMock(return_value=hits)), \
         patch("athena.agents.graph.persist_sources", AsyncMock()), \
         patch("athena.agents.graph.recall", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.remember", AsyncMock()), \
         patch("athena.agents.graph.select_sources", side_effect=lambda a, n=20, entities=None: list(a.values())), \
         patch("athena.agents.graph.fetch_many", AsyncMock(return_value={"https://a.com": "content"})), \
         patch("athena.agents.graph.assemble_content", side_effect=lambda s, d: {"https://a.com": "content"}), \
         patch("athena.agents.graph.build_evidence", return_value=[{"url": "https://a.com", "text": "content", "score": 0.9}]), \
         patch("athena.agents.graph.synthesize_sections", AsyncMock(return_value=("# Report", ["https://a.com"], {"https://a.com": "content"}))), \
         patch("athena.agents.graph.factcheck", return_value={"risk": 0.0, "total": 1, "unsupported": 0, "flagged": []}), \
         patch("athena.agents.graph.select_span", side_effect=lambda t, x, max_chars=400: x), \
         patch("athena.agents.graph.persist_report", AsyncMock()):
        await run_research("r", "topic", rounds=1,
                           llm={"provider": "g", "model": "m", "api_key": "k"},
                           providers=[], mode="broadcast", plan=["MY EDITED QUESTION", "   ", "SECOND Q"])
    dec.assert_not_called()                                    # user plan used -> no auto-decompose
    rs = next(e for e in events if e["type"] == "round_start")
    assert rs["data"]["questions"] == ["MY EDITED QUESTION", "SECOND Q"]   # blanks filtered out


@pytest.mark.asyncio
async def test_factcheck_runs_off_the_event_loop_thread():
    """factcheck is CPU-bound ML inference; it must run in a worker thread so it can't freeze the
    event loop (and starve other concurrent runs)."""
    main_thread = threading.current_thread().ident
    seen = {}
    def rec_factcheck(md, srcs, *args, **kwargs):   # tolerate threshold/evidence_chunks (P1-2 signature)
        seen["thread"] = threading.current_thread().ident
        return {"risk": 0.0, "total": 1, "unsupported": 0, "flagged": []}
    hits = [SearchHit("https://a.com", "A", "s", 0, "ddg")]
    with patch("athena.agents.graph.bus.publish", new=AsyncMock()), \
         patch("athena.agents.graph.bus.is_cancelled", return_value=False), \
         patch("athena.agents.graph.arxiv_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.github_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.filter_by_relevance", side_effect=lambda t, h: h), \
         patch("athena.agents.graph.decompose", AsyncMock(return_value=["q1"])), \
         patch("athena.agents.graph.extract_entities", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.multi_search", AsyncMock(return_value=hits)), \
         patch("athena.agents.graph.persist_sources", AsyncMock()), \
         patch("athena.agents.graph.recall", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.remember", AsyncMock()), \
         patch("athena.agents.graph.select_sources", side_effect=lambda a, n=20, entities=None: list(a.values())), \
         patch("athena.agents.graph.fetch_many", AsyncMock(return_value={"https://a.com": "content"})), \
         patch("athena.agents.graph.assemble_content", side_effect=lambda s, d: {"https://a.com": "content"}), \
         patch("athena.agents.graph.build_evidence", return_value=[{"url": "https://a.com", "text": "content", "score": 0.9}]), \
         patch("athena.agents.graph.synthesize_sections", AsyncMock(return_value=("# Report", ["https://a.com"], {"https://a.com": "content"}))), \
         patch("athena.agents.graph.factcheck", side_effect=rec_factcheck), \
         patch("athena.agents.graph.select_span", side_effect=lambda t, x, max_chars=400: x), \
         patch("athena.agents.graph.persist_report", AsyncMock()):
        await run_research("r", "topic", rounds=1,
                           llm={"provider": "g", "model": "m", "api_key": "k"}, providers=[], mode="broadcast")
    assert seen.get("thread") is not None and seen["thread"] != main_thread


@pytest.mark.asyncio
async def test_persist_report_failure_still_surfaces_the_report():
    """A DB blip at the finish line must not discard a fully-synthesized report."""
    events = []
    async def fake_publish(run_id, ev): events.append(ev)
    async def boom(*a, **k): raise RuntimeError("db connection reset")
    hits = [SearchHit("https://a.com", "A", "s", 0, "ddg")]
    with patch("athena.agents.graph.bus.publish", side_effect=fake_publish), \
         patch("athena.agents.graph.bus.is_cancelled", return_value=False), \
         patch("athena.agents.graph.arxiv_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.github_search", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.filter_by_relevance", side_effect=lambda t, h: h), \
         patch("athena.agents.graph.decompose", AsyncMock(return_value=["q1"])), \
         patch("athena.agents.graph.extract_entities", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.multi_search", AsyncMock(return_value=hits)), \
         patch("athena.agents.graph.persist_sources", AsyncMock()), \
         patch("athena.agents.graph.recall", AsyncMock(return_value=[])), \
         patch("athena.agents.graph.remember", AsyncMock()), \
         patch("athena.agents.graph.select_sources", side_effect=lambda a, n=20, entities=None: list(a.values())), \
         patch("athena.agents.graph.fetch_many", AsyncMock(return_value={"https://a.com": "content"})), \
         patch("athena.agents.graph.assemble_content", side_effect=lambda s, d: {"https://a.com": "content"}), \
         patch("athena.agents.graph.build_evidence", return_value=[{"url": "https://a.com", "text": "content", "score": 0.9}]), \
         patch("athena.agents.graph.synthesize_sections", AsyncMock(return_value=("# Report", ["https://a.com"], {"https://a.com": "content"}))), \
         patch("athena.agents.graph.factcheck", return_value={"risk": 0.0, "total": 1, "unsupported": 0, "flagged": []}), \
         patch("athena.agents.graph.select_span", side_effect=lambda t, x, max_chars=400: x), \
         patch("athena.agents.graph.persist_report", side_effect=boom):
        report = await run_research("r", "topic", rounds=1,
                                    llm={"provider": "g", "model": "m", "api_key": "k"}, providers=[], mode="broadcast")
    types = [e["type"] for e in events]
    assert "done" in types and "failed" not in types     # persist blip did NOT fail the run
    assert report.startswith("# Report")                 # ...and the report is still returned


@pytest.mark.asyncio
async def test_specialist_seeding_survives_github_failure():
    """A GitHub rate-limit/error must not discard already-fetched arXiv papers."""
    events = []
    async def fake_publish(run_id, ev): events.append(ev)
    arxiv_hit = {"url": "https://arxiv.org/abs/2401.00001", "title": "Paper", "snippet": "abstract",
                 "content": "full abstract text", "source_type": "paper"}
    def set_rel(t, hits):
        for h in hits:
            h.relevance = 0.9
        return hits
    all_hits: dict = {}
    with patch("athena.agents.graph.bus.publish", side_effect=fake_publish), \
         patch("athena.agents.graph.arxiv_search", AsyncMock(return_value=[arxiv_hit])), \
         patch("athena.agents.graph.github_search", AsyncMock(side_effect=RuntimeError("403 rate limited"))), \
         patch("athena.agents.graph.filter_by_relevance", side_effect=set_rel):
        await _seed_specialists("r", "topic", all_hits)
    assert len(all_hits) == 1                                   # arXiv paper kept despite GitHub failure
    assert any(e["type"] == "source" for e in events)


@pytest.mark.asyncio
async def test_cancel_stops_early():
    with patch("athena.agents.graph.bus.is_cancelled", return_value=True), \
         patch("athena.agents.graph.bus.publish", AsyncMock()), \
         patch("athena.agents.graph.decompose", AsyncMock(return_value=["q1"])):
        report = await run_research("run1","topic",rounds=3,
                                    llm={"provider":"groq","model":"m","api_key":"k"}, providers=[], mode="broadcast")
        assert report == ""


@pytest.mark.asyncio
async def test_failure_emits_failed_event_and_does_not_raise():
    events = []
    async def fake_publish(run_id, ev): events.append(ev)
    async def boom(*a, **k): raise RuntimeError("GroqException - Invalid API Key (401)")
    with patch("athena.agents.graph.bus.publish", side_effect=fake_publish), \
         patch("athena.agents.graph.bus.is_cancelled", return_value=False), \
         patch("athena.agents.graph.decompose", side_effect=boom), \
         patch("athena.db.execute", new=AsyncMock()):
        report = await run_research("run1", "topic", rounds=2,
                                    llm={"provider": "groq", "model": "m", "api_key": "bad"},
                                    providers=[], mode="broadcast")
    types = [e["type"] for e in events]
    assert "failed" in types
    msg = next(e for e in events if e["type"] == "failed")["data"]["message"]
    assert "invalid api key" in msg.lower()
    assert report == ""
