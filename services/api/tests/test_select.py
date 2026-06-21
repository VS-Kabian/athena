from athena.search.base import SearchHit
from athena.agents.select import select_sources, assemble_content

def entry(url, stype, trust, rel, validated, content=None, snippet="snip"):
    h = SearchHit(url=url, title=url, snippet=snippet, rank=0, provider="x")
    h.relevance = rel
    d = {"hit": h, "round": 1, "source_type": stype, "trust": trust, "validated": validated, "relevance": rel}
    if content is not None:
        d["content"] = content
    return d

def test_selection_guarantees_type_diversity():
    hits = {
        "p": entry("https://arxiv.org/abs/1", "paper", 0.75, 0.6, True),
        "g": entry("https://github.com/a/b", "github", 0.75, 0.55, True),
        "b1": entry("https://blog1.com", "blog", 0.45, 0.95, False),
        "b2": entry("https://blog2.com", "blog", 0.45, 0.92, False),
        "b3": entry("https://blog3.com", "blog", 0.45, 0.90, False),
    }
    sel = select_sources(hits, n=3)
    urls = [e["hit"].url for e in sel]
    # even though blogs have higher relevance, the paper and github are guaranteed in
    assert "https://arxiv.org/abs/1" in urls
    assert "https://github.com/a/b" in urls

def test_assemble_content_prefers_specialist_then_fetch_then_snippet():
    sel = [
        entry("https://arxiv.org/abs/1", "paper", 0.75, 0.8, True, content="ABSTRACT TEXT"),
        entry("https://blog.com", "blog", 0.45, 0.9, False, snippet="SNIP"),
        entry("https://docs.x.com", "docs", 0.6, 0.7, False, snippet="DOCSNIP"),
    ]
    docs = {"https://blog.com": "FETCHED PAGE TEXT"}
    content = assemble_content(sel, docs)
    assert content["https://arxiv.org/abs/1"] == "ABSTRACT TEXT"   # specialist
    assert content["https://blog.com"] == "FETCHED PAGE TEXT"      # extracted
    assert content["https://docs.x.com"] == "DOCSNIP"             # snippet fallback

from athena.agents.select import dedup_near
from athena.search.base import SearchHit

def _e(url, title, trust=0.5, rel=0.7):
    h = SearchHit(url=url, title=title, snippet="s", rank=0, provider="x")
    h.relevance = rel
    return {"hit": h, "round": 1, "source_type": "blog", "trust": trust, "relevance": rel}

def test_dedup_near_collapses_similar_titles():
    hits = {
        "a": _e("https://x.com/1", "LangGraph vs CrewAI vs AutoGen comparison 2026", trust=0.45),
        "b": _e("https://y.com/2", "LangGraph vs CrewAI vs AutoGen comparison 2025", trust=0.6),
        "c": _e("https://z.com/3", "Securing multi-agent systems against prompt injection"),
    }
    out = dedup_near(hits, threshold=0.8)
    titles = [e["hit"].title for e in out.values()]
    # the two near-identical comparison titles collapse to one (the higher-trust kept)
    assert sum(1 for t in titles if "comparison" in t) == 1
    assert any("prompt injection" in t for t in titles)

def test_freshness_boosts_recent_year():
    from athena.agents.select import _freshness
    assert _freshness("Best frameworks in 2026", "https://x.com") > _freshness("A 2021 guide", "https://x.com")

def test_select_covers_named_entities():
    def mk(url, title, trust=0.5, rel=0.7):
        h = SearchHit(url=url, title=title, snippet="", rank=0, provider="x")
        h.relevance = rel
        return {"hit": h, "round": 1, "source_type": "blog", "trust": trust, "relevance": rel}
    hits = {
        "p": mk("https://arxiv.org/abs/1", "A general paper on agents", trust=0.75, rel=0.75),
        "lg": mk("https://x.com/lg", "LangGraph deep dive guide", trust=0.45, rel=0.62),
        "crew": mk("https://y.com/crew", "CrewAI tutorial for teams", trust=0.45, rel=0.62),
    }
    sel = select_sources(hits, n=3, entities=["LangGraph", "CrewAI"])
    titles = " ".join(e["hit"].title.lower() for e in sel)
    assert "langgraph" in titles and "crewai" in titles
