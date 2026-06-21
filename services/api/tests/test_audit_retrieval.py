"""Regression tests for the retrieval/search audit findings:
F-001 (fetch stream-cap), F-005 (select reserve respects n), F-007 (relevance memoization),
F-008 (github concurrent READMEs), F-010 (rerank fill reaches k), F-012 (2024 freshness boost),
F-014 (single/priority providers seeded), F-020 (rrf deterministic tie-break),
F-021 (select_span embedding length guard), F-022 (url_hash percent-encoding case).
"""
import asyncio
import time

import httpx
import pytest
import respx
from unittest.mock import AsyncMock, patch


# ── F-001: stream the body and stop at the byte cap instead of buffering the whole thing ──
@pytest.mark.asyncio
async def test_fetch_caps_bytes_pulled_from_a_huge_stream():
    from athena.fetch import fetch_extract

    pulled = {"n": 0}
    chunk = b"A" * 65536  # 64 KiB per chunk

    # respx doesn't stream lazily, so drive the cap via a fake client/response with a real async
    # iterator and count how many bytes fetch_extract actually pulls before it stops at the cap.
    class _Resp:
        status_code = 200
        is_redirect = False
        headers = {"content-type": "text/html"}
        extensions = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def aiter_bytes(self):
            for _ in range(800):
                pulled["n"] += len(chunk)
                yield chunk

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, method, url):
            return _Resp()

    max_bytes = 2_000_000
    with patch("athena.fetch.httpx.AsyncClient", _Client), \
         patch("athena.fetch.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]), \
         patch("athena.fetch.cache.get_json", AsyncMock(return_value=None)), \
         patch("athena.fetch.cache.set_json", AsyncMock(return_value=None)), \
         patch("athena.fetch.trafilatura.extract", return_value=None), \
         patch("athena.fetch.settings.js_fetch", False):
        await fetch_extract("https://huge.example.com/p", max_bytes=max_bytes)
    # we must have stopped well before pulling the whole 50 MB body
    assert pulled["n"] < max_bytes + len(chunk)     # at most one chunk past the cap
    assert pulled["n"] < 50 * 1024 * 1024 / 4       # nowhere near the full body


@pytest.mark.asyncio
@respx.mock
async def test_fetch_stream_still_extracts_and_revalidates_peer():
    """The streamed path preserves the DNS-rebinding peer check (rejects internal peers)."""
    from athena.fetch import fetch_extract

    class _Stream:
        def get_extra_info(self, k):
            return ("169.254.169.254", 443) if k == "server_addr" else None

    html = ("<html><body><article><p>" + ("real streamed body content. " * 10)
            + "</p></article></body></html>")
    respx.get("https://rebind2.example.com/x").mock(
        return_value=httpx.Response(200, text=html, extensions={"network_stream": _Stream()}))
    with patch("athena.fetch.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]), \
         patch("athena.fetch.cache.get_json", AsyncMock(return_value=None)), \
         patch("athena.fetch.cache.set_json", AsyncMock(return_value=None)):
        text = await fetch_extract("https://rebind2.example.com/x")
    assert text is None   # connected peer is link-local -> refused before body is parsed


@pytest.mark.asyncio
@respx.mock
async def test_fetch_stream_extracts_real_text():
    from athena.fetch import fetch_extract
    html = ("<html><body><article><h1>RAG</h1><p>"
            + ("Retrieval augmented generation is useful. " * 8) + "</p></article></body></html>")
    respx.get("https://stream.example.com/a").mock(return_value=httpx.Response(200, text=html))
    with patch("athena.fetch.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]), \
         patch("athena.fetch.cache.get_json", AsyncMock(return_value=None)), \
         patch("athena.fetch.cache.set_json", AsyncMock(return_value=None)):
        text = await fetch_extract("https://stream.example.com/a")
    assert text and "Retrieval augmented generation" in text


# ── F-005: reserve passes must respect `n` so guaranteed entity sources survive [:n] ──
def test_select_entity_sources_survive_small_n():
    from athena.search.base import SearchHit
    from athena.agents.select import select_sources

    def entry(url, stype, trust, rel, title):
        h = SearchHit(url=url, title=title, snippet="", rank=0, provider="x")
        h.relevance = rel
        return {"hit": h, "round": 1, "source_type": stype, "trust": trust,
                "validated": False, "relevance": rel}

    # three authoritative-type sources + two OTHER sources that match the named entities
    hits = {
        "p": entry("https://arxiv.org/abs/1", "paper", 0.9, 0.9, "A general paper"),
        "g": entry("https://github.com/a/b", "github", 0.9, 0.9, "A repo"),
        "d": entry("https://docs.x.com/y", "docs", 0.9, 0.9, "Some docs"),
        "lg": entry("https://x.com/lg", "blog", 0.4, 0.5, "LangGraph deep dive"),
        "crew": entry("https://y.com/crew", "blog", 0.4, 0.5, "CrewAI tutorial"),
    }
    sel = select_sources(hits, n=3, entities=["LangGraph", "CrewAI"])
    urls = {e["hit"].url for e in sel}
    assert len(sel) == 3
    # both guaranteed entity sources survive the [:n] truncation
    assert "https://x.com/lg" in urls and "https://y.com/crew" in urls


# ── F-007: identical (query, text) pairs aren't re-scored across calls ──
def test_relevance_memoizes_rerank_across_calls():
    from athena.search.base import SearchHit
    from athena.search import relevance

    relevance._SCORE_CACHE.clear()
    calls = {"n": 0}

    def counting_rerank(topic, texts):
        calls["n"] += len(texts)
        return [5.0 if "rag" in t.lower() else -5.0 for t in texts]

    def mk(url, title):
        return SearchHit(url=url, title=title, snippet="s", rank=0, provider="ddg")

    hits = [mk("https://a.com", "RAG frameworks"), mk("https://b.com", "Hire PHP Developers")]
    with patch("athena.search.relevance.rerank", side_effect=counting_rerank):
        relevance.filter_by_relevance("topic", list(hits), threshold=0.5)
        first = calls["n"]
        # same (topic, title+snippet) pairs again -> served from cache, reranker not re-called
        relevance.filter_by_relevance("topic", list(hits), threshold=0.5)
    assert first == 2          # both texts scored once on the first pass
    assert calls["n"] == 2     # second pass added zero new rerank work


def test_relevance_cache_overflow_clears():
    from athena.search import relevance
    relevance._SCORE_CACHE.clear()
    # seed PAST the cap so the next call triggers the up-front clear (bounded, drop-nothing-we-need)
    relevance._SCORE_CACHE.update({("q", str(i)): 0.0 for i in range(relevance._SCORE_CACHE_CAP + 1)})

    def fake_rerank(topic, texts):
        return [1.0 for _ in texts]

    with patch("athena.search.relevance.rerank", side_effect=fake_rerank):
        out = relevance._rerank_cached("q", ["brand-new-text"])
    assert out == [1.0]                                       # correct score, no KeyError
    assert len(relevance._SCORE_CACHE) <= relevance._SCORE_CACHE_CAP   # cleared up-front -> bounded again


# ── F-008: github READMEs are fetched concurrently, not serially ──
@pytest.mark.asyncio
@respx.mock
async def test_github_fetches_readmes_concurrently():
    from athena.search.specialist import github_search

    respx.get("https://api.github.com/search/repositories").mock(return_value=httpx.Response(200, json={
        "items": [
            {"full_name": f"org/repo{i}", "html_url": f"https://github.com/org/repo{i}",
             "description": f"desc {i}", "stargazers_count": 100 + i}
            for i in range(4)]}))

    DELAY = 0.3

    async def slow_readme(request):
        await asyncio.sleep(DELAY)
        return httpx.Response(200, text="README body for a repo")

    for i in range(4):
        respx.get(f"https://api.github.com/repos/org/repo{i}/readme").mock(side_effect=slow_readme)

    t0 = time.perf_counter()
    res = await github_search("anything", k=4)
    elapsed = time.perf_counter() - t0

    assert len(res) == 4 and all("README body" in r["content"] for r in res)
    # serial would be ~4*DELAY=1.2s; concurrent should finish near a single DELAY
    assert elapsed < DELAY * 2.5


# ── F-010: when rerank runs, the fill loop can reach k from items ranked 49+ ──
def test_build_evidence_reaches_k_beyond_top48():
    from athena.rag import build_evidence

    # 60 single-chunk URLs; rerank only scores the top-48 candidates (rest carry embedding score).
    docs = {f"https://site{i}.com": f"chunk body number {i} about the topic" for i in range(60)}
    # one chunk each, so per_doc_cap can't starve fill; we need fill to dip past index 48 to reach k.
    with patch("athena.rag.embed_passages", side_effect=lambda t: [[1.0, 0.0] for _ in t]), \
         patch("athena.rag.embed_query", return_value=[1.0, 0.0]), \
         patch("athena.rag.rerank", side_effect=lambda q, texts: [float(len(texts) - i) for i in range(len(texts))]):
        ev = build_evidence("topic", docs, k=55, per_doc_cap=2)
    assert len(ev) == 55   # reached k by drawing from the full item list, not just the top-48


# ── F-012: 2024 sources get the recency boost ──
def test_freshness_boosts_2024():
    from athena.agents.select import _freshness
    assert _freshness("A 2024 guide", "https://x.com") > _freshness("A 2021 guide", "https://x.com")
    assert _freshness("A 2024 guide", "https://x.com") == _freshness("A 2025 guide", "https://x.com")


# ── F-014: single/priority hits reach the pool with providers=[provider] ──
@pytest.mark.asyncio
async def test_single_and_priority_seed_providers():
    from athena.search.base import SearchHit
    from athena.search.registry import multi_search

    class Fake:
        def __init__(self, name, urls): self.name = name; self.urls = urls
        async def search(self, q, k=10):
            return [SearchHit(url=u, title=u, snippet="", rank=i, provider=self.name)
                    for i, u in enumerate(self.urls)]

    with patch("athena.search.registry.cache.get_json", AsyncMock(return_value=None)), \
         patch("athena.search.registry.cache.set_json", AsyncMock(return_value=None)):
        single = await multi_search("q", [Fake("ddg", ["https://x.com"])], mode="single")
        prio = await multi_search("q", [Fake("ddg", ["https://y.com"]), Fake("b", ["https://z.com"])],
                                  mode="priority")
    assert single and all(h.providers == [h.provider] for h in single)
    assert prio and all(h.providers == [h.provider] for h in prio)


# ── F-020: equal rrf_score ties order deterministically by url_hash ──
def test_rrf_tie_break_is_deterministic():
    from athena.search.base import SearchHit
    from athena.search.merge import rrf_merge

    def h(url): return SearchHit(url=url, title=url, snippet="", rank=0, provider="x")

    a = [h("https://zzz.com"), h("https://aaa.com"), h("https://mmm.com")]
    merged1 = rrf_merge([a], k=60)
    merged2 = rrf_merge([list(reversed(a))], k=60)   # same hits, different iteration order
    # all three share rank 0 -> equal rrf_score; order must be stable regardless of input order
    assert [m.url for m in merged1] == [m.url for m in merged2]
    # and the order is by url_hash ascending
    assert [m.url for m in merged1] == sorted(m.url for m in merged1)


# ── F-021: select_span embedding fallback guards len(vecs)==len(sents) ──
def test_select_span_embedding_short_vecs_does_not_indexerror():
    from athena.rag import select_span

    text = "Alpha statement about cars. Beta statement about quantum qubits. Gamma about birds."

    with patch("athena.rag.rerank", return_value=[]), \
         patch("athena.rag.embed_query", return_value=[1.0, 0.0]), \
         patch("athena.rag.embed_passages", return_value=[[1.0, 0.0]]):   # ONE fewer vector than sentences
        span = select_span("cars", text)
    # degrades to leading text instead of raising IndexError past the vecs list
    assert span.startswith("Alpha statement about cars")


# ── F-022: url_hash normalizes percent-encoding case ──
def test_url_hash_normalizes_percent_encoding_case():
    from athena.search.base import url_hash
    assert url_hash("https://example.com/a%2Fb") == url_hash("https://example.com/a%2fb")
    assert url_hash("https://example.com/path%3Fq") == url_hash("https://example.com/path%3fq")
