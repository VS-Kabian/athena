"""Multi-hop citation chasing (Upgrade 1): link extraction, authority ranking, bounded second hop."""
import pytest
from unittest.mock import patch, AsyncMock

from athena.agents import hop
from athena.agents.hop import extract_links, rank_links, chase
from athena.search.base import SearchHit


def test_extract_links_resolves_relative_and_drops_junk():
    html = ('<a href="/docs/guide">rel</a>'
            '<a href="https://other.com/page">abs</a>'
            '<a href="mailto:x@y.com">mail</a>'
            '<a href="https://site.com/app.js">asset</a>'
            '<a href="https://other.com/page#frag">dup</a>')
    links = extract_links(html, "https://site.com/blog/post")
    assert "https://site.com/docs/guide" in links     # relative resolved
    assert "https://other.com/page" in links          # absolute kept
    assert not any("mailto" in u for u in links)       # scheme dropped
    assert not any(u.endswith(".js") for u in links)   # asset dropped
    assert links.count("https://other.com/page") == 1  # fragment-dup collapsed


def test_rank_links_orders_by_authority_and_drops_seen():
    links = ["https://random-seo-blog.io/top10", "https://arxiv.org/abs/2401.00001",
             "https://docs.python.org/3/library", "https://seen.com/x"]
    ranked = rank_links("python library docs", links, seen_keys={"https://seen.com/x"}, k=3)
    assert "https://seen.com/x" not in ranked                       # already-seen dropped
    assert ranked[0] in ("https://arxiv.org/abs/2401.00001", "https://docs.python.org/3/library")
    assert "random-seo-blog" in ranked[-1]                          # low authority ranked last


def _read_entry(url, subq, rel):
    return {"hit": SearchHit(url, "T", "s", 0, "p"), "subq": subq, "relevance": rel, "content": "body"}


@pytest.mark.asyncio
async def test_chase_adds_relevant_primaries_attributed_to_parent_facet():
    all_hits = {"p1": _read_entry("https://blog.com/post", "facet-A", 0.8)}

    async def fake_harvest(url):
        return ["https://docs.langchain.com/primary", "https://offtopic.com/junk"]

    async def fake_fetch_many(urls, limit=12):
        return {u: f"content of {u}" for u in urls}

    def fake_filter(topic, hits):
        for h in hits:
            h.relevance = 0.8 if "langchain" in h.url else 0.1   # one on-topic, one off-topic
        return [h for h in hits if h.relevance >= 0.45]

    with patch.object(hop, "_harvest", side_effect=fake_harvest), \
         patch.object(hop, "fetch_many", side_effect=fake_fetch_many), \
         patch.object(hop, "filter_by_relevance", side_effect=fake_filter), \
         patch.object(hop.bus, "publish", new=AsyncMock()):
        added = await chase("r", "langchain docs", all_hits, rnd=2)

    assert added == 1                                              # off-topic primary dropped
    key = "https://docs.langchain.com/primary"
    assert key in all_hits
    e = all_hits[key]
    assert e["subq"] == "facet-A" and e["hop"] == 2 and e["content"].startswith("content of")


@pytest.mark.asyncio
async def test_chase_noop_without_read_sources():
    # nothing has been read yet -> nothing to harvest from
    assert await chase("r", "topic", {"u": {"hit": SearchHit("https://a", "t", "s", 0, "p"),
                                            "relevance": 0.5}}, rnd=1) == 0
